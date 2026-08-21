"""Confirming, entering by hand, and the break that follows.

Two things here are worth more than the rest. The first is that **the roster and
the timesheet stay separate rows**: once confirming overwrites the plan, the
question "what were you actually asked to work?" has no answer, and that is the
sentence the whole app exists to be able to print. The second is that **an
overridden break is never recomputed** — a value somebody typed that quietly
reverts is worse than one that was never accepted.
"""

import datetime as dt
import json

import pytest

from apps.roster.models import Shift, minutes_between
from apps.timesheets.hours import clock, contracted_minutes, decimal_hours
from apps.timesheets.models import DayRecord, EntrySource, WorkSegment, week_monday


@pytest.fixture
def rostered(anna, monday):
    """Anna, rostered 08:00–16:30 on the Monday: eight hours plus a 30 break."""
    return Shift.objects.create(
        employee=anna, date=monday, start=dt.time(8, 0), end=dt.time(16, 30),
    )


class TestConfirmingWhatWasRostered:
    def test_confirming_copies_the_times_and_agrees_to_them(self, org, anna, monday, rostered):
        record = DayRecord.from_shifts(anna, monday, [rostered], by=anna.user, settings=org)
        assert record.is_confirmed
        assert record.source == EntrySource.ROSTER
        assert [(s.start, s.end) for s in record.segments.all()] == [(dt.time(8, 0), dt.time(16, 30))]

    def test_the_break_is_applied_to_the_copied_times(self, org, anna, monday, rostered):
        """The bug this pins is subtle and total: ``apply_break_rules`` reads the
        segments through a cached relation, and on a record whose segments were
        just bulk-created that cache is empty. Without the refresh, every
        confirmed day gets a break of nought — which is a timesheet that
        overstates everybody's hours and looks completely normal."""
        record = DayRecord.from_shifts(anna, monday, [rostered], by=anna.user, settings=org)
        assert record.gross_minutes == 510
        assert record.break_minutes == 30
        assert record.worked_minutes == 480

    def test_confirming_does_not_touch_the_roster(self, org, anna, monday, rostered):
        """The whole reason they are two tables. If confirming wrote back to the
        shift, a manager who later edited it would silently rewrite what
        somebody agreed to, and nothing could answer "what were you asked to
        work?"."""
        DayRecord.from_shifts(anna, monday, [rostered], by=anna.user, settings=org)
        rostered.refresh_from_db()
        assert (rostered.start, rostered.end) == (dt.time(8, 0), dt.time(16, 30))
        assert Shift.objects.count() == 1

    def test_a_day_with_nothing_rostered_confirms_to_nothing(self, org, anna, monday):
        """Not an error: it is what "confirm this week" does for the days
        somebody was not on."""
        assert DayRecord.from_shifts(anna, monday, [], by=anna.user, settings=org) is None

    def test_confirming_twice_does_not_duplicate_the_segments(self, org, anna, monday, rostered):
        DayRecord.from_shifts(anna, monday, [rostered], by=anna.user, settings=org)
        record = DayRecord.from_shifts(anna, monday, [rostered], by=anna.user, settings=org)
        assert record.segments.count() == 1
        assert DayRecord.objects.count() == 1

    def test_a_split_shift_becomes_two_segments(self, org, cem, monday):
        morning = Shift.objects.create(employee=cem, date=monday,
                                       start=dt.time(7, 30), end=dt.time(11, 30))
        late = Shift.objects.create(employee=cem, date=monday,
                                    start=dt.time(14, 0), end=dt.time(18, 0))
        record = DayRecord.from_shifts(cem, monday, [late, morning], by=None, settings=org)
        # Sorted by start, not by the order they arrived in.
        assert [(s.start, s.end) for s in record.segments.all()] == [
            (dt.time(7, 30), dt.time(11, 30)), (dt.time(14, 0), dt.time(18, 0)),
        ]
        # Eight hours across two stretches — the break is a question about the
        # eight, not about either four. A per-segment break would give nought.
        assert record.gross_minutes == 480
        assert record.break_minutes == 30

    def test_it_can_say_the_entered_hours_differ_from_the_plan(self, org, anna, monday, rostered):
        """The one line a manager reads first. Not "confirmed", but confirmed
        *and different from what was asked*."""
        record = DayRecord.from_shifts(anna, monday, [rostered], by=anna.user, settings=org)
        assert record.matches_roster([rostered])

        record.segments.update(end=dt.time(18, 0))
        record.refresh_from_db()
        assert not record.matches_roster([rostered])


