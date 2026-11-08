"""§3 and §5 ArbZG: the two limits, and the one thing they must never do.

The most important test in this file is the last one — that an unlawful day
still **saves**. Everything else here is arithmetic; that one is the design.
Software which refused an eleven-hour day would not prevent the eleventh hour,
because somebody worked it either way; it would only destroy the record that it
happened, which is the opposite of what §16 ArbZG asks the employer to keep.

The rest divides in two. The §3 cases pin the boundary in both directions — a
day *at* eight hours is not over eight, and a day *at* ten is not over ten — and
the two levels, because "over eight" and "over ten" are different statements and
collapsing them into one would either cry wolf on every busy Tuesday or say
nothing at all about the day that actually breaks the ceiling.

The §5 cases pin the arithmetic that only exists because a day is a column of
stretches rather than a single pair: the rest is measured from the *last*
clock-out to the *next* first clock-in, and either of those may be on a date the
row is not filed under.
"""

import datetime as dt

import pytest
from django.urls import reverse

from apps.timesheets import limits
from apps.timesheets.models import DayRecord, WorkSegment
from apps.timesheets.views import build_month
from apps.timesheets.zones import zone_for


def _record(employee, date, spans, **kwargs):
    """One day of one person, with its stretches in the order given.

    ``apply_break_rules`` after a refresh, the same shape ``test_month`` uses:
    the break relation is cached, and a record whose segments were just created
    answers ``shape`` from an empty cache unless it is refreshed first.
    """
    record = DayRecord.objects.create(employee=employee, date=date, **kwargs)
    for index, (start, end) in enumerate(spans):
        WorkSegment.objects.create(
            day=record, position=index,
            start=dt.time(*start), end=dt.time(*end) if end else None,
        )
    record.refresh_from_db()
    record.apply_break_rules()
    record.save()
    return record


def _flags(record, previous=None, employee=None):
    employee = employee or record.employee
    return limits.for_day(
        record, previous, zone_for(employee), record.worked_minutes,
    )


def _codes(flags):
    return [flag["code"] for flag in flags]


# --------------------------------------------------------------------------
# §3 — how long a day may be
# --------------------------------------------------------------------------

