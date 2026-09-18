"""The two nights a year a wall-clock subtraction is wrong about somebody's pay.

Every case here is one that renders perfectly and reports a plausible number.
That is why they are pinned: nobody notices an eight-hour night shift on the
last Sunday in October, and the employee who was demonstrably at work for nine
hours is the one who ends up in front of a labour court.

The dates are real and fixed. The European Union moves the clocks on the last
Sunday of March and of October, at 02:00 and 03:00 local time respectively, and
those two Sundays are what these tests name.
"""

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from apps.timesheets.zones import (
    DEFAULT_ZONE, elapsed_minutes, local_today, nonexistent, zone, zone_for,
)

BERLIN = ZoneInfo("Europe/Berlin")

# The last Sunday in March 2026: 02:00 becomes 03:00 and the hour between them
# never happens.
SPRING_FORWARD = dt.date(2026, 3, 29)
# The last Sunday in October 2026: 03:00 becomes 02:00 and the hour happens
# twice.
FALL_BACK = dt.date(2026, 10, 25)


class TestAnOrdinaryDay:
    """363 days a year this has to agree with the plain subtraction it replaces.

    If it did not, every existing test about a night shift would be wrong and
    the disagreement would be blamed on the clock change rather than on this.
    """

    @pytest.mark.parametrize(("start", "end", "minutes"), [
        ((8, 0), (17, 0), 9 * 60),
        ((8, 30), (12, 0), 210),
        ((22, 0), (6, 0), 8 * 60),        # across midnight
        ((23, 0), (3, 0), 4 * 60),        # the case the brief named
        ((0, 0), (0, 0), 24 * 60),        # a whole day, not nought
    ])
    def test_it_matches_a_plain_subtraction(self, start, end, minutes):
        day = dt.date(2026, 6, 10)
        first = dt.time(*start)
        last = dt.time(*end)
        assert elapsed_minutes(day, first, last, BERLIN) == minutes
        # And with no zone at all, which is the wall-clock reading the roster's
        # own preview uses.
        assert elapsed_minutes(day, first, last, None) == minutes


class TestTheNightTheClocksGoForward:
    """An hour that does not exist, and a shift that is an hour shorter."""

    def test_a_night_shift_across_it_is_an_hour_shorter(self):
        """23:00–07:00 is seven hours, not eight.

        The wall-clock subtraction says eight, and paying eight is paying an
        hour nobody worked — every March, for everybody on that shift.
        """
        assert elapsed_minutes(
            SPRING_FORWARD - dt.timedelta(days=1),
            dt.time(23, 0), dt.time(7, 0), BERLIN,
        ) == 7 * 60

    def test_a_shift_that_starts_after_the_change_is_unaffected(self):
        assert elapsed_minutes(
            SPRING_FORWARD, dt.time(8, 0), dt.time(16, 0), BERLIN,
        ) == 8 * 60

    def test_the_missing_hour_is_named_as_missing(self):
        """02:30 on that morning is not a time.

        Python does not raise on it — ZoneInfo resolves it with the
        pre-transition offset and carries on, which is right for arithmetic and
        wrong for a form. This is the only place anybody finds out.
        """
        assert nonexistent(SPRING_FORWARD, dt.time(2, 30), BERLIN)
        assert not nonexistent(SPRING_FORWARD, dt.time(1, 30), BERLIN)
        assert not nonexistent(SPRING_FORWARD, dt.time(3, 30), BERLIN)
        # And the same clock time on any other date is perfectly ordinary.
        assert not nonexistent(SPRING_FORWARD - dt.timedelta(days=7),
                               dt.time(2, 30), BERLIN)


