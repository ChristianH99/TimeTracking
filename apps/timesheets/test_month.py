"""The monthly timesheet: the ten columns, and saving a month in one POST.

The value here is concentrated in the arithmetic the page prints, because every
one of those figures is a number somebody is paid against and every one of them
still renders when it is wrong. The three that are checked hardest are the ones
with two implementations behind them:

* the **saldo**, which must be actual minus supposed and not the other way round
  — the sign disagreeing with ``hours_balance`` would put +0:30 on one page and
  -0:30 on another about the same Tuesday;
* the **running column**, which must reach exactly what ``hours_balance`` gives
  for the last day of the month, because they are two readings of one thing;
* the **correction**, which is applied *after* the break — the other order
  pushes a day over a break threshold and deducts a break nobody took.
"""

import datetime as dt
import pathlib

import pytest
from django.utils import translation
from django.core.exceptions import ValidationError

from apps.absences.models import Absence, AbsenceKind, RequestStatus
from apps.roster.models import Shift
from apps.timesheets import bookings
from apps.timesheets.balance import hours_balance
from apps.timesheets.models import DayRecord, WorkSegment
from apps.timesheets.views import (
    build_month, month_end, month_shift, month_start, status_value,
)


@pytest.fixture
def september(anna):
    """A month with no public holiday in Germany and no clock change in it.

    Chosen the way ``conftest``'s ``monday`` is: a test that counts working days
    must not be quietly changed by the calendar it happens to run on, and
    September is the only long month with neither a holiday nor a DST boundary.
    """
    return dt.date(2025, 9, 1)


def _record(employee, date, spans, **kwargs):
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


# --------------------------------------------------------------------------
# The calendar arithmetic
# --------------------------------------------------------------------------

class TestTheMonthItself:
    """``month_shift`` is three lines and every one of them is an off-by-one
    waiting to happen — the modulo especially, which is why December and January
    are named rather than left to a round trip."""

    def test_a_month_runs_from_the_first_to_the_last(self):
        assert month_start(dt.date(2025, 9, 17)) == dt.date(2025, 9, 1)
        assert month_end(dt.date(2025, 9, 1)) == dt.date(2025, 9, 30)
        assert month_end(dt.date(2025, 2, 1)) == dt.date(2025, 2, 28)
        assert month_end(dt.date(2024, 2, 1)) == dt.date(2024, 2, 29)

    def test_it_steps_across_the_turn_of_the_year(self):
        assert month_shift(dt.date(2025, 12, 1), 1) == dt.date(2026, 1, 1)
        assert month_shift(dt.date(2025, 1, 1), -1) == dt.date(2024, 12, 1)
        assert month_shift(dt.date(2025, 9, 1), 12) == dt.date(2026, 9, 1)
        assert month_shift(dt.date(2025, 9, 1), -12) == dt.date(2024, 9, 1)

    def test_a_month_has_a_row_for_every_date(self, org, anna, september):
        month = build_month(anna, september)
        assert len(month["rows"]) == 30
        assert month["rows"][0]["date"] == september
        assert month["rows"][-1]["date"] == dt.date(2025, 9, 30)


# --------------------------------------------------------------------------
# The columns
# --------------------------------------------------------------------------