class TestTheLengthOfADay:
    """Eight hours, ten by exception. Two thresholds, two different sentences."""

    def test_an_ordinary_day_says_nothing(self, anna, org):
        # 08:00–16:30 is eight and a half at work, less thirty minutes of break:
        # exactly eight hours worked, which is the working day §3 s.1 sets.
        record = _record(anna, dt.date(2025, 9, 1), [((8, 0), (16, 30))])
        assert record.worked_minutes == limits.ORDINARY_DAY_MINUTES
        assert _flags(record) == []

    def test_eight_hours_exactly_is_not_over_eight(self, anna, org):
        """The boundary, in the direction that matters.

        ``>`` and not ``>=``: §3 s.1 is "darf acht Stunden nicht überschreiten",
        and a marking on every full-time Tuesday in Germany is a marking nobody
        would read by Thursday.
        """
        record = _record(anna, dt.date(2025, 9, 1), [((8, 0), (16, 30))])
        assert _flags(record) == []

    def test_a_nine_hour_day_is_a_caution_and_not_a_breach(self, anna, org):
        """Lawful *if* a shorter day pays it back, and the app cannot say whether
        one did — so it must not claim the day was unlawful."""
        record = _record(anna, dt.date(2025, 9, 1), [((8, 0), (17, 30))])
        assert record.worked_minutes == 9 * 60
        flags = _flags(record)
        assert _codes(flags) == ["over-ordinary"]
        assert limits.worst(flags) == limits.CAUTION

    def test_ten_hours_exactly_is_still_only_a_caution(self, anna, org):
        """§3 s.2 permits ten. The ceiling is what is *over* ten."""
        # 07:00–17:45 is 10h45 at work, less the 45-minute break the second tier
        # requires over nine hours: ten hours worked.
        record = _record(anna, dt.date(2025, 9, 1), [((7, 0), (17, 45))])
        assert record.worked_minutes == limits.MAXIMUM_DAY_MINUTES
        assert _codes(_flags(record)) == ["over-ordinary"]

    def test_over_ten_hours_is_a_breach(self, anna, org):
        record = _record(anna, dt.date(2025, 9, 1), [((7, 0), (18, 30))])
        assert record.worked_minutes > limits.MAXIMUM_DAY_MINUTES
        flags = _flags(record)
        assert _codes(flags) == ["over-maximum"]
        assert limits.worst(flags) == limits.BREACH

    def test_the_two_levels_are_never_both_reported(self, anna, org):
        """One statement per day about its length. A day over ten is also over
        eight, and saying both would be the page arguing with itself."""
        record = _record(anna, dt.date(2025, 9, 1), [((7, 0), (19, 0))])
        assert len(_flags(record)) == 1

    def test_a_day_still_running_is_not_judged_on_its_length(self, anna, org):
        """A running stretch is worth nothing until it has an end, so an
        eleven-hour shift in progress reads as nought — and flagging nought
        would be flagging the wrong thing at the wrong moment."""
        record = _record(anna, dt.date(2025, 9, 1), [((6, 0), None)])
        assert record.is_running
        assert _flags(record) == []

    def test_a_correction_counts_towards_the_limit(self, anna, org):
        """§3 is about working time, and a correction is working time somebody
        did not clock. A day pushed over ten by hand is over ten."""
        record = _record(
            anna, dt.date(2025, 9, 1), [((7, 0), (17, 45))],
            correction_minutes=60, correction_reason="drove to the second site",
        )
        assert _codes(_flags(record)) == ["over-maximum"]


# --------------------------------------------------------------------------
# §5 — the rest between two days
# --------------------------------------------------------------------------