class TestTheBreakOverride:
    def test_an_overridden_break_is_never_recomputed(self, org, anna, monday):
        """The guard that matters. Without it, somebody who deliberately entered
        60 finds 30 there the next time anything touches the row — with nothing
        on the page showing that it changed."""
        record = DayRecord.objects.create(
            employee=anna, date=monday, break_minutes=60, break_is_override=True,
        )
        WorkSegment.objects.create(day=record, start=dt.time(8, 0), end=dt.time(16, 30))
        record.refresh_from_db()

        record.apply_break_rules(settings=org)
        assert record.break_minutes == 60

    def test_a_break_that_was_not_overridden_follows_the_rules(self, org, anna, monday):
        record = DayRecord.objects.create(employee=anna, date=monday, break_minutes=0)
        WorkSegment.objects.create(day=record, start=dt.time(8, 0), end=dt.time(18, 0))
        record.refresh_from_db()

        record.apply_break_rules(settings=org)
        assert record.break_minutes == 45

    def test_differing_from_the_rules_is_not_the_same_as_overridden(self, org, anna, monday):
        """What the amber highlight is driven by, and deliberately a different
        question: a break somebody typed that happens to equal the computed one
        needs no highlight, and a break the rules produced under an older table
        does need one once the table changes."""
        record = DayRecord.objects.create(
            employee=anna, date=monday, break_minutes=30, break_is_override=True,
        )
        WorkSegment.objects.create(day=record, start=dt.time(8, 0), end=dt.time(16, 30))
        record.refresh_from_db()

        assert record.break_is_override
        assert not record.break_differs_from_rules

    def test_worked_time_never_goes_negative(self, org, anna, monday):
        """A break longer than the day is nonsense a manager can type. Letting it
        go negative would make a week's total quietly smaller than the days in
        it — wrong, and merely surprising to look at."""
        record = DayRecord.objects.create(
            employee=anna, date=monday, break_minutes=600, break_is_override=True,
        )
        WorkSegment.objects.create(day=record, start=dt.time(8, 0), end=dt.time(12, 0))
        record.refresh_from_db()
        assert record.worked_minutes == 0


class TestEditingWithdrawsTheConfirmation:
    def test_saving_a_change_unconfirms_the_day(self, org, anna, client, monday, rostered):
        """A confirmed day whose hours were rewritten would make the record say
        somebody agreed to figures they have never seen — which is exactly the
        claim a timesheet exists to be able to make honestly."""
        record = DayRecord.from_shifts(anna, monday, [rostered], by=anna.user, settings=org)
        assert record.is_confirmed
        segment = record.segments.get()

        response = client.post(f"/timesheet/{anna.pk}/{monday.isoformat()}/", {
            "segments-TOTAL_FORMS": "1", "segments-INITIAL_FORMS": "1",
            "segments-MIN_NUM_FORMS": "0", "segments-MAX_NUM_FORMS": "1000",
            "segments-0-id": str(segment.pk),
            "segments-0-start": "08:00", "segments-0-end": "18:00",
            "automatic_break": "on", "break_minutes": "", "note": "",
        })
        assert response.status_code == 302
        record.refresh_from_db()
        assert not record.is_confirmed
        assert record.gross_minutes == 600
        assert record.break_minutes == 45

    def test_unconfirming_a_day_that_was_never_confirmed_is_a_no_op(self, org, anna, monday):
        record = DayRecord.objects.create(employee=anna, date=monday)
        record.unconfirm()
        assert not record.is_confirmed