class TestTheColumns:
    def test_a_day_adds_up_the_way_the_page_says_it_does(self, org, anna, september):
        """Bookings, less the break, plus the correction — in that order."""
        _record(anna, dt.date(2025, 9, 1), [((8, 0), (17, 0))])
        row = build_month(anna, september)["rows"][0]

        assert row["gross_minutes"] == 540          # 08:00–17:00, in one stretch
        # Nine hours exactly is not *over* nine, so the first tier is all that
        # applies — and nothing was taken, so all thirty of it comes off.
        assert row["break_minutes"] == 30
        assert row["correction_minutes"] == 0
        assert row["counted_minutes"] == 510
        assert row["contracted_minutes"] == 480     # anna's eight-hour day
        assert row["saldo"] == 30

    def test_the_correction_is_added_after_the_break(self, org, anna, september):
        """The order is the whole of it.

        A day of 5h50 with a ten-minute correction is *not* a six-hour day for
        the break rules: the correction is time nobody stood through, and adding
        it first crosses the six-hour tier and deducts a break the person never
        took — which costs them thirty minutes of pay for having been honest
        about ten.
        """
        record = _record(anna, dt.date(2025, 9, 1), [((8, 0), (13, 50))])
        assert record.break_minutes == 0            # 5h50 is under every tier

        record.correction_minutes = 10
        record.correction_reason = "drove to the other site"
        record.save()
        record.refresh_from_db()
        record.apply_break_rules()

        assert record.break_minutes == 0, "the correction moved a break threshold"
        assert record.net_minutes == 350
        assert record.worked_minutes == 360

    def test_a_break_taken_between_the_stretches_is_not_deducted_again(
        self, org, anna, september,
    ):
        """The case this was reported for.

        09:30–15:30 and 16:00–18:00 is eight hours at work with thirty minutes
        off in the middle — precisely what §4 ArbZG asks of an eight-hour day.
        Deducting another thirty charged the person twice for a break they had
        taken, and made an honest record of a lawful day come out half an hour
        short.
        """
        record = _record(anna, september, [((9, 30), (15, 30)), ((16, 0), (18, 0))])
        assert record.gross_minutes == 480
        assert record.break_taken_minutes == 30
        assert record.break_minutes == 0
        assert record.worked_minutes == 480

        row = build_month(anna, september)["rows"][0]
        assert row["counted_minutes"] == 480
        assert row["saldo"] == 0

    def test_a_day_with_no_break_at_all_still_gets_one(self, org, anna, september):
        """The other side of it. Nothing taken means the rules still bite —
        which is the whole reason the deduction exists."""
        record = _record(anna, september, [((8, 0), (16, 30))])
        assert record.break_taken_minutes == 0
        assert record.break_minutes == 30
        assert record.worked_minutes == 480

    def test_a_qualifying_break_is_topped_up_rather_than_replaced(
        self, org, anna, september,
    ):
        """A quarter of an hour off is a quarter of an hour off; the remaining
        fifteen still comes out. Counting it as no break would deduct thirty on
        top of it, and counting it as a whole one would leave the day over the
        tier with half the break the tier asks for."""
        record = _record(anna, september, [((8, 0), (12, 0)), ((12, 15), (16, 45))])
        assert record.gross_minutes == 510
        assert record.break_taken_minutes == 15
        assert record.break_minutes == 15
        assert record.worked_minutes == 495

    def test_a_pause_under_a_quarter_of_an_hour_is_not_a_break(
        self, org, anna, september,
    ):
        """§4 ArbZG splits a break into chunks "von jeweils mindestens 15
        Minuten", so ten minutes is neither a Ruhepause nor an interruption:
        it counts towards nothing, and the two stretches either side of it are
        one stretch of eight and a half hours worked through.

        It is still not *worked* — somebody who clocked out was not there — so
        it stays out of the gross either way.
        """
        record = _record(anna, september, [((8, 0), (12, 0)), ((12, 10), (16, 40))])
        assert record.gross_minutes == 510
        assert record.break_taken_minutes == 0
        assert record.break_minutes == 30
        assert record.worked_minutes == 480

    def test_a_break_taken_too_late_does_not_pay_for_one_never_taken(
        self, org, anna, september,
    ):
        """The reported case. 08:30–15:00 is six and a half hours worked straight
        through and owes thirty minutes; clocking out for an hour and coming
        back for one more does not un-work it. §4 has two sentences, and the
        second is that nobody may work "länger als sechs Stunden hintereinander
        ohne Ruhepause"."""
        alone = _record(anna, september, [((8, 30), (15, 0))])
        assert alone.break_minutes == 30
        assert alone.worked_minutes == 360

        both = _record(
            anna, september + dt.timedelta(days=1),
            [((8, 30), (15, 0)), ((16, 0), (17, 0))],
        )
        assert both.gross_minutes == 450
        assert both.break_taken_minutes == 60
        assert both.break_minutes == 30, (
            "adding work after a break removed the break the earlier stretch owed"
        )
        assert both.worked_minutes == 420

    def test_the_gaps_are_walked_in_the_order_they_happened(
        self, org, anna, september,
    ):
        """A night shift's second stretch starts earlier on the clock than its
        first. Sorting by time would put the day back to front and read the gap
        as nineteen hours — ``position`` is a field rather than an ordering by
        ``start`` for exactly this."""
        record = _record(anna, september, [((22, 0), (2, 0)), ((2, 30), (6, 0))])
        assert record.gross_minutes == 240 + 210
        assert record.break_taken_minutes == 30

    def test_a_correction_can_take_time_off(self, org, anna, september):
        record = _record(anna, dt.date(2025, 9, 1), [((8, 0), (17, 0))])
        record.correction_minutes = -30
        record.correction_reason = "long lunch, agreed"
        record.save()
        # 9h at work, 30 off for the break, 30 more by hand.
        assert record.worked_minutes == 480

    def test_a_correction_needs_a_reason(self, org, anna):
        record = DayRecord(employee=anna, date=dt.date(2025, 9, 1), correction_minutes=15)
        with pytest.raises(ValidationError):
            record.full_clean()

    def test_a_day_nobody_worked_and_owes_nothing_has_no_saldo(self, org, anna, september):
        """A Sunday is not a saldo of nought.

        A column of 0:00 down every weekend buries the days that are actually
        level, which are the ones somebody is looking for.
        """
        month = build_month(anna, september)
        sunday = next(r for r in month["rows"] if r["date"] == dt.date(2025, 9, 7))
        assert sunday["contracted_minutes"] == 0
        assert sunday["saldo"] is None

    def test_a_bookings_column_is_a_column_of_comings_and_goings(self, org, anna, september):
        _record(anna, dt.date(2025, 9, 1), [((8, 0), (12, 0)), ((12, 30), (17, 0))])
        row = build_month(anna, september)["rows"][0]
        assert [(b["kind"], b["time"].strftime("%H:%M")) for b in row["bookings"]] == [
            ("in", "08:00"), ("out", "12:00"), ("in", "12:30"), ("out", "17:00"),
        ]

    def test_a_running_shift_is_a_coming_with_no_going(self, org, anna, september):
        _record(anna, dt.date(2025, 9, 1), [((8, 0), None)])
        row = build_month(anna, september)["rows"][0]
        assert [b["kind"] for b in row["bookings"]] == ["in"]
        assert row["is_running"]

    def test_an_absence_credits_the_contracted_hours(self, org, anna, september):
        """A sick day comes out level, with the reason named on the row.

        §3 EFZG: it is paid as though it had been worked. A month that showed a
        fortnight's flu as eighty hours of shortfall would be reporting a debt
        the employee does not owe.
        """
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.SICK,
            start_date=dt.date(2025, 9, 2), end_date=dt.date(2025, 9, 2),
            status=RequestStatus.APPROVED,
        )
        row = build_month(anna, september)["rows"][1]
        assert row["credited_minutes"] == 480
        assert row["saldo"] == 0
        assert row["absence"].kind == AbsenceKind.SICK

    def test_time_off_in_lieu_credits_nothing(self, org, anna, september):
        """The one absence that does not, and that is what makes it work: the
        shortfall *is* the overtime being taken back."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.OVERTIME,
            start_date=dt.date(2025, 9, 2), end_date=dt.date(2025, 9, 2),
            status=RequestStatus.APPROVED,
        )
        row = build_month(anna, september)["rows"][1]
        assert row["credited_minutes"] == 0
        assert row["saldo"] == -480


class TestTheSaldoPointsTheRightWay:
    """The sign is the message, and getting it backwards makes every figure on
    the page disagree with every figure on every other page."""

    def test_a_longer_day_is_a_surplus(self, org, anna, september):
        _record(anna, dt.date(2025, 9, 1), [((8, 0), (17, 30))])
        row = build_month(anna, september)["rows"][0]
        assert row["counted_minutes"] > row["contracted_minutes"]
        assert row["saldo"] > 0

    def test_a_shorter_day_is_a_shortfall(self, org, anna, september):
        _record(anna, dt.date(2025, 9, 1), [((8, 0), (12, 0))])
        row = build_month(anna, september)["rows"][0]
        assert row["saldo"] < 0


class TestTheRunningColumn:
    """Two readings of one thing. The day they drift is the day the timesheet
    says one number at the bottom of a column and another at the top of the
    page."""

    def test_it_carries_forward_rather_than_starting_at_nought(self, org, anna):
        """The first row of a month opens from what came before it, not from
        zero — otherwise the same person has two different balances depending on
        which month somebody happens to be looking at."""
        anna.opening_balance_minutes = 120
        anna.opening_balance_on = dt.date(2025, 1, 1)
        anna.save()

        # Asked of `hours_balance` rather than read off the page: the row that
        # announced the opening figure at the top of the table has gone, and the
        # column carrying it forward silently is exactly what is being checked.
        carried = hours_balance(anna, until=dt.date(2025, 8, 31))["total"]
        month = build_month(anna, dt.date(2025, 9, 1))
        assert month["rows"][0]["running_saldo"] == carried + month["rows"][0]["saldo"]

    def test_the_last_row_is_the_balance_to_date(self, org, anna):
        """The invariant that makes the column worth having. If these two ever
        drift it will be because one of them learned about a new kind of
        credited day and the other did not."""
        first = month_start(dt.date.today() - dt.timedelta(days=40))
        _record(anna, first + dt.timedelta(days=1), [((8, 0), (17, 0))])

        month = build_month(anna, first)
        last = [row for row in month["rows"] if row["running_saldo"] is not None][-1]
        assert last["running_saldo"] == hours_balance(anna, until=last["date"])["total"]

    def test_a_future_day_moves_nothing(self, org, anna):
        """A contract that says eight hours next Tuesday is not a debt anybody
        has already failed to pay. `hours_balance` clamps at today and this has
        to make the same clamp or the two disagree by the rest of the month."""
        first = month_start(dt.date.today() + dt.timedelta(days=45))
        month = build_month(anna, first)
        assert all(row["running_saldo"] is None for row in month["rows"])
        carried = hours_balance(anna, until=first - dt.timedelta(days=1))["total"]
        assert month["balance_to_date"] == carried


# --------------------------------------------------------------------------
# Comings and goings
# --------------------------------------------------------------------------

class TestPairingTheBookings:
    """``apps/timesheets/bookings.py``. A punch list that does not pair is not a
    day with a longer stretch in it — it is a missing punch, and guessing which
    one would put hours on a timesheet nobody entered."""

    def test_a_plain_day_pairs(self):
        pairs = bookings.parse([("in", "08:00"), ("out", "12:00"),
                                ("in", "1230"), ("out", "17")])
        assert pairs == [
            (dt.time(8, 0), dt.time(12, 0)),
            (dt.time(12, 30), dt.time(17, 0)),
        ]

    def test_a_trailing_coming_is_a_shift_in_progress(self):
        assert bookings.parse([("in", "08:00")]) == [(dt.time(8, 0), None)]

    def test_two_comings_in_a_row_are_refused(self):
        with pytest.raises(ValidationError):
            bookings.parse([("in", "08:00"), ("in", "09:00")])

    def test_a_going_with_no_coming_is_refused(self):
        with pytest.raises(ValidationError):
            bookings.parse([("out", "17:00")])

    def test_a_stretch_with_no_length_is_refused(self):
        with pytest.raises(ValidationError):
            bookings.parse([("in", "08:00"), ("out", "08:00")])

    def test_blank_rows_are_dropped_rather_than_refused(self):
        """The pop-up leaves an empty line at the bottom for the next punch, and
        making somebody delete it before they can save would be the app
        complaining about its own affordance."""
        assert bookings.parse([("in", "08:00"), ("out", "17:00"), ("in", "")]) == [
            (dt.time(8, 0), dt.time(17, 0)),
        ]

    def test_the_order_given_is_the_order_kept(self):
        """A night shift's going is at 06:00 and its coming at 22:00. Sorting by
        the clock would put the day back to front."""
        assert bookings.parse([("in", "22:00"), ("out", "06:00")]) == [
            (dt.time(22, 0), dt.time(6, 0)),
        ]

    def test_two_stretches_covering_one_minute_are_refused(self):
        pairs = bookings.parse([("in", "08:00"), ("out", "17:30"),
                                ("in", "17:00"), ("out", "18:30")])
        with pytest.raises(ValidationError):
            bookings.check_overlaps(pairs)

    def test_a_night_shift_is_not_an_overlap(self):
        """The naive comparison — clock value against clock value — reports every
        night shift as an overlap and lets the one real overlap through whenever
        a night shift is on the day."""
        bookings.check_overlaps(bookings.parse([
            ("in", "22:00"), ("out", "06:00"),
        ]))


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------

@pytest.fixture
def post_month(client, anna):
    """Write ``{date: {...}}`` a day at a time, as the page does.

    There is no Save button and no month form: every value is written when the
    box is left or the pop-up accepted, so one POST is one date. The fixture
    keeps the old shape — a dictionary of days — because what the tests are
    about is the arithmetic, not the number of round trips it takes.

    Returns the last response, which is what a test asserting on a refusal
    wants. Each reply carries the whole month recomputed; ``payload`` below is
    for the tests that read it.
    """
    def post(first, days):
        response = None
        for date in sorted(days):
            row = days[date]
            key = date.isoformat()
            response = client.post(f"/timesheet/save/{key}/", {
                "month": first.strftime("%Y-%m"),
                f"time-{key}": row.get("times", []),
                f"kind-{key}": row.get("kinds", []),
                f"correction-{key}": row.get("correction", ""),
                f"why-{key}": row.get("why", ""),
                f"note-{key}": row.get("note", ""),
            })
            if response.status_code != 200:
                # All-or-nothing is per *day* now, so a refusal stops this run
                # the way it stops the person: the day is not written and the
                # next one is not attempted either.
                break
        return response

    def clear(first, date):
        key = date.isoformat()
        return client.post(f"/timesheet/save/{key}/", {
            "month": first.strftime("%Y-%m"),
        })

    post.clear = clear
    return post


class TestSavingTheMonth:
    def test_bookings_become_a_day(self, org, anna, september, post_month):
        response = post_month(september, {
            september: {"times": ["08:00", "12:00", "12:30", "17:00"],
                        "kinds": ["in", "out", "in", "out"]},
        })
        assert response.status_code == 200
        assert response.json()["ok"] is True

        record = DayRecord.objects.get(employee=anna, date=september)
        assert [(s.start, s.end) for s in record.segments.all()] == [
            (dt.time(8, 0), dt.time(12, 0)),
            (dt.time(12, 30), dt.time(17, 0)),
        ]
        # Eight and a half hours at work (4h + 4h30) with the half hour between
        # the stretches already taken, which is what the six-hour tier asks for
        # — so nothing further comes off. The rules ran; they had nothing to add.
        assert record.gross_minutes == 510
        assert record.break_taken_minutes == 30
        assert record.break_minutes == 0
        assert record.worked_minutes == 510

    def test_a_time_is_read_however_it_was_typed(self, org, anna, september, post_month):
        """No format setting, here as everywhere else. Asking somebody which
        notation they are about to use is asking them to do the computer's job.
        """
        post_month(september, {
            september: {"times": ["830", "17"], "kinds": ["in", "out"]},
        })
        segment = DayRecord.objects.get(employee=anna, date=september).segments.get()
        assert (segment.start, segment.end) == (dt.time(8, 30), dt.time(17, 0))

    def test_an_untouched_month_writes_nothing(self, org, anna, september, post_month):
        """Most of a month, most of the time. A Save that rewrote thirty-one rows
        would bump `updated_at` on every one of them and make the audit trail say
        somebody edited a fortnight they never opened."""
        record = _record(anna, september, [((8, 0), (17, 0))])
        before = record.updated_at

        post_month(september, {
            september: {"times": ["08:00", "17:00"], "kinds": ["in", "out"]},
        })
        record.refresh_from_db()
        assert record.updated_at == before

    def test_clearing_a_row_removes_the_day(self, org, anna, september, post_month):
        """A record of nought hours and no record at all are different
        statements, and clearing every cell is the only way to say the second."""
        _record(anna, september, [((8, 0), (17, 0))])
        post_month.clear(september, september)
        assert not DayRecord.objects.filter(employee=anna, date=september).exists()

    def test_editing_the_hours_withdraws_the_confirmation(self, org, anna, september, post_month):
        """Otherwise the record says somebody agreed to figures they have never
        seen, which is exactly the claim a timesheet exists to make honestly."""
        record = _record(anna, september, [((8, 0), (17, 0))])
        record.confirm(by=anna.user)
        assert record.is_confirmed

        post_month(september, {
            september: {"times": ["08:00", "16:00"], "kinds": ["in", "out"]},
        })
        record.refresh_from_db()
        assert not record.is_confirmed

    def test_a_comment_on_its_own_is_not_an_answer_about_hours(
        self, org, anna, september, post_month,
    ):
        """A row can carry a note and nothing else, and that must not read as a
        day of nought hours.

        "They worked none of it" and "nobody has answered yet" are different
        statements and the page has always drawn them differently. The saldo is
        the same either way — the contracted hours are owed regardless — so this
        is only about what the column claims to know.
        """
        post_month(september, {september: {"note": "Schlüssel abgegeben"}})
        record = DayRecord.objects.get(employee=anna, date=september)
        assert record.note == "Schlüssel abgegeben"

        row = build_month(anna, september)["rows"][0]
        assert row["worked_minutes"] is None
        assert row["saldo"] == -480

    def test_a_comment_alone_does_not_withdraw_it(self, org, anna, september, post_month):
        """A comment is not hours. Withdrawing an agreement because somebody
        typed a note would make the confirmation meaningless — it would be about
        the row rather than about the figures."""
        record = _record(anna, september, [((8, 0), (17, 0))])
        record.confirm(by=anna.user)

        post_month(september, {
            september: {"times": ["08:00", "17:00"], "kinds": ["in", "out"],
                        "note": "covered the front desk"},
        })
        record.refresh_from_db()
        assert record.is_confirmed
        assert record.note == "covered the front desk"

    def test_a_correction_is_saved_with_its_reason(self, org, anna, september, post_month):
        post_month(september, {
            september: {"times": ["08:00", "17:00"], "kinds": ["in", "out"],
                        "correction": "30", "why": "forgot to book out"},
        })
        record = DayRecord.objects.get(employee=anna, date=september)
        assert record.correction_minutes == 30
        assert record.correction_reason == "forgot to book out"
        assert record.worked_minutes == 510 + 30

    def test_a_correction_with_no_reason_is_refused(
        self, org, anna, september, post_month,
    ):
        """Refused with a sentence, and the day is left exactly as it was.

        The reason comes back as text rather than as a message on the next page
        load, because there is no next page load — the person is still looking
        at the box they typed into.
        """
        response = post_month(september, {
            dt.date(2025, 9, 2): {"times": ["08:00", "17:00"], "kinds": ["in", "out"],
                                  "correction": "30"},
        })
        assert response.status_code == 400
        assert response.json()["ok"] is False
        assert response.json()["error"]
        assert not DayRecord.objects.filter(employee=anna, date=dt.date(2025, 9, 2)).exists()

    def test_a_day_that_cannot_be_paired_is_refused(
        self, org, anna, september, post_month,
    ):
        response = post_month(september, {
            september: {"times": ["08:00", "09:00"], "kinds": ["in", "in"]},
        })
        assert response.status_code == 400
        assert not DayRecord.objects.filter(employee=anna).exists()

    def test_a_refused_day_leaves_the_others_alone(
        self, org, anna, september, post_month,
    ):
        """One day is the unit now, so the all-or-nothing question the month form
        had to answer does not arise: a day that cannot be read is refused on its
        own and every other day is untouched by construction."""
        post_month(september, {
            september: {"times": ["08:00", "17:00"], "kinds": ["in", "out"]},
        })
        post_month(september, {
            dt.date(2025, 9, 2): {"times": ["08:00", "09:00"], "kinds": ["in", "in"]},
        })
        assert DayRecord.objects.filter(employee=anna).count() == 1
        assert DayRecord.objects.get(employee=anna).date == september

    def test_the_date_in_the_path_is_the_one_that_is_written(
        self, org, anna, september, client,
    ):
        """The date is part of the URL and the fields are keyed on it, so there
        is nowhere for the two to disagree — a day written into next March would
        have to be asked for by a URL that says next March, which is a request
        the page never makes."""
        key = september.isoformat()
        response = client.post(f"/timesheet/save/{key}/", {
            "month": september.strftime("%Y-%m"),
            # Keyed on a different date than the path names: ignored, because
            # `_apply_day` reads the fields for the date it was given.
            "time-2026-03-14": ["08:00", "17:00"],
            "kind-2026-03-14": ["in", "out"],
        })
        assert response.status_code == 200
        assert not DayRecord.objects.filter(employee=anna, date=dt.date(2026, 3, 14)).exists()
        assert not DayRecord.objects.filter(employee=anna, date=september).exists()

    def test_a_second_open_stretch_is_refused(self, org, anna, september, post_month):
        """Two days each with a coming and no going is a state Stop cannot read:
        it would have to guess which of them it ended."""
        post_month(september, {september: {"times": ["08:00"], "kinds": ["in"]}})
        response = post_month(september, {
            dt.date(2025, 9, 2): {"times": ["08:00"], "kinds": ["in"]},
        })
        assert response.status_code == 400
        assert DayRecord.objects.filter(employee=anna).count() == 1

    def test_the_answer_carries_the_whole_month(self, org, anna, september, post_month):
        """One day's edit moves the running total on every row below it and all
        six figures in the footer. A reply carrying only the edited row would
        leave the rest of the column stale — and repeating the prefix sum in
        JavaScript is the duplication `build_month` exists to avoid."""
        response = post_month(september, {
            september: {"times": ["08:00", "17:00"], "kinds": ["in", "out"]},
        })
        month = response.json()["month"]
        assert len(month["rows"]) == 30
        # 08:00–17:00 is nine hours in one stretch, less the 30 the six-hour
        # tier requires — nine exactly does not reach the second one.
        assert month["rows"][0]["counted"] == "08:30"
        assert month["rows"][0]["saldo"] == "+00:30"
        assert month["rows"][0]["break_display"] == "00:30"
        # Written by the server in the page's own notation, never as minutes for
        # the browser to format — that is one more place for the two to disagree
        # about a rounding, on figures somebody is paid against.
        assert month["totals"]["counted"] == "08:30"


class TestWhoMaySaveWhoseMonth:
    def test_an_employee_cannot_save_another_persons_day(
        self, org, anna, client, db, september,
    ):
        from apps.employees.models import Employee

        other = Employee.objects.create(first_name="Other", username="other.month")
        other.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2000, 1, 1))
        key = september.isoformat()
        response = client.post(f"/team/{other.pk}/save/{key}/", {
            f"time-{key}": ["08:00", "17:00"],
            f"kind-{key}": ["in", "out"],
        })
        assert response.status_code == 404
        assert not DayRecord.objects.filter(employee=other).exists()

    def test_a_manager_can(self, org, manager, manager_client, db, september):
        from apps.employees.models import Employee

        other = Employee.objects.create(first_name="Other", username="other.month2")
        other.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2000, 1, 1))
        key = september.isoformat()
        response = manager_client.post(f"/team/{other.pk}/save/{key}/", {
            f"time-{key}": ["08:00", "17:00"],
            f"kind-{key}": ["in", "out"],
        })
        assert response.status_code == 200
        assert DayRecord.objects.filter(employee=other, date=september).exists()


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------

class TestThePageItself:
    def test_it_renders_and_names_the_month(self, org, anna, client):
        response = client.get("/timesheet/?month=2025-09")
        assert response.status_code == 200
        assert response.context["month"] == dt.date(2025, 9, 1)
        assert len(response.context["rows"]) == 30

    def test_a_date_lands_on_the_month_it_falls_in(self, org, anna, client):
        """A link carrying a date — from the roster, or from a message naming a
        day — must not drop somebody on today's month."""
        response = client.get("/timesheet/?month=2025-09-17")
        assert response.context["month"] == dt.date(2025, 9, 1)

    def test_nonsense_lands_on_this_month(self, org, anna, client):
        response = client.get("/timesheet/?month=not-a-month")
        assert response.context["month"] == month_start(dt.date.today())

    def test_the_rostered_times_are_offered_on_a_day_nobody_answered(
        self, org, anna, client,
    ):
        """The checkmark. A day with hours already on it gets no suggestion — the
        page must not offer times somebody has already answered."""
        first = month_start(dt.date.today())
        Shift.objects.create(
            employee=anna, date=first, start=dt.time(8, 0), end=dt.time(16, 0),
        )
        response = client.get(f"/timesheet/?month={first:%Y-%m}")
        row = response.context["rows"][0]
        assert row["shifts"] and not row["bookings"]

    def test_the_picker_opens_on_the_year_being_looked_at(self, org, anna, client):
        """However old the link, the grid is the twelve months of *that* year
        with that month marked in it.

        The select this replaced had to have the month being looked at forced
        into its list, because a select whose selected option is missing shows
        the first entry instead — a picker that quietly disagrees with the page
        it is on. A year and a grid cannot have that fault: there is no list to
        fall out of.
        """
        response = client.get("/timesheet/?month=2019-04")
        cells = response.context["year_months"]
        assert len(cells) == 12
        assert cells[0] == dt.date(2019, 1, 1)
        assert dt.date(2019, 4, 1) in cells
        # The arrows above the grid keep the month and move the year, so they
        # are real links to a real month and work with no script at all.
        assert response.context["previous_year"] == dt.date(2018, 4, 1)
        assert response.context["next_year"] == dt.date(2020, 4, 1)


