"""Start and Stop, and the open-ended day behind them.

The invariant the whole feature rests on is that **there is one representation of
"at work"** — a stretch with no end — and that the button, the week row and the
day form all read it. A second flag would be the bug where the button says Stop
and the timesheet says nothing is running.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError

from apps.timesheets import clocking
from apps.timesheets.models import DayRecord, WorkSegment

BERLIN = ZoneInfo("Europe/Berlin")


def _at(day, hour, minute=0, tz=BERLIN):
    return dt.datetime.combine(day, dt.time(hour, minute)).replace(tzinfo=tz)


@pytest.fixture
def today():
    return dt.date.today()


class TestOnlyOneButtonAtATime:
    def test_a_fresh_day_offers_start(self, org, anna, today):
        state = clocking.state_for(anna)
        assert state["can_start"]
        assert state["running"] is None

    def test_once_started_it_offers_stop(self, org, anna, today):
        clocking.start(anna, by=anna.user, now=_at(today, 8))
        state = clocking.state_for(anna, now=_at(today, 10))
        assert not state["can_start"]
        assert state["since"] == dt.time(8, 0)
        assert state["minutes_so_far"] == 120

    def test_starting_twice_is_refused(self, org, anna, today):
        """Not a nicety: two open stretches is a state with no reading, because
        Stop would have to guess which of them it ended."""
        clocking.start(anna, by=anna.user, now=_at(today, 8))
        with pytest.raises(ValidationError):
            clocking.start(anna, by=anna.user, now=_at(today, 9))

    def test_stopping_when_nothing_runs_is_refused(self, org, anna):
        with pytest.raises(ValidationError):
            clocking.stop(anna, by=anna.user)


class TestWhatItRecords:
    def test_stop_closes_the_stretch_and_works_out_the_break(self, org, anna, today):
        """The break is worked out at Stop and not before, because that is the
        first moment the day has a length to work one out from."""
        clocking.start(anna, by=anna.user, now=_at(today, 8))
        segment = clocking.stop(anna, by=anna.user, now=_at(today, 17))

        record = DayRecord.objects.get(employee=anna, date=today)
        assert segment.start == dt.time(8, 0)
        assert segment.end == dt.time(17, 0)
        assert record.gross_minutes == 9 * 60
        # Nine hours exactly is not *over* nine hours, so the second tier does
        # not bite — §4 ArbZG asks forty-five of a day longer than nine.
        assert record.break_minutes == 30
        assert record.worked_minutes == 9 * 60 - 30

    def test_a_running_stretch_is_worth_nothing_yet(self, org, anna, today):
        """The tempting answer is "up to now", and it is wrong for the one job
        `minutes` has: it is summed into the gross, which the break rules and
        the balance are computed from, and a number that changes on every page
        refresh is not something anybody can sign off."""
        clocking.start(anna, by=anna.user, now=_at(today, 8))
        record = DayRecord.objects.get(employee=anna, date=today)
        assert record.gross_minutes == 0
        assert record.is_running
        assert record.running_segment.minutes_so_far(_at(today, 11)) == 180

    def test_it_does_not_round(self, org, anna, today):
        """An employer who wants quarter-hours can arrange that with their
        staff. Rounding always in the same direction is how a minute a day
        becomes four hours a year, and the record is supposed to be of the time
        actually worked."""
        clocking.start(anna, by=anna.user, now=_at(today, 7, 58))
        segment = clocking.stop(anna, by=anna.user, now=_at(today, 16, 3))
        assert segment.start == dt.time(7, 58)
        assert segment.end == dt.time(16, 3)

    def test_a_zero_length_stretch_is_refused(self, org, anna, today):
        """Somebody who pressed both buttons inside a minute meant to press
        neither, and the model refuses a stretch of no length anyway."""
        clocking.start(anna, by=anna.user, now=_at(today, 8))
        with pytest.raises(ValidationError):
            clocking.stop(anna, by=anna.user, now=_at(today, 8))

    def test_starting_inside_an_existing_stretch_is_refused(self, org, anna, today):
        """Somebody types 08:00–16:00 in the morning, then presses Start out of
        habit at 09:15. Without this the day quietly holds two stretches over
        the same hours and reports seven hours nobody worked."""
        record = DayRecord.objects.create(employee=anna, date=today)
        WorkSegment.objects.create(day=record, start=dt.time(8), end=dt.time(16))
        with pytest.raises(ValidationError):
            clocking.start(anna, by=anna.user, now=_at(today, 9, 15))


class TestTheNightShift:
    def test_stop_finds_a_stretch_started_yesterday(self, org, anna, today):
        """A stretch started at 22:00 is still open at 02:00, and by then
        "today" is a different date from the one it belongs to."""
        yesterday = today - dt.timedelta(days=1)
        clocking.start(anna, by=anna.user, now=_at(yesterday, 22))
        segment = clocking.stop(anna, by=anna.user, now=_at(today, 2))

        assert segment.day.date == yesterday
        assert segment.day.gross_minutes == 4 * 60

    def test_it_does_not_reach_back_two_days(self, org, anna, today):
        """A stretch left open for two days is not somebody still at work — it
        is somebody who forgot, and quietly closing it forty hours later would
        write a working day nobody worked."""
        long_ago = today - dt.timedelta(days=3)
        record = DayRecord.objects.create(employee=anna, date=long_ago)
        WorkSegment.objects.create(day=record, start=dt.time(9), end=None)

        assert clocking.open_stretch(anna, _at(today, 10)) is None


class TestConfirmingARunningDay:
    def test_it_is_refused(self, org, anna, today):
        """Confirming means "this is what I worked", and a day with an open
        stretch has no such figure yet. Allowing it would record an agreement to
        a total that changes the moment somebody presses Stop."""
        clocking.start(anna, by=anna.user, now=_at(today, 8))
        record = DayRecord.objects.get(employee=anna, date=today)
        with pytest.raises(ValidationError):
            record.confirm(by=anna.user)

    def test_a_running_day_is_not_reported_as_differing(self, org, anna, monday):
        """"Still running" and "different from what was asked" are different
        statements, and only one of them is true yet. Flagging both would put an
        attention pill on every shift the moment somebody pressed Start —
        training everybody to ignore the one pill that matters."""
        from apps.roster.models import Shift
        from apps.timesheets.views import build_week

        Shift.objects.create(employee=anna, date=monday,
                             start=dt.time(8), end=dt.time(16))
        clocking.start(anna, by=anna.user, now=_at(monday, 8))

        row = build_week(anna, monday)["rows"][0]
        assert row["is_running"]
        assert not row["differs_from_roster"]

    def test_a_running_day_never_matches_the_roster(self, org, anna, today):
        """"Still going" is not the same statement as "different from the plan",
        and sorting a None into the pairs would raise on the comparison
        anyway."""
        clocking.start(anna, by=anna.user, now=_at(today, 8))
        record = DayRecord.objects.get(employee=anna, date=today)
        assert not record.matches_roster([])


class TestThroughTheView:
    def test_the_route_decides_which_of_the_two_it_is(self, org, anna, client, today):
        """One route rather than two, because the page only ever offers one of
        them and a second URL would be a second thing that could get out of step
        with the state. Which one it is is read from the database, not from what
        the form said — a tab left open overnight must not be able to start a
        second shift by being the older of the two.
        """
        url = f"/timesheet/{anna.pk}/clock/"

        client.post(url)
        assert clocking.open_stretch(anna) is not None, "the first press started it"

        # Backdated by an hour, because a start and a stop inside the same
        # minute is a stretch of no length and is refused — which is itself
        # correct, and is pinned above.
        segment = clocking.open_stretch(anna)
        segment.start = (dt.datetime.combine(today, dt.time(9))).time()
        segment.save(update_fields=["start"])

        client.post(url)
        assert clocking.open_stretch(anna) is None, "the second press stopped it"

    def test_somebody_else_cannot_clock_you_in(self, org, anna, cem, client):
        """The same door as every other timesheet route: your own always,
        anybody else's only as a manager."""
        response = client.post(f"/timesheet/{cem.pk}/clock/")
        assert response.status_code == 404
        assert clocking.open_stretch(cem) is None
