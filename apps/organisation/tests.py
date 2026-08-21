"""The rules, and the two places a plausible implementation gives a confident
wrong answer rather than an error.

Those two are what the value is concentrated in. A break resolved the obvious
way and an entitlement scaled by hours both produce a number that looks
perfectly reasonable on the page and is wrong — one underpays a break, the other
quietly gives a part-time employee fewer days off than the law allows. Neither
raises, neither logs, and neither is visible until somebody with a calculator
disagrees with the app.
"""

from decimal import Decimal

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from apps.organisation.models import (
    DEFAULT_BREAK_RULES, AssignmentMode, LeaveRounding, OrgSettings,
    SpecialLeaveThreshold, SpecialLeaveType,
)


class TestTheBreakIsResolvedTheRightWay:
    """The formula is ``max over rules of min(break, max(0, gross - over))``.

    The obvious alternative — "worked over six hours, so thirty minutes" applied
    to the clock-in-to-clock-out span — agrees with it on the long days and is
    wrong on exactly the days most people work. Each case below is one the naive
    version gets wrong, and the numbers are what a works council would write.
    """

    @pytest.mark.parametrize("gross, expected", [
        # Under the first tier: nothing at all.
        (300, 0),
        (360, 0),
        # Just over. The naive version gives the whole 30 and leaves 5h35 of
        # working time — less than the six hours the rule is about. The right
        # answer is only as much break as it takes to come back under.
        (365, 5),
        (380, 20),
        # At and past the point where the full first tier is needed.
        (390, 30),
        (420, 30),
        # Just over the second tier. Its own break already brings the day back
        # under eight hours, so the second tier does not apply — the naive
        # version charges 45 here and takes 15 minutes somebody was working.
        (485, 30),
        (500, 30),
        # Far enough over that 30 is not enough.
        (525, 45),
        (600, 45),
    ])
    def test_the_break_is_only_as_long_as_it_needs_to_be(self, org, gross, expected):
        assert org.required_break(gross) == expected

    def test_the_result_never_leaves_working_time_over_a_tier(self, org):
        """The property the formula exists to guarantee, checked across the day.

        Stated as an invariant rather than as more examples: for every length of
        day, the working time left after the break must not exceed any tier
        whose break was not fully granted. That is the whole content of the
        rule, and a reimplementation that satisfies it cannot be wrong in the
        direction that costs somebody a break.
        """
        rules = list(org.break_rules.all())
        for gross in range(0, 16 * 60, 5):
            taken = org.required_break(gross)
            net = gross - taken
            for rule in rules:
                if net > rule.over_minutes:
                    assert taken >= rule.break_minutes, (
                        f"a {gross}-minute day gets {taken} minutes, leaving {net} "
                        f"minutes of working time — over the {rule.over_minutes} tier "
                        f"without its full {rule.break_minutes}"
                    )

    def test_an_empty_table_falls_back_to_the_defaults(self, db):
        """A database that has never had the settings page opened still computes
        breaks — otherwise a fresh installation would record everybody as
        working through, and nobody would notice until an inspection.

        This is the one place the app overrides what the database literally
        says, and the direction is the point: a break not deducted overstates
        hours worked, which is the side an employer is answerable for.
        """
        settings = OrgSettings.current()
        assert not settings.is_stored
        assert settings.required_break(600) == 45

    def test_an_emptied_table_also_falls_back(self, org):
        """Deleting every rule does *not* mean "no breaks".

        Stated as a test because it is a real trade and somebody will want to
        change it: the cost is that an organisation cannot express "no breaks at
        all", and the benefit is that an empty table never silently produces a
        timesheet with no break on a ten-hour day. In Germany the first is not a
        configuration anybody needs.
        """
        org.break_rules.all().delete()
        org.refresh_from_db()
        assert org.required_break(600) == 45

    def test_is_stored_is_not_the_primary_key(self, db):
        """The primary key is pinned to 1 with a *default*, so an unsaved
        instance already has ``pk == 1``. Every ``if self.pk`` guard therefore
        reads as True and follows relations on a row that was never saved —
        which does not raise, and quietly returns whatever is stored under id 1.
        """
        unsaved = OrgSettings()
        assert unsaved.pk == 1
        assert not unsaved.is_stored

        unsaved.save()
        assert OrgSettings.current().is_stored


