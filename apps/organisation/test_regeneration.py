"""Regenerationstage: the preset, its table, and the figure typed over it.

**The numbers here are the point of the file.** Regenerationstage are an
ordinary threshold type once they exist — nothing in the app knows their name —
so what has to be pinned is that the preset writes the steps the collective
agreement actually gives, and that the step function is what the app answers
with rather than a proportion.

Nr. 1a of Anlage D.12 to the TVöD-V (§ 3.2a TVöD-B): two days a calendar year on
a five-day week, reduced in proportion for fewer working days a week, with at
least half a day rounded *up* to a whole one and anything under a half dropped.
That gives 1 day a week → 0, two or three → 1, four or more → 2 — which is a
step, and it is the reason the type is in the threshold mode. The pro-rata mode
is the obvious choice and gives 1.2 for a three-day week, which is then rounded
by the *house's* own rounding setting: a different rule that agrees with this one
only by accident.
"""

from decimal import Decimal

import pytest

from apps.employees.models import SpecialLeaveGrant
from apps.organisation.models import (
    REGENERATION_NAME, AssignmentMode, LeaveRounding, OrgSettings, SpecialLeaveType,
)


def _install(client):
    return client.post("/settings/working-time/leave-types/regeneration/", follow=True)


@pytest.mark.django_db
class TestThePreset:

    def test_it_writes_the_table_the_agreement_gives(self, staff_client, org):
        _install(staff_client)
        leave_type = SpecialLeaveType.objects.get(name=REGENERATION_NAME)

        assert leave_type.mode == AssignmentMode.THRESHOLD
        assert [
            (row.min_days_per_week, row.days)
            for row in leave_type.thresholds.order_by("min_days_per_week")
        ] == [(2, Decimal("1.0")), (4, Decimal("2.0"))]

    @pytest.mark.parametrize("days_a_week,expected", [
        (1, "0.0"),   # 2 × 1/5 = 0.4, under a half, dropped
        (2, "1.0"),   # 0.8, rounded up
        (3, "1.0"),   # 1.2, the fraction dropped
        (4, "2.0"),   # 1.6, rounded up
        (5, "2.0"),   # the full entitlement
        (6, "2.0"),   # more days than full time buys no more than the two
    ])
    def test_the_steps_are_the_ones_in_the_agreement(
        self, staff_client, org, days_a_week, expected,
    ):
        """The table read straight off the rule, every step of it.

        A one-day week matching no row and getting nothing is an *answer* and
        not a gap: "two or three days gets one" says by implication that one day
        gets none, and inventing 0.4 for that person is precisely what the
        employer did not agree to.
        """
        _install(staff_client)
        leave_type = SpecialLeaveType.objects.get(name=REGENERATION_NAME)
        assert leave_type.days_for(days_a_week) == Decimal(expected)

    def test_the_steps_do_not_move_with_the_house_rounding_setting(
        self, staff_client, org,
    ):
        """The agreement's rounding is not the house's, and a threshold type is
        how the app says so. Under `pro_rata` a three-day week would be 1.2 and
        then whatever `leave_rounding` does to it — two rules that agree only by
        accident, and the day somebody changes the rounding they stop agreeing.
        """
        _install(staff_client)
        leave_type = SpecialLeaveType.objects.get(name=REGENERATION_NAME)

        for rounding in LeaveRounding.values:
            settings = OrgSettings.current()
            settings.leave_rounding = rounding
            settings.save()
            assert leave_type.days_for(3, settings=settings) == Decimal("1.0")

    def test_it_carries_the_note_saying_what_is_not_worked_out(
        self, staff_client, org,
    ):
        """Three things the app does not model — the four-month reduction, the
        31 December deadline, and days taken at another employer — and the note
        is where a manager meets them, at the moment they are deciding whether
        to type over the days."""
        _install(staff_client)
        note = SpecialLeaveType.objects.get(name=REGENERATION_NAME).note
        assert note
        assert "four months" in note
        assert "31 December" in note

    def test_installing_twice_refuses_rather_than_making_a_second_one(
        self, staff_client, org,
    ):
        """Two rows called Regenerationstage is a grant list where nobody can
        tell which one is theirs, and it is the state a double-submitted POST
        would otherwise leave behind."""
        _install(staff_client)
        _install(staff_client)
        assert SpecialLeaveType.objects.filter(name=REGENERATION_NAME).count() == 1

    def test_the_button_is_gone_once_it_is_there(self, staff_client, org):
        """An offer whose only possible outcome is "that already exists" is
        worse than no offer."""
        assert staff_client.get(
            "/settings/working-time/leave-types/"
        ).context["has_regeneration"] is False
        _install(staff_client)
        assert staff_client.get(
            "/settings/working-time/leave-types/"
        ).context["has_regeneration"] is True

    def test_a_house_whose_full_week_is_not_five_days_is_told(self, staff_client, org):
        """The table is written against the five-day week the agreement assumes.
        Said rather than silently scaled: what a house on a different full week
        is entitled to is a question about their agreement, and not one this app
        may answer by moving somebody's statutory days."""
        settings = OrgSettings.current()
        settings.full_time_days_per_week = 6
        settings.save()

        response = _install(staff_client)
        said = [str(message) for message in response.context["messages"]]
        assert any("five-day week" in text for text in said)

    def test_a_manager_who_is_not_staff_cannot_install_it(self, manager_client, org):
        """Changing what a day of leave is worth to everybody at once is the
        software-administration right, not the roster one."""
        manager_client.post("/settings/working-time/leave-types/regeneration/")
        assert not SpecialLeaveType.objects.filter(name=REGENERATION_NAME).exists()


