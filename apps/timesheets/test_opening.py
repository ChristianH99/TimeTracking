"""What somebody arrives with, and the running total it starts.

Nobody starts at nought. The figures a new joiner brings from a previous
contract — hours in hand, days of leave not yet taken — had nowhere to go, and
the only ways to record them were to invent a week of hours nobody worked or to
leave the balance wrong and remember the difference.

The test that matters most here is the last one: **the running balance and the
week view must agree.** They are two readings of one thing, computed by two
functions, and the day they disagree is the day somebody's timesheet says one
number at the top of the page and a different one in the middle.
"""

import datetime as dt
from decimal import Decimal

import pytest

from apps.absences.models import Absence, AbsenceKind, Balance, RequestStatus
from apps.employees.models import Employee
from apps.timesheets.balance import hours_balance
from apps.timesheets.fields import SignedDurationField
from apps.timesheets.hours import contracted_minutes
from apps.timesheets.models import DayRecord, WorkSegment
from apps.timesheets.views import build_week


def _worked(employee, day, start, end):
    record, _ = DayRecord.objects.get_or_create(employee=employee, date=day)
    WorkSegment.objects.create(day=record, start=dt.time(start), end=dt.time(end))
    record.refresh_from_db()
    record.apply_break_rules()
    record.save(update_fields=["break_minutes"])
    return record


class TestReadingASignedDuration:
    """The one field in the app where a leading minus means something."""

    @pytest.mark.parametrize(("typed", "minutes"), [
        ("14", 14 * 60),
        ("-14", -14 * 60),
        ("-14:00", -14 * 60),
        ("-14,0", -14 * 60),
        ("+8:30", 510),
        ("-8,5", -510),
        ("-0:45", -45),
        ("-830", -510),
        # What a spreadsheet and a PDF paste: a real minus sign and an en dash.
        ("−14", -14 * 60),
        ("–14", -14 * 60),
    ])
    def test_it_reads_the_sign_and_then_the_duration(self, typed, minutes):
        assert SignedDurationField().to_python(typed) == minutes

    def test_it_writes_the_sign_outside_the_colon(self):
        """``-1:-15`` is what a naive divmod gives for a small shortfall, and it
        is the sort of thing somebody reads twice and then reports."""
        field = SignedDurationField()
        assert field.prepare_value(-840) == "-14:00"
        assert field.prepare_value(-45) == "-0:45"
        assert field.prepare_value(510) == "8:30"

    def test_a_duration_is_not_wrapped_at_a_day(self):
        """The bug this split found: `timeparse.clock` is a *time of day*, so it
        wraps at 24 and drops the sign. Used on a duration it renders 25 hours
        as "01:00" and fourteen hours owed as "10:00" — plausible numbers, both
        wrong, neither raising anything."""
        from apps.timesheets.timeparse import clock, duration_clock

        assert duration_clock(25 * 60) == "25:00"
        assert duration_clock(24 * 60) == "24:00"
        assert clock(25 * 60) == "01:00", "the time-of-day one still wraps, on purpose"

    def test_nonsense_is_still_refused(self):
        field = SignedDurationField()
        for value in ("-", "-abc", "--4", "-:"):
            with pytest.raises(Exception):
                field.to_python(value)


class TestTheHoursSomebodyArrivesWith:
    def test_the_balance_starts_from_the_opening_figure(self, org, anna, monday):
        anna.opening_balance_minutes = 14 * 60
        anna.opening_balance_on = monday
        anna.started_on = monday
        anna.save()

        running = hours_balance(anna, until=monday)
        assert running["opening"] == 14 * 60
        # Monday is contracted eight hours and nothing was worked, so the day
        # itself is a shortfall — the opening figure is what it moves from.
        assert running["total"] == 14 * 60 - contracted_minutes(Decimal("8"))

    def test_it_can_be_negative(self, org, anna, monday):
        """Somebody can arrive owing hours as easily as being owed them, and a
        field that could not say so would push that case into a fake week of
        negative shifts."""
        anna.opening_balance_minutes = -14 * 60
        anna.opening_balance_on = monday
        anna.started_on = monday
        anna.save()
        assert hours_balance(anna, until=monday)["opening"] == -14 * 60

    def test_days_before_the_opening_date_are_not_counted(self, org, anna, monday):
        """Days before somebody's contract began are not a shortfall — they were
        not employed. The opening figure *is* the summary of everything before
        it, agreed with them."""
        anna.started_on = monday
        anna.opening_balance_on = monday
        anna.opening_balance_minutes = 0
        anna.save()

        running = hours_balance(anna, until=monday)
        assert running["contracted"] == contracted_minutes(Decimal("8")), \
            "one day, not the whole of the year before"

    def test_the_future_is_never_counted(self, org, anna):
        """A contract that says eight hours next Tuesday is not a debt somebody
        has already failed to pay."""
        today = dt.date.today()
        anna.started_on = today - dt.timedelta(days=7)
        anna.opening_balance_on = anna.started_on
        anna.save()

        near = hours_balance(anna, until=today)
        far = hours_balance(anna, until=today + dt.timedelta(days=365))
        assert near["total"] == far["total"]
        assert far["until"] == today

    def test_a_running_shift_moves_nothing_yet(self, org, anna):
        """A balance refreshed mid-shift must not creep upwards while somebody
        watches it."""
        from apps.timesheets import clocking

        today = dt.date.today()
        anna.started_on = today
        anna.opening_balance_on = today
        anna.opening_balance_minutes = 60
        anna.save()

        before = hours_balance(anna)["total"]
        clocking.start(anna, by=anna.user)
        assert hours_balance(anna)["total"] == before