# --------------------------------------------------------------------------
# The two ways of writing a duration
# --------------------------------------------------------------------------

def test_the_browser_writes_a_duration_the_way_the_server_does():
    """The pop-up's summary sits beside cells the server rendered, so the two
    have to agree about notation as well as about arithmetic.

    The formatter in ``hours.js`` is transcribed here and run against
    ``hours.hhmm`` — not trusted to a comment saying they match.
    """
    from apps.timesheets.hours import hhmm as server_hhmm

    source = (
        pathlib.Path(__file__).resolve().parents[2] / "static" / "js" / "hours.js"
    ).read_text(encoding="utf-8")

    # If somebody rewrites the line the string below stops matching and this
    # fails, which is the point: a silent divergence is the failure mode.
    assert 'String(whole).padStart(2, "0") + ":" + String(rest).padStart(2, "0")' in source, (
        "hours.js no longer writes a duration the way hours.hhmm does"
    )

    def browser(minutes):
        sign = "-" if minutes < 0 else ""
        return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"

    for minutes in list(range(-600, 1500, 7)) + [0, 15, 60, 455, 480, 1440]:
        assert browser(minutes) == server_hhmm(minutes), minutes


def test_every_figure_on_the_page_is_hh_mm(org, anna, client, september):
    """Ten columns read *down* only line up when every figure is the same width,
    and 7,5 above 12,25 above 0,25 is a column somebody has to read twice.

    There is no longer a notation to choose, so this asserts the absence of the
    other one rather than a preference being overridden.
    """
    _record(anna, september, [((8, 0), (17, 0))])

    page = client.get(f"/timesheet/?month={september:%Y-%m}").content.decode()
    assert "08:30" in page, "the month is not written in hh:mm"
    assert "8,50" not in page, "a decimal duration reached the month"