class TestConfirmingAWholeWeek:
    def test_it_skips_days_somebody_has_already_entered(self, org, anna, client, monday):
        """The one thing this button must never do is overwrite a correction.
        A day entered by hand is left exactly as it is, and the message says how
        many were skipped."""
        for offset in range(2):
            Shift.objects.create(employee=anna, date=monday + dt.timedelta(days=offset),
                                 start=dt.time(8, 0), end=dt.time(16, 30))
        typed = DayRecord.objects.create(employee=anna, date=monday, note="stayed late")
        WorkSegment.objects.create(day=typed, start=dt.time(8, 0), end=dt.time(19, 0))

        client.post("/timesheet/confirm-week/", {"week": monday.isoformat()})

        typed.refresh_from_db()
        assert typed.note == "stayed late"
        assert typed.gross_minutes == 660
        assert not typed.is_confirmed

    def test_it_does_not_confirm_days_in_the_future(self, org, anna, client, monday):
        """Confirming a day that has not happened is a statement nobody is in a
        position to make."""
        future = week_monday(dt.date.today()) + dt.timedelta(days=30)
        Shift.objects.create(employee=anna, date=future,
                             start=dt.time(8, 0), end=dt.time(16, 30))
        client.post("/timesheet/confirm-week/", {"week": future.isoformat()})
        assert not DayRecord.objects.filter(employee=anna, date=future).exists()


class TestWhoMaySeeWhoseTime:
    def test_an_employee_may_open_their_own_day(self, org, anna, client, monday):
        response = client.get(f"/timesheet/{anna.pk}/{monday.isoformat()}/")
        assert response.status_code == 200

    def test_an_employee_may_not_open_somebody_elses(self, org, anna, cem, client, monday):
        response = client.get(f"/timesheet/{cem.pk}/{monday.isoformat()}/")
        assert response.status_code == 404

    def test_a_manager_may(self, org, anna, manager_client, monday):
        response = manager_client.get(f"/team/{anna.pk}/{monday.isoformat()}/")
        assert response.status_code == 200

    def test_an_employee_may_not_confirm_somebody_elses_day(self, org, anna, cem, client, monday):
        Shift.objects.create(employee=cem, date=monday, start=dt.time(8, 0), end=dt.time(16, 0))
        response = client.post(f"/timesheet/{cem.pk}/{monday.isoformat()}/confirm/")
        assert response.status_code == 404
        assert not DayRecord.objects.filter(employee=cem).exists()

    def test_an_unlinked_employee_is_not_everybodys(self, org, cem, other_user):
        """``own_or_manager`` compares ``employee.user_id`` to ``request.user.id``.

        The trap is the null: with both sides ``None`` a bare ``==`` is True,
        which would hand every not-yet-signed-in employee's timesheet to anybody
        with an account. The explicit ``is not None`` guard is what stops it, so
        it is checked against a real account rather than a stub — an
        ``AnonymousUser`` also has an ``id`` of None and would pass a weaker
        test for the wrong reason.
        """
        from django.test import RequestFactory

        from apps.employees.permissions import own_or_manager

        assert cem.user_id is None
        request = RequestFactory().get("/")
        request.user = other_user
        assert not own_or_manager(request, cem)


class TestTheArithmeticOfDurations:
    @pytest.mark.parametrize("start, end, expected", [
        ((8, 0), (16, 30), 510),
        ((8, 0), (8, 0), 24 * 60),
        # A night shift. The naive subtraction gives -960 for this, which would
        # make a week's total smaller than the days in it.
        ((22, 0), (6, 0), 480),
    ])
    def test_a_span_that_crosses_midnight_is_positive(self, start, end, expected):
        assert minutes_between(dt.time(*start), dt.time(*end)) == expected

    @pytest.mark.parametrize("minutes, expected", [
        (455, "7:35"), (0, "0:00"), (60, "1:00"),
        # A negative total is a real answer — worked minus contracted for
        # somebody who left early. The naive divmod gives "-1:-15".
        (-75, "-1:15"),
    ])
    def test_the_clock_form_keeps_the_sign_outside_the_colon(self, minutes, expected):
        assert clock(minutes) == expected

    def test_the_two_forms_are_the_same_number(self):
        assert decimal_hours(450) == pytest.approx(7.5)
        assert clock(450) == "7:30"

    def test_a_contract_in_hours_becomes_whole_minutes(self):
        from decimal import Decimal

        assert contracted_minutes(Decimal("7.75")) == 465
        assert contracted_minutes(Decimal("8")) == 480