@pytest.mark.django_db
class TestTheFigureTypedOverTheRule:
    """The case the user of this app actually has: somebody who took one of
    their two days at their last job this year, and so is owed one here."""

    def test_an_override_wins_over_the_table(self, staff_client, anna, org):
        _install(staff_client)
        leave_type = SpecialLeaveType.objects.get(name=REGENERATION_NAME)
        grant = SpecialLeaveGrant.objects.create(
            employee=anna, leave_type=leave_type,
            days_override=Decimal("1.0"),
            override_reason="one day already taken at a previous employer",
        )
        # Anna works five days, so the rule would give two.
        assert leave_type.days_for(anna.working_days_per_week) == Decimal("2.0")
        assert grant.days() == Decimal("1.0")

    def test_an_override_with_no_reason_is_refused(self, staff_client, anna, org):
        """The same rule ``correction_reason`` makes and with the same force: a
        number the rules produced and a number somebody typed are the same
        number and mean entirely different things a year later, when the only
        question anybody has is whether the 1.0 was a mistake."""
        from django.core.exceptions import ValidationError

        _install(staff_client)
        grant = SpecialLeaveGrant(
            employee=anna,
            leave_type=SpecialLeaveType.objects.get(name=REGENERATION_NAME),
            days_override=Decimal("1.0"),
        )
        with pytest.raises(ValidationError) as raised:
            grant.full_clean()
        assert "override_reason" in raised.value.message_dict

    def test_no_override_needs_no_reason(self, staff_client, anna, org):
        """The rule's own answer explains itself by being the rule, and asking
        for a sentence about it would be asking a manager to justify not
        intervening."""
        _install(staff_client)
        grant = SpecialLeaveGrant(
            employee=anna,
            leave_type=SpecialLeaveType.objects.get(name=REGENERATION_NAME),
        )
        grant.full_clean()

    def test_an_override_of_nought_still_needs_a_reason(self, staff_client, anna, org):
        """The one somebody would get wrong: ``0`` is falsy and is also the most
        consequential override on the page — it takes the entitlement away
        entirely, and "why" is the whole of what a later reader needs."""
        from django.core.exceptions import ValidationError

        _install(staff_client)
        grant = SpecialLeaveGrant(
            employee=anna,
            leave_type=SpecialLeaveType.objects.get(name=REGENERATION_NAME),
            days_override=Decimal("0.0"),
        )
        with pytest.raises(ValidationError):
            grant.full_clean()