def test_the_month_has_no_save_button(org, anna, client):
    """Every value is written when the box is left or the pop-up accepted, so a
    Save button would be a control with nothing left to do — and a page that has
    one teaches people to look for it before they navigate away."""
    page = client.get("/timesheet/").content.decode()
    assert "data-unsaved-guard" not in page
    assert 'type="submit"' not in page.split('<table')[1].split('</table>')[0]


# --------------------------------------------------------------------------
# A status, set from the status cell
# --------------------------------------------------------------------------

class TestSettingAStatusFromTheCell:
    """Sick, a day off, time in lieu — recorded without opening the Time off
    page. The *forms* are the absences app's own; this only fills in the one
    date the cell is on, so there is no second answer to "may this person book
    this day"."""

    def test_a_sick_day_is_asked_for_like_any_other(self, org, anna, september, client):
        response = client.post(f"/timesheet/status/{september.isoformat()}/", {
            "kind": AbsenceKind.SICK,
        })
        assert response.status_code == 302
        absence = Absence.objects.get(employee=anna)
        assert absence.kind == AbsenceKind.SICK
        assert (absence.start_date, absence.end_date) == (september, september)
        # Sickness used to count from the moment it was entered. It waits like
        # everything else now, and credits nothing until somebody answers.
        assert absence.status == RequestStatus.REQUESTED
        assert build_month(anna, september)["rows"][0]["credited_minutes"] == 0

    def test_time_off_is_asked_for_rather_than_taken(
        self, org, anna, september, client,
    ):
        client.post(f"/timesheet/status/{september.isoformat()}/", {
            "kind": AbsenceKind.HOLIDAY, "reason": "Zahnarzt",
        })
        absence = Absence.objects.get(employee=anna)
        assert absence.kind == AbsenceKind.HOLIDAY
        assert absence.status == RequestStatus.REQUESTED, (
            "a status set from the timesheet must not approve itself — approving "
            "is a separate press that leaves a row saying who decided it"
        )

    def test_a_half_day_is_half_a_day(self, org, anna, september, client):
        """Approved by hand, because nothing set from this cell approves itself
        and a request that has not been decided credits nothing — otherwise one
        that was later declined would take hours off a timesheet
        retrospectively."""
        client.post(f"/timesheet/status/{september.isoformat()}/", {
            "kind": AbsenceKind.SICK, "is_half_day": "1",
        })
        absence = Absence.objects.get(employee=anna)
        assert absence.is_half_day
        assert build_month(anna, september)["rows"][0]["credited_minutes"] == 0

        absence.status = RequestStatus.APPROVED
        absence.save(update_fields=["status"])
        assert build_month(anna, september)["rows"][0]["credited_minutes"] == 240

    def test_time_off_credits_nothing_until_it_is_decided(
        self, org, anna, september, client,
    ):
        """The row shows the reason and waits. Crediting a request that has not
        been decided would let one that is later declined take hours off a
        timesheet after the fact."""
        client.post(f"/timesheet/status/{september.isoformat()}/", {
            "kind": AbsenceKind.HOLIDAY,
        })
        row = build_month(anna, september)["rows"][0]
        assert row["absence"].kind == AbsenceKind.HOLIDAY
        assert row["credited_minutes"] == 0

    def test_clearing_it_withdraws_rather_than_deletes(
        self, org, anna, september, client,
    ):
        """The record still says the conversation happened — the same rule
        ``absences.request_cancel`` follows. Deleting would leave a manager who
        remembers approving something with no trace of it at all."""
        client.post(f"/timesheet/status/{september.isoformat()}/", {
            "kind": AbsenceKind.HOLIDAY,
        })
        client.post(f"/timesheet/status/{september.isoformat()}/", {"kind": ""})

        absence = Absence.objects.get(employee=anna)
        assert absence.status == RequestStatus.WITHDRAWN
        assert build_month(anna, september)["rows"][0]["absence"] is None

    def test_changing_it_replaces_what_was_there(
        self, org, anna, september, client,
    ):
        """One gesture, not two. Refusing because something is already on the
        day would make correcting a mistyped status a two-step job."""
        client.post(f"/timesheet/status/{september.isoformat()}/", {
            "kind": AbsenceKind.HOLIDAY,
        })
        client.post(f"/timesheet/status/{september.isoformat()}/", {
            "kind": AbsenceKind.SICK,
        })
        live = Absence.objects.exclude(status=RequestStatus.WITHDRAWN).get(employee=anna)
        assert live.kind == AbsenceKind.SICK

    def test_a_status_that_cannot_be_saved_leaves_the_old_one_alone(
        self, org, anna, september, client,
    ):
        """The rollback matters. Without it a status that could not be saved
        would still have withdrawn the one that was there, so a mistyped
        correction would silently clear the day."""
        client.post(f"/timesheet/status/{september.isoformat()}/", {
            "kind": AbsenceKind.HOLIDAY,
        })
        # Special leave with no type named: refused by AbsenceRequestForm.
        response = client.post(f"/timesheet/status/{september.isoformat()}/", {
            "kind": AbsenceKind.SPECIAL,
        })
        assert response.status_code == 302
        live = Absence.objects.exclude(status=RequestStatus.WITHDRAWN).get(employee=anna)
        assert live.kind == AbsenceKind.HOLIDAY

    def test_a_range_is_sent_back_to_the_page_it_was_booked_on(
        self, org, anna, september, client,
    ):
        """Taking one date out of a fortnight would have to split it, which is
        four more states and no clearer than editing it where it was booked."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=september, end_date=september + dt.timedelta(days=4),
            status=RequestStatus.APPROVED,
        )
        client.post(f"/timesheet/status/{september.isoformat()}/", {"kind": ""})
        absence = Absence.objects.get(employee=anna)
        assert absence.status == RequestStatus.APPROVED
        assert absence.end_date == september + dt.timedelta(days=4)

    def test_an_employee_cannot_set_another_persons_status(
        self, org, anna, september, client, db,
    ):
        from apps.employees.models import Employee

        other = Employee.objects.create(first_name="Other", username="other.status")
        other.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2000, 1, 1))
        response = client.post(
            f"/team/{other.pk}/status/{september.isoformat()}/",
            {"kind": AbsenceKind.SICK},
        )
        assert response.status_code == 404
        assert not Absence.objects.filter(employee=other).exists()

    def test_a_manager_can(self, org, manager, manager_client, september, db):
        from apps.employees.models import Employee

        other = Employee.objects.create(first_name="Other", username="other.status2")
        other.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2000, 1, 1))
        response = manager_client.post(
            f"/team/{other.pk}/status/{september.isoformat()}/",
            {"kind": AbsenceKind.SICK},
        )
        assert response.status_code == 302
        assert Absence.objects.filter(employee=other, kind=AbsenceKind.SICK).exists()

    def test_clearing_an_approved_day_asks_rather_than_withdraws(
        self, org, anna, september, client,
    ):
        """The same line `absences.request_cancel` draws, drawn from the cell.

        An employee may take back what nobody has answered; an approved absence
        is a day the roster was built around, so choosing "nothing" against one
        asks for it to be cancelled and leaves it booked until somebody says.
        """
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=september, end_date=september,
            status=RequestStatus.APPROVED,
        )
        client.post(f"/timesheet/status/{september.isoformat()}/", {"kind": ""})
        absence.refresh_from_db()
        assert absence.status == RequestStatus.CANCELLING
        assert build_month(anna, september)["rows"][0]["credited_minutes"] == 480

    def test_an_approved_day_cannot_be_swapped_for_another_from_the_cell(
        self, org, anna, september, client,
    ):
        """One cell cannot both cancel and book. Silently withdrawing the
        approved one to make room is the version that loses somebody's holiday
        without ever saying so."""
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=september, end_date=september,
            status=RequestStatus.APPROVED,
        )
        client.post(f"/timesheet/status/{september.isoformat()}/", {
            "kind": AbsenceKind.SICK,
        })
        absence.refresh_from_db()
        assert absence.status == RequestStatus.APPROVED
        assert absence.kind == AbsenceKind.HOLIDAY
        assert anna.absences.count() == 1

    def test_a_manager_takes_it_off_outright(
        self, org, manager, manager_client, september, db,
    ):
        """A manager who would otherwise be answering their own request one
        press later. It is still recorded against them — "who took this off" is
        the same question as "who agreed to it"."""
        from apps.employees.models import Employee

        other = Employee.objects.create(first_name="Other", username="other.cancel")
        other.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2000, 1, 1))
        absence = Absence.objects.create(
            employee=other, kind=AbsenceKind.HOLIDAY,
            start_date=september, end_date=september,
            status=RequestStatus.APPROVED,
        )
        manager_client.post(f"/team/{other.pk}/status/{september.isoformat()}/", {"kind": ""})
        absence.refresh_from_db()
        assert absence.status == RequestStatus.WITHDRAWN
        assert absence.decided_by == manager.user

    def test_the_cell_says_which_entry_of_the_dropdown_the_day_is_on(
        self, org, anna, september, client,
    ):
        """The row carries the key of the option the dropdown must open on —
        and whether there is a dropdown on that row at all.

        A range is read-only from a cell: taking one date out of it would have
        to split it.
        """
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.SICK,
            start_date=september, end_date=september + dt.timedelta(days=3),
            status=RequestStatus.REQUESTED,
        )
        rows = build_month(anna, september)["rows"]
        assert rows[0]["status_kind"] == AbsenceKind.SICK
        assert rows[0]["status_editable"] is False
        assert rows[10]["status_value"] == ""
        assert rows[10]["status_editable"] is True

    def test_a_half_day_opens_on_the_half_day_entry(
        self, org, anna, september, client,
    ):
        """**The row's key must name an option the list actually has.**

        Checked against the rendered option list rather than against a string
        typed here, because a literal would go on passing on the day the two
        spellings drifted apart — and the symptom is not an error: a `<select>`
        whose selected value is missing shows its *first* option instead, so the
        cell would quietly claim a booked half day was an ordinary working day.
        """
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=september, end_date=september, is_half_day=True,
            status=RequestStatus.APPROVED,
        )
        response = client.get(f"/timesheet/?month={september:%Y-%m}")
        offered = {
            option["value"]
            for option in response.context["status_options"]
            + response.context["status_special_options"]
        }
        row = response.context["rows"][0]
        assert row["status_value"] in offered
        assert row["status_value"] != status_value(AbsenceKind.HOLIDAY)
        assert row["status_value"] == status_value(AbsenceKind.HOLIDAY, half=True)

    def test_an_undecided_absence_carries_the_note_the_dotted_edge_explains(
        self, org, anna, september, client,
    ):
        """The pill is drawn with a dotted edge and the title says which kind of
        waiting it is — sickness waits to be *acknowledged* and counts already,
        where a day off waits to be allowed. Built per row in Python because
        `{% translate … as x %}` does not unset itself between rows of a loop.
        """
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=september, end_date=september,
            status=RequestStatus.REQUESTED,
        )
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.SICK,
            start_date=september + dt.timedelta(days=1),
            end_date=september + dt.timedelta(days=1),
            status=RequestStatus.APPROVED,
        )
        rows = build_month(anna, september)["rows"]
        assert rows[0]["status_pending_note"]
        # Decided, so nothing to say — and the row after an undecided one is the
        # one a leaking template variable would have got wrong.
        assert rows[1]["status_pending_note"] == ""
        assert rows[10]["status_pending_note"] == ""