class TestTheLeaveDaysSomebodyArrivesWith:
    def test_they_are_added_to_the_entitlement(self, org, anna):
        year = dt.date.today().year
        plain = Balance(anna, year, org).entitlement

        anna.opening_leave_days = Decimal("6.0")
        anna.opening_balance_on = dt.date(year, 1, 15)
        anna.save()

        assert Balance(anna, year, org).entitlement == plain + Decimal("6.0")

    def test_they_are_counted_only_in_their_own_year(self, org, anna):
        """The obvious mistake is to add them to every year, which hands
        somebody their joining figure again each January. The other is to add
        them to no year at all, which is what happens if the date is null."""
        year = dt.date.today().year
        anna.opening_leave_days = Decimal("6.0")
        anna.opening_balance_on = dt.date(year, 1, 15)
        anna.started_on = dt.date(year, 1, 15)
        anna.save()

        assert Balance(anna, year, org).opening_days == Decimal("6.0")
        assert Balance(anna, year + 1, org).opening_days == Decimal("0")
        assert Balance(anna, year - 1, org).opening_days == Decimal("0")

    def test_what_is_left_of_them_carries_forward_normally(self, org, anna):
        """Not lost after the first year: whatever is untaken goes through
        `LeaveCarryOver` like anybody else's remainder, which is the same path
        and therefore not a second code branch to get wrong."""
        from apps.absences.carryover import LeaveCarryOver

        anna.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2025, 1, 1))
        anna.started_on = dt.date(2025, 1, 1)
        anna.opening_balance_on = dt.date(2025, 1, 1)
        anna.opening_leave_days = Decimal("6.0")
        anna.save()

        closing = Balance(anna, 2025, org)
        row = LeaveCarryOver.close_year(anna, 2025, org)
        assert row.total_days == closing.remaining
        assert closing.remaining == org.leave_days_for(5) + Decimal("6.0")

        # And 2026 does not get the six again.
        assert Balance(anna, 2026, org).opening_days == Decimal("0")

    def test_a_figure_with_no_date_falls_back_to_the_start_date(self, org, db):
        """An opening figure with no date could not be attributed to a year and
        would be counted into none — stored, invisible, impossible to explain."""
        person = Employee.objects.create(
            first_name="Nula", username="nula.test",
            started_on=dt.date(2026, 4, 1), opening_leave_days=Decimal("3.0"),
        )
        person.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2026, 4, 1))

        assert person.opening_balance_on is None
        assert person.opening_date == dt.date(2026, 4, 1)
        assert Balance(person, 2026, org).opening_days == Decimal("3.0")


class TestTheTwoFiguresAgree:
    """The invariant, and the reason `apps/timesheets/balance.py` has a header.

    The running balance and the week view are two readings of one thing computed
    by two functions. The day they disagree is the day somebody's timesheet says
    one number at the top of the page and a different one in the middle — and
    neither is obviously the wrong one.
    """

    def test_a_weeks_movement_equals_that_weeks_difference(self, org, anna, monday):
        anna.started_on = monday
        anna.opening_balance_on = monday
        anna.opening_balance_minutes = 3 * 60
        anna.save()

        _worked(anna, monday, 8, 17)
        _worked(anna, monday + dt.timedelta(days=1), 8, 14)
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.SICK,
            start_date=monday + dt.timedelta(days=2),
            end_date=monday + dt.timedelta(days=2),
            status=RequestStatus.REQUESTED,
        )

        week = build_week(anna, monday)
        running = hours_balance(anna, until=monday + dt.timedelta(days=6))

        assert running["movement"] == week["difference"], (
            "the running balance and the week view disagree about the same seven days"
        )
        assert running["total"] == 3 * 60 + week["difference"]

    def test_it_holds_with_a_half_day_and_a_holiday(self, org, anna, monday):
        """The two branches most likely to be added to one function and not the
        other: a credited absence worth half a day, and a public holiday."""
        from apps.absences.models import BankHoliday

        anna.started_on = monday
        anna.opening_balance_on = monday
        anna.save()

        BankHoliday.objects.create(
            date=monday + dt.timedelta(days=1), name="Test-Feiertag",
        )
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            is_half_day=True, status=RequestStatus.APPROVED,
        )
        _worked(anna, monday, 8, 12)

        week = build_week(anna, monday)
        running = hours_balance(anna, until=monday + dt.timedelta(days=6))
        assert running["movement"] == week["difference"]

    def test_it_holds_across_a_contract_change(self, org, anna, monday):
        """Both sides ask for the contract *as at the day*, and a version that
        asked one of them for today's would drift by exactly the change."""
        anna.started_on = monday
        anna.opening_balance_on = monday
        anna.save()
        anna.set_hours([4, 4, 4, 4, 4, 0, 0], valid_from=monday + dt.timedelta(days=3))

        week = build_week(anna, monday)
        running = hours_balance(anna, until=monday + dt.timedelta(days=6))
        assert running["movement"] == week["difference"]