class TestTheEntitlementIsProRataByDays:
    """Days, not hours — and that is a legal point rather than a simplification.

    A day of leave buys a day off; how long that day is does not change how many
    of them a year holds. Scaling by hours gives somebody on three ten-hour days
    fewer days off than somebody on three six-hour days, which is the
    discrimination case every works agreement on part-time leave exists to
    avoid.
    """

    def test_a_full_week_gets_the_full_entitlement(self, org):
        assert org.leave_days_for(5) == Decimal("30")

    def test_four_days_gets_four_fifths(self, org):
        assert org.leave_days_for(4) == Decimal("24")

    def test_the_same_days_gets_the_same_leave_however_short(self, org, anna, dilan):
        """Dilan works half Anna's hours across the same five days.

        If this ever fails it will be because somebody 'improved' the
        calculation to use ``weekly_hours``, which reads as more accurate and is
        the exact mistake.
        """
        assert dilan.weekly_hours == anna.weekly_hours / 2
        assert dilan.annual_leave_days(org) == anna.annual_leave_days(org)

    def test_somebody_who_works_no_days_is_entitled_to_nothing(self, org):
        assert org.leave_days_for(0) == Decimal("0.0")

    @pytest.mark.parametrize("rounding, expected", [
        (LeaveRounding.UP, Decimal("17")),
        (LeaveRounding.HALF, Decimal("17")),
        (LeaveRounding.EXACT, Decimal("16.8")),
    ])
    def test_the_fraction_is_handled_as_the_policy_says(self, org, rounding, expected):
        """28 days over five, for somebody on three — 16.8, which no holiday
        calendar can express. What happens to the 0.8 is a policy and not a
        detail, because it has to be the same for two people on one contract."""
        org.full_time_leave_days = Decimal("28.0")
        org.leave_rounding = rounding
        assert org.leave_days_for(3) == expected

    def test_rounding_up_does_not_add_a_day_to_a_whole_number(self, org):
        """The ceiling trap: 30 × 3/5 is exactly 18, and a naive ``ceil`` on a
        Decimal that is 17.999999 by way of a float gives 18 anyway — but the
        version that gives 19 is the one that ships and nobody checks."""
        org.leave_rounding = LeaveRounding.UP
        assert org.leave_days_for(3) == Decimal("18")


class TestTheThreeWaysSpecialLeaveIsWorkedOut:
    """Three modes because three exist in real agreements and they give
    genuinely different numbers. One 'pro rata' mode would be tidier and would
    silently turn "everybody gets their birthday off" into "everybody gets three
    fifths of their birthday off"."""

    def test_a_fixed_type_is_the_same_for_everybody(self, org):
        birthday = SpecialLeaveType.objects.create(
            name="Geburtstag", mode=AssignmentMode.FIXED, days=Decimal("1.0"),
        )
        assert birthday.days_for(5, org) == Decimal("1.0")
        assert birthday.days_for(2, org) == Decimal("1.0")

    def test_a_pro_rata_type_scales_like_the_annual_leave(self, org):
        jubilee = SpecialLeaveType.objects.create(
            name="Jubiläum", mode=AssignmentMode.PRO_RATA, days=Decimal("5.0"),
        )
        assert jubilee.days_for(5, org) == Decimal("5")
        assert jubilee.days_for(3, org) == Decimal("3")

    def test_a_threshold_type_is_a_step_and_the_gap_is_the_point(self, org):
        """"Five days a week gets two, three days gets one" says, by
        implication, that two days a week gets none. Inventing 0.8 for that
        person is exactly what the employer did not agree to, and it is the only
        thing this mode exists to be able to express."""
        training = SpecialLeaveType.objects.create(
            name="Fortbildung", mode=AssignmentMode.THRESHOLD, days=Decimal("0"),
        )
        SpecialLeaveThreshold.objects.create(
            leave_type=training, min_days_per_week=3, days=Decimal("1.0"))
        SpecialLeaveThreshold.objects.create(
            leave_type=training, min_days_per_week=5, days=Decimal("2.0"))

        assert training.days_for(5, org) == Decimal("2.0")
        assert training.days_for(4, org) == Decimal("1.0")
        assert training.days_for(3, org) == Decimal("1.0")
        assert training.days_for(2, org) == Decimal("0.0")

    def test_the_most_generous_matching_row_wins(self, org):
        """Ordered ascending by the model's Meta, so the *last* match is the
        answer. A first-match implementation would give a five-day employee the
        three-day row, which is a smaller number that looks like a real one."""
        training = SpecialLeaveType.objects.create(
            name="Fortbildung", mode=AssignmentMode.THRESHOLD, days=Decimal("0"),
        )
        for days, amount in ((1, "0.5"), (3, "1.0"), (5, "2.0")):
            SpecialLeaveThreshold.objects.create(
                leave_type=training, min_days_per_week=days, days=Decimal(amount))
        assert training.days_for(5, org) == Decimal("2.0")