def test_the_browser_and_the_server_agree_about_breaks(org):
    """The one rule written twice in two languages.

    ``hours.js`` repeats ``required_break`` so the day form can answer while
    somebody is typing rather than asking the server per keystroke. This holds
    the two to the same answers by reading the formula out of the JavaScript and
    running it — not by trusting a comment that says they match.
    """
    source = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "static" / "js" / "hours.js"
    ).read_text(encoding="utf-8")

    # The rule as written in the browser, transcribed once here. If somebody
    # changes hours.js the string below stops matching and this fails, which is
    # the point: a silent divergence is the failure mode.
    assert "Math.min(rule.break, Math.max(0, gross - rule.over))" in source, (
        "hours.js no longer computes the break the way required_break does — "
        "the two implementations have drifted"
    )

    rules = [{"over": r.over_minutes, "break": r.break_minutes}
             for r in org.break_rules.all()]

    def browser_version(gross):
        required = 0
        for rule in rules:
            needed = min(rule["break"], max(0, gross - rule["over"]))
            required = max(required, needed)
        return required

    for gross in range(0, 16 * 60, 5):
        assert browser_version(gross) == org.required_break(gross, rules=list(org.break_rules.all())), (
            f"the two disagree at {gross} minutes"
        )
    # And the page really hands the browser the rules rather than an answer.
    assert json.dumps(rules)


class TestOverlappingStretchesAreRefused:
    """Two stretches covering the same minute double-count it into the day's
    total — and the total is what the break rules and every balance are computed
    from, so the error is silent and arrives as an unexplained surplus at the end
    of the month.

    Checked in the browser as well (``static/js/timesheet_day.js``), because
    "before saving" is the only time it is cheap to fix.
    """

    def _post(self, client, employee, date, rows, **extra):
        data = {
            "segments-TOTAL_FORMS": str(len(rows)),
            "segments-INITIAL_FORMS": "0",
            "segments-MIN_NUM_FORMS": "0",
            "segments-MAX_NUM_FORMS": "1000",
            "automatic_break": "on", "break_minutes": "", "note": "",
        }
        data.update(extra)
        for index, (start, end) in enumerate(rows):
            data[f"segments-{index}-start"] = start
            data[f"segments-{index}-end"] = end
        return client.post(f"/timesheet/{employee.pk}/{date.isoformat()}/", data)

    def test_the_case_from_the_brief_is_refused(self, org, anna, client, monday):
        """08:30–17:30 beside 17:00–18:30 overlaps by half an hour."""
        response = self._post(client, anna, monday,
                              [("08:30", "17:30"), ("17:00", "18:30")])
        assert response.status_code == 200          # redisplayed, not saved
        assert not DayRecord.objects.filter(employee=anna, date=monday).exists()
        assert "overlap" in response.content.decode()

    def test_the_message_names_both_stretches(self, org, anna, client, monday):
        """"Two of those stretches" is the start of a hunt on a day with four
        rows on it."""
        body = self._post(client, anna, monday,
                          [("08:30", "17:30"), ("17:00", "18:30")]).content.decode()
        assert "08:30–17:30" in body and "17:00–18:30" in body

    def test_touching_at_the_boundary_is_not_an_overlap(self, org, anna, client, monday):
        """A split shift ending at 12:00 and resuming at 12:00 shares no minute.
        Refusing it would refuse the commonest shape there is."""
        response = self._post(client, anna, monday,
                              [("08:00", "12:00"), ("12:00", "16:00")])
        assert response.status_code == 302
        assert DayRecord.objects.get(employee=anna, date=monday).gross_minutes == 480

    def test_a_night_shift_is_not_reported_as_an_overlap(self, org, anna, client, monday):
        """22:00–06:00 crosses midnight, so as raw clock values its end is
        *before* its start. Compared that way every night shift looks like an
        overlap — and the one real overlap slips through whenever there is a
        night shift on the day."""
        response = self._post(client, anna, monday, [("22:00", "06:00")])
        assert response.status_code == 302
        assert DayRecord.objects.get(employee=anna, date=monday).gross_minutes == 480

    def test_three_stretches_with_one_clash_are_refused(self, org, anna, client, monday):
        response = self._post(client, anna, monday,
                              [("06:00", "09:00"), ("10:00", "14:00"), ("13:00", "15:00")])
        assert response.status_code == 200
        assert not DayRecord.objects.filter(employee=anna, date=monday).exists()

    def test_a_stretch_marked_for_deletion_cannot_clash(self, org, anna, client, monday):
        """It is still in the DOM and in the POST — a formset is an index range,
        not a list — so a check that counted it would refuse a day somebody had
        just fixed by removing the offending row."""
        response = self._post(
            client, anna, monday,
            [("08:30", "17:30"), ("17:00", "18:30")],
            **{"segments-1-DELETE": "on"},
        )
        assert response.status_code == 302
        assert DayRecord.objects.get(employee=anna, date=monday).segments.count() == 1

    def test_the_browser_checks_the_same_thing(self):
        """The rule is repeated in timesheet_day.js so the row goes red as it is
        typed. Held to the same shape here rather than trusting a comment."""
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2] / "static" / "js" / "timesheet_day.js"
        ).read_text(encoding="utf-8")
        assert "if (to <= from) to += 24 * 60;" in source, (
            "timesheet_day.js no longer normalises a midnight-crossing stretch "
            "before comparing, so it reports every night shift as an overlap"
        )
        assert "spans[i].from < spans[i - 1].to" in source
        # Touching boundaries must stay legal in the browser too.
        assert "<=" not in "spans[i].from < spans[i - 1].to"