class TestTheRestBetweenDays:

    def test_an_ordinary_night_is_fine(self, anna, org):
        first = _record(anna, dt.date(2025, 9, 1), [((8, 0), (16, 30))])
        second = _record(anna, dt.date(2025, 9, 2), [((8, 0), (16, 30))])
        assert limits.rest_minutes(first, second, zone_for(anna)) == 15 * 60 + 30
        assert _flags(second, first) == []

    def test_eleven_hours_exactly_is_enough(self, anna, org):
        """The boundary. §5(1) is "mindestens elf Stunden", so eleven is met."""
        first = _record(anna, dt.date(2025, 9, 1), [((12, 0), (21, 0))])
        second = _record(anna, dt.date(2025, 9, 2), [((8, 0), (16, 0))])
        assert limits.rest_minutes(first, second, zone_for(anna)) == limits.MINIMUM_REST_MINUTES
        assert _codes(_flags(second, first)) == []

    def test_a_short_night_is_a_breach(self, anna, org):
        first = _record(anna, dt.date(2025, 9, 1), [((12, 0), (22, 0))])
        second = _record(anna, dt.date(2025, 9, 2), [((7, 0), (15, 0))])
        flags = _flags(second, first)
        assert _codes(flags) == ["short-rest"]
        assert limits.worst(flags) == limits.BREACH

    def test_the_rest_is_measured_from_the_last_stretch_of_the_day(self, anna, org):
        """A split shift. The morning ending at eleven is not what the rest runs
        from — the evening one is, and reading the first would report fourteen
        hours' rest on a night that was six."""
        first = _record(anna, dt.date(2025, 9, 1), [((8, 0), (11, 0)), ((18, 0), (23, 0))])
        second = _record(anna, dt.date(2025, 9, 2), [((5, 0), (13, 0))])
        assert limits.rest_minutes(first, second, zone_for(anna)) == 6 * 60
        assert _codes(_flags(second, first)) == ["short-rest"]

    def test_a_night_shift_ends_on_the_following_date(self, anna, org):
        """22:00–06:00 is filed under the first date and finishes on the second,
        so the rest before an 08:00 start is two hours and not twenty-six."""
        first = _record(anna, dt.date(2025, 9, 1), [((22, 0), (6, 0))])
        second = _record(anna, dt.date(2025, 9, 2), [((8, 0), (16, 0))])
        assert limits.rest_minutes(first, second, zone_for(anna)) == 2 * 60
        assert _codes(_flags(second, first)) == ["short-rest"]

    def test_a_night_shift_in_two_stretches_carries_the_date_forward(self, anna, org):
        """The case a per-segment ``end <= start`` test gets wrong.

        22:00–02:00 then 03:00–06:00: the second stretch's own readings are in
        clock order, so nothing about *it* says it is on the next date — only
        the fact that it begins earlier than the previous one ended does. Read
        naively, the day's last clock-out lands twenty hours before its first
        clock-in and the rest comes out as a day and a half.
        """
        first = _record(anna, dt.date(2025, 9, 1), [((22, 0), (2, 0)), ((3, 0), (6, 0))])
        second = _record(anna, dt.date(2025, 9, 2), [((9, 0), (17, 0))])
        assert limits.rest_minutes(first, second, zone_for(anna)) == 3 * 60

    def test_no_previous_record_is_no_answer_rather_than_a_breach(self, anna, org):
        """A date with no row is a day nobody has answered for. Inventing a rest
        for it — in either direction — would be the app agreeing with a record
        that does not exist."""
        second = _record(anna, dt.date(2025, 9, 2), [((7, 0), (15, 0))])
        assert limits.rest_minutes(None, second, zone_for(anna)) is None
        assert _flags(second, None) == []

    def test_a_previous_day_still_running_has_no_clock_out(self, anna, org):
        first = _record(anna, dt.date(2025, 9, 1), [((22, 0), None)])
        second = _record(anna, dt.date(2025, 9, 2), [((7, 0), (15, 0))])
        assert limits.rest_minutes(first, second, zone_for(anna)) is None

    def test_the_rest_is_still_checked_on_a_day_that_is_running(self, anna, org):
        """Its *length* is unknowable while it runs; when it began is not, and
        that is the whole of the §5 question."""
        first = _record(anna, dt.date(2025, 9, 1), [((12, 0), (22, 0))])
        second = _record(anna, dt.date(2025, 9, 2), [((6, 0), None)])
        assert _codes(_flags(second, first)) == ["short-rest"]

    def test_the_rest_crosses_the_night_the_clocks_go_back(self, anna, org):
        """26 October 2025, when Europe/Berlin repeats an hour.

        Somebody who finished at 22:00 and started again at 08:00 was off for
        *eleven* real hours, not ten — and §5 is a rule about how long they
        actually rested. The wall-clock subtraction says ten and would report a
        breach that did not happen.
        """
        first = _record(anna, dt.date(2025, 10, 25), [((14, 0), (22, 0))])
        second = _record(anna, dt.date(2025, 10, 26), [((8, 0), (16, 0))])
        assert limits.rest_minutes(first, second, zone_for(anna)) == 11 * 60
        assert _flags(second, first) == []

    def test_the_same_night_in_march_is_an_hour_shorter(self, anna, org):
        """29–30 March 2025, when the hour is skipped. The mirror of the case
        above, and the one where the wall clock is generous rather than harsh."""
        first = _record(anna, dt.date(2025, 3, 29), [((14, 0), (22, 0))])
        second = _record(anna, dt.date(2025, 3, 30), [((9, 0), (17, 0))])
        assert limits.rest_minutes(first, second, zone_for(anna)) == 10 * 60
        assert _codes(_flags(second, first)) == ["short-rest"]


# --------------------------------------------------------------------------
# What the month does with them
# --------------------------------------------------------------------------