class TestTheNightTheClocksGoBack:
    """An hour that happens twice, and a shift that is an hour longer."""

    def test_a_night_shift_across_it_is_an_hour_longer(self):
        """23:00–07:00 is nine hours.

        This is the direction that gets litigated: the employee was
        demonstrably at work for nine hours and the timesheet says eight.
        """
        assert elapsed_minutes(
            FALL_BACK - dt.timedelta(days=1),
            dt.time(23, 0), dt.time(7, 0), BERLIN,
        ) == 9 * 60

    def test_the_repeated_hour_is_not_an_error(self):
        """02:30 happens twice and both of them are ordinary times.

        Reporting it as impossible would refuse a time somebody genuinely
        looked at. `fold=0` takes the first of the two, which is the one that
        comes first in the night — and no paper timesheet has ever
        distinguished them either.
        """
        assert not nonexistent(FALL_BACK, dt.time(2, 30), BERLIN)

    def test_the_break_rules_see_the_longer_day(self, org):
        """The point of getting the length right, in the figure it feeds.

        The hour does not stop at the span. It goes into the gross, which the
        break rules and the balance are computed from, so a wall-clock reading
        of this night short-changes somebody by a whole hour of paid time —
        which is the number they are paid on and the one a labour court is
        shown.
        """
        gross = elapsed_minutes(
            FALL_BACK - dt.timedelta(days=1),
            dt.time(23, 0), dt.time(7, 0), BERLIN,
        )
        assert gross == 9 * 60
        naive = 8 * 60  # what subtracting the two clock readings would give

        assert gross - org.required_break(gross) == 8 * 60 + 30
        assert naive - org.required_break(naive) == 7 * 60 + 30

    def test_a_long_enough_night_crosses_the_second_tier(self, org):
        """And on a longer shift the error crosses a tier as well.

        22:00 to 07:00 is ten hours on this night and nine on any other, which
        is exactly the boundary §4 ArbZG puts the forty-five-minute break at —
        so the wall-clock reading deducts thirty where forty-five are owed, on
        top of losing the hour.
        """
        gross = elapsed_minutes(
            FALL_BACK - dt.timedelta(days=1),
            dt.time(22, 0), dt.time(7, 0), BERLIN,
        )
        assert gross == 10 * 60
        assert org.required_break(gross) == 45
        assert org.required_break(9 * 60) == 30


class TestWhichClock:
    def test_an_employee_with_no_override_is_on_the_house_clock(self, org, anna):
        org.time_zone = "Europe/Berlin"
        org.save()
        assert str(zone_for(anna)) == "Europe/Berlin"

    def test_an_employee_elsewhere_keeps_their_own(self, org, anna):
        """The remote colleague. They clock in at nine *their* time, and a start
        button writing the office's nine would record a lie about when they were
        at work."""
        org.time_zone = "Europe/Berlin"
        org.save()
        anna.time_zone = "America/Argentina/Buenos_Aires"
        anna.save()
        assert str(zone_for(anna)) == "America/Argentina/Buenos_Aires"

    def test_the_date_is_the_date_it_is_there(self, org):
        """Not a formality: somebody clocking off at 00:30 in Lisbon is clocking
        off on a date Berlin has already left, and filing it under the server's
        date puts the end of a night shift on the wrong row."""
        pacific = local_today(zone("Pacific/Kiritimati"))
        samoa = local_today(zone("Pacific/Niue"))
        # Kiritimati is UTC+14 and Niue UTC-11: twenty-five hours apart, so they
        # are never on the same date at the same instant.
        assert pacific != samoa

    def test_the_zone_database_is_actually_present(self):
        """The fallback must never be the *answer* for a real zone.

        `zone()` degrades to UTC rather than raising, which is right for a
        mistyped key and catastrophic as the answer for Europe/Berlin: every
        clocked time would be an hour or two out all summer, in a way that looks
        almost right and raises nothing.

        It is a real risk and not a hypothetical one. `zoneinfo` reads the
        operating system's IANA database, and `python:3.13-slim` — which is what
        deploy/Dockerfile runs — is not guaranteed to carry one. The fix is the
        `tzdata` dependency in pyproject.toml, unconditional rather than
        Windows-only; this is what stops it being dropped again.
        """
        for key in ("Europe/Berlin", "Europe/Lisbon", "America/New_York", "UTC"):
            assert str(zone(key)) == key, (
                f"{key} did not resolve — the zone database is missing, and every "
                "time in this app is silently being read in UTC. Check that tzdata "
                "is still an unconditional dependency."
            )

        # And the summer offset really is an hour ahead of the winter one, which
        # is the thing a stub database would not know.
        winter = dt.datetime(2026, 1, 15, 12, tzinfo=BERLIN).utcoffset()
        summer = dt.datetime(2026, 7, 15, 12, tzinfo=BERLIN).utcoffset()
        assert summer - winter == dt.timedelta(hours=1)

    def test_an_unknown_zone_falls_back_rather_than_raising(self):
        """A zone key this machine's database does not carry is a configuration
        problem and must not be one that takes the week page down with it."""
        assert str(zone("Middle/Earth")) == DEFAULT_ZONE
        assert str(zone("")) == DEFAULT_ZONE
        assert str(zone(None)) == DEFAULT_ZONE

    def test_saving_the_settings_forgets_the_cached_zone(self, org):
        """The house zone is cached for a minute, and this is the one setting
        where waiting that minute would be visible: the page you land on after
        saving would still be clocking people in on the old clock."""
        org.time_zone = "Europe/Berlin"
        org.save()
        assert str(zone_for(None)) == "Europe/Berlin"

        org.time_zone = "Europe/Lisbon"
        org.save()
        assert str(zone_for(None)) == "Europe/Lisbon"