class TestTheSettingsAreASingleton:
    def test_saving_never_makes_a_second_row(self, db):
        first = OrgSettings.current()
        first.full_time_leave_days = Decimal("25.0")
        first.save()
        second = OrgSettings.current()
        second.full_time_leave_days = Decimal("26.0")
        second.save()
        assert OrgSettings.objects.count() == 1
        assert OrgSettings.current().full_time_leave_days == Decimal("26.0")

    def test_reading_does_not_write(self, db):
        """``current()`` is called while rendering nearly every page. A create
        here would put SQLite's single write lock inside a GET — the
        read-must-not-write rule broken on the hottest path there is."""
        OrgSettings.current()
        assert OrgSettings.objects.count() == 0


# --------------------------------------------------------------------------
# Who may reach these pages
# --------------------------------------------------------------------------

def _routes(namespace):
    """Every named route under one namespace, with a plausible argument set.

    Discovered from the URLconf rather than listed, so a page added next month
    is covered the day it lands — which is the whole point, since the exposure
    is a decorator somebody forgets on a *new* view.
    """
    found = []

    def walk(resolver, app_name):
        for entry in resolver.url_patterns:
            if isinstance(entry, URLResolver):
                walk(entry, entry.app_name or app_name)
            elif isinstance(entry, URLPattern) and entry.name and app_name == namespace:
                found.append(entry)

    walk(get_resolver(), "")
    return found


class TestTheWorkingTimeRulesAreStaffOnly:
    """Checked by walking the URLconf, not by naming the views.

    A forgotten decorator on a page added later is the failure this covers, and
    naming today's views would cover exactly the pages that already have one.
    """

    def test_every_route_refuses_an_ordinary_account(self, client, db):
        from django.urls import reverse

        for pattern in _routes("organisation"):
            try:
                url = reverse(f"organisation:{pattern.name}", args=[1])
            except Exception:
                url = reverse(f"organisation:{pattern.name}")
            response = client.get(url)
            assert response.status_code == 404, (
                f"organisation:{pattern.name} answered {response.status_code} to an "
                "ordinary account — it is missing @staff_required"
            )

    def test_a_manager_is_not_enough(self, manager_client, db):
        """Managing the roster and setting what a day of leave is worth are
        different rights. A deputy head plans shifts; they do not get to move
        everybody's entitlement."""
        from django.urls import reverse

        assert manager_client.get(reverse("organisation:settings")).status_code == 404


def test_the_defaults_are_stricter_than_the_law_rather_than_looser(db):
    """The second tier is eight hours; the Arbeitszeitgesetz says nine.

    A default that erred the other way would ship an app quietly recording
    45-minute breaks as taken when only 30 were required — which is the one
    direction a default about a legal minimum may not err in.
    """
    tiers = dict(DEFAULT_BREAK_RULES)
    assert tiers[360] == 30, "the six-hour tier is statutory"
    assert 480 in tiers and tiers[480] == 45
    assert 540 not in tiers, "nine hours would be the statutory minimum, not a stricter house rule"