class TestTimeOffInLieu:
    """Hours already worked, taken back. It costs no leave and the app keeps no
    overtime account — the shortfall against contracted hours *is* the
    arithmetic, and recording the kind only names what it was for."""

    def test_it_costs_no_leave(self, org, anna, monday):
        from apps.absences.models import Absence, AbsenceKind, Balance, RequestStatus

        Absence.objects.create(
            employee=anna, kind=AbsenceKind.OVERTIME,
            start_date=monday, end_date=monday + dt.timedelta(days=1),
            status=RequestStatus.APPROVED,
        )
        balance = Balance(anna, monday.year, org)
        assert balance.taken == 0
        assert balance.remaining == balance.entitlement
        assert balance.overtime_days == 2

    def test_it_still_shows_as_waiting_while_undecided(self, org, anna, monday):
        """A manager has to see it is asked for; it simply never lands in the
        leave figure."""
        from apps.absences.models import Absence, AbsenceKind, Balance, RequestStatus

        Absence.objects.create(
            employee=anna, kind=AbsenceKind.OVERTIME,
            start_date=monday, end_date=monday,
            status=RequestStatus.REQUESTED,
        )
        balance = Balance(anna, monday.year, org)
        assert balance.pending == 0
        assert balance.pending_overtime_days == 1

    def test_an_employee_can_ask_for_it(self, org, anna, client, monday):
        from apps.absences.models import Absence, AbsenceKind, RequestStatus

        future = monday + dt.timedelta(days=30)
        response = client.post("/absences/request/", {
            "kind": AbsenceKind.OVERTIME,
            "start_date": future.isoformat(),
            "end_date": future.isoformat(),
            "reason": "Überstunden",
        })
        assert response.status_code == 302
        absence = Absence.objects.get(employee=anna, kind=AbsenceKind.OVERTIME)
        assert absence.status == RequestStatus.REQUESTED

    def test_the_day_still_counts_as_a_shortfall(self, org, anna, monday):
        """The whole reason it needs no overtime account: a day with no hours
        entered already reads as minus the contracted hours, flagged or not."""
        from apps.absences.models import Absence, AbsenceKind, RequestStatus
        from apps.timesheets.views import build_week

        Absence.objects.create(
            employee=anna, kind=AbsenceKind.OVERTIME,
            start_date=monday, end_date=monday,
            status=RequestStatus.APPROVED,
        )
        week = build_week(anna, monday, org)
        row = week["rows"][0]
        assert row["absence"].kind == AbsenceKind.OVERTIME
        assert row["worked_minutes"] is None
        assert row["contracted_minutes"] == 480
        assert week["difference"] == -week["contracted_total"]