class TestTheMonth:

    def test_the_first_of_the_month_sees_the_last_of_the_month_before(self, anna, org):
        """The reason ``_facts_for`` fetches one day wider than its window.

        A rest period is a question about the gap *between* two days, so the
        first row of a month cannot be answered from inside that month — and a
        month that silently could not answer it would be a month with a hole in
        exactly the place a fortnight of night shifts lands.
        """
        _record(anna, dt.date(2025, 8, 31), [((14, 0), (23, 0))])
        _record(anna, dt.date(2025, 9, 1), [((6, 0), (14, 0))])
        month = build_month(anna, dt.date(2025, 9, 1))
        assert month["rows"][0]["limit_level"] == limits.BREACH
        assert "§5" in month["rows"][0]["limit_note"]

    def test_the_month_counts_both_levels_separately(self, anna, org):
        _record(anna, dt.date(2025, 9, 1), [((8, 0), (17, 30))])   # nine hours
        _record(anna, dt.date(2025, 9, 3), [((7, 0), (18, 30))])   # over ten
        month = build_month(anna, dt.date(2025, 9, 1))
        assert month["limit_cautions"] == 1
        assert month["limit_breaches"] == 1

    def test_an_ordinary_month_counts_nothing(self, anna, org):
        for day in range(1, 6):
            _record(anna, dt.date(2025, 9, day), [((8, 0), (16, 30))])
        month = build_month(anna, dt.date(2025, 9, 1))
        assert month["limit_breaches"] == 0
        assert month["limit_cautions"] == 0
        assert all(row["limit_level"] == "" for row in month["rows"])

    def test_a_day_with_no_record_carries_no_flag(self, anna, org):
        month = build_month(anna, dt.date(2025, 9, 1))
        assert all(row["limit_flags"] == [] for row in month["rows"])


# --------------------------------------------------------------------------
# The one that is the design
# --------------------------------------------------------------------------

class TestAnUnlawfulDayIsStillRecorded:
    """**Flagged, never refused.**

    §16 ArbZG requires a record of the time actually worked. Refusing to save a
    twelve-hour day does not stop the twelfth hour — somebody worked it either
    way — it removes the only evidence that they did, and leaves the employer
    with a tidy timesheet and no answer. Every one of these would still pass if
    the flags were deleted; none would pass if a flag ever became a refusal.
    """

    def test_a_twelve_hour_day_saves(self, anna, org):
        record = _record(anna, dt.date(2025, 9, 1), [((6, 0), (18, 45))])
        record.refresh_from_db()
        assert record.worked_minutes == 12 * 60
        assert _codes(_flags(record)) == ["over-maximum"]

    def test_a_two_hour_rest_saves_on_both_days(self, anna, org):
        first = _record(anna, dt.date(2025, 9, 1), [((14, 0), (23, 0))])
        second = _record(anna, dt.date(2025, 9, 2), [((1, 0), (9, 0))])
        assert DayRecord.objects.filter(employee=anna).count() == 2
        assert _codes(_flags(second, first)) == ["short-rest"]

    def test_the_page_still_renders_a_month_full_of_them(self, anna, org, client):
        for day in range(1, 6):
            _record(anna, dt.date(2025, 9, day), [((6, 0), (19, 0))])
        response = client.get(reverse("timesheets:mine"), {"month": "2025-09"})
        assert response.status_code == 200


@pytest.mark.parametrize("name", ["ORDINARY_DAY_MINUTES", "MAXIMUM_DAY_MINUTES",
                                  "MINIMUM_REST_MINUTES"])
def test_the_thresholds_are_the_statute(name):
    """Not settings, and this is the assertion that says so.

    The break table is configurable because §4 sets a floor an employer may be
    generous about. These are ceilings: a house that could raise them would be
    configuring its way out of the law rather than into it.
    """
    assert getattr(limits, name) == {
        "ORDINARY_DAY_MINUTES": 8 * 60,
        "MAXIMUM_DAY_MINUTES": 10 * 60,
        "MINIMUM_REST_MINUTES": 11 * 60,
    }[name]
