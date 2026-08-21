"""How long a stretch of work actually was, when the clock itself moves.

Everywhere else in this app a time is a wall clock reading and a span is a
subtraction. That is right almost always and **wrong twice a year**, on the two
nights the clocks change, and it is wrong in the one direction that matters: it
is wrong about somebody's pay.

    A night shift rostered 23:00–07:00 across the last Sunday in March is
    *seven* hours. The clocks go forward at 02:00 and that hour does not exist.
    A wall-clock subtraction says eight.

    The same shift across the last Sunday in October is *nine* hours. 02:00
    happens twice. A wall-clock subtraction still says eight.

Nobody notices, because both answers are plausible and the night in question is
one night a year. What happens instead is that a care home pays an hour it did
not owe every March, and short-pays an hour every October — and the October one
is the one that ends up in front of a labour court, because the employee was
demonstrably at work for nine hours and the timesheet says eight.

So: a span is measured **between two instants**, not between two clock readings.
``elapsed_minutes`` builds an aware ``datetime`` for each end in the zone that
applies and subtracts them. On the 363 ordinary days a year it returns exactly
what ``roster.minutes_between`` returns, which is what
``apps/timesheets/tests.py`` pins — the two are not allowed to disagree except
on the days they must.

---- which zone ----

Two levels, and the second is why this is a setting at all rather than a
constant:

* ``OrgSettings.time_zone`` is the house clock. A kindergarten in Freiburg keeps
  Europe/Berlin and never thinks about this again.
* ``Employee.time_zone`` overrides it for one person. That is the remote
  bookkeeper in Lisbon and the colleague who spends the winter with family in
  Buenos Aires — they clock in at nine *their* time, and a start button that
  wrote the office's nine would be recording a lie about when they were at work.

An employee with no override is on the house clock, which is the answer for
everybody in an ordinary business.

**The stored value is still a wall clock time in that person's zone**, and it is
worth being explicit that this is a decision rather than an oversight. The
alternative — storing UTC instants — makes ``08:00`` render as ``07:00`` for
half the year unless every single read converts back, and the read that forgets
is silent. A local time plus the zone it was read in is the same information, is
what the employee typed, and is what the page has to print back.

---- the hour that does not exist ----

02:30 on the morning the clocks go forward is not a time. Python does not raise
on it; ``ZoneInfo`` resolves it with the pre-transition offset and carries on,
which is the right behaviour for arithmetic and the wrong one for a form.
``nonexistent`` names it so ``apps/timesheets/forms.py`` can say the useful
thing — *that clock time did not happen on that date* — rather than accepting a
shift that quietly measures an hour short.

The opposite case, 02:30 happening twice in October, is **not** an error and is
not reported as one: it is an ordinary time that somebody worked through, and
``fold=0`` takes the first of the two, which is the one that comes first in the
night. A person who started at 02:30 the second time round started an hour after
one who started at 02:30 the first time, and no notation on a paper timesheet
has ever distinguished them either.
"""

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MINUTES_PER_DAY = 24 * 60

# What everything falls back to. Not UTC: a business whose settings row has
# never been saved is overwhelmingly a German one being set up, and a default of
# UTC would put every clocked start an hour or two out in a way that looks
# almost right — which is worse than looking wrong.
DEFAULT_ZONE = "Europe/Berlin"


def zone(name=None):
    """A ``ZoneInfo`` for a name, falling back rather than raising.

    A zone key that the operating system's database does not carry is a
    configuration problem, and it must not be one that takes a timesheet down
    with it. The fallback is loud in the sense that every time then reads in
    Berlin's clock, which somebody notices; an exception here would be a 500 on
    the week page and nothing to read.
    """
    for candidate in (name, DEFAULT_ZONE, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return dt.timezone.utc


# The house zone is asked for once per *segment* on a busy page — the team week
# is eleven people times seven days — and each ask would otherwise be a query
# for a singleton row that changes about once in the life of an installation.
#
# Cached for a minute rather than for ever, and invalidated outright by
# ``OrgSettings.save``. The minute is what covers the case the invalidation
# cannot: gunicorn runs several workers, each with its own local memory, so the
# worker that saved the change forgets immediately and the others forget within
# the minute. A setting nobody edits twice a year being up to sixty seconds
# stale in one worker is not a failure mode worth a shared cache to avoid.
_ORG_ZONE_KEY = "timetracking:org-time-zone"
_ORG_ZONE_TTL = 60


def org_zone_name():
    """The workplace's own zone key, from the settings row."""
    from django.core.cache import cache

    name = cache.get(_ORG_ZONE_KEY)
    if name is None:
        from apps.organisation.models import OrgSettings

        name = getattr(OrgSettings.current(), "time_zone", "") or DEFAULT_ZONE
        cache.set(_ORG_ZONE_KEY, name, _ORG_ZONE_TTL)
    return name


def forget_org_zone():
    """Drop the cached zone. Called by ``OrgSettings.save``."""
    from django.core.cache import cache

    cache.delete(_ORG_ZONE_KEY)


def zone_for(employee=None, settings=None):
    """The clock this person reads. Their own override, or the house's."""
    override = getattr(employee, "time_zone", "") or ""
    if override:
        return zone(override)
    if settings is not None:
        return zone(getattr(settings, "time_zone", "") or DEFAULT_ZONE)
    return zone(org_zone_name())


def zone_name_for(employee=None, settings=None):
    """The key rather than the object, for a page that wants to print it."""
    return str(zone_for(employee, settings))


def at(date, time, tz):
    """One wall clock reading on one date, as an aware ``datetime``.

    ``fold=0`` by default, which picks the *first* of a repeated hour — see the
    module docstring for why that is the answer and not a coin toss.
    """
    return dt.datetime.combine(date, time).replace(tzinfo=tz)


def nonexistent(date, time, tz):
    """Whether that clock reading was skipped by a spring-forward on that date.

    Detected by round-tripping through UTC: a time that exists comes back as
    itself, and one that was skipped comes back as the instant the offset change
    mapped it onto — an hour later, wearing a different offset. That is
    ``ZoneInfo``'s documented way of answering the question and it needs no
    table of transition dates of its own, which matters because a table would be
    the same staleness trap the public holidays deliberately avoid.
    """
    moment = at(date, time, tz)
    return moment.astimezone(dt.timezone.utc).astimezone(tz) != moment


def elapsed_minutes(date, start, end, tz=None):
    """Real minutes between two clock readings, the second possibly tomorrow.

    ``date`` is the date the *start* was read on. An ``end`` at or before the
    start on the clock is the next day, exactly as ``roster.minutes_between``
    has always read it — a shift from 22:00 to 06:00 is eight hours and not
    minus sixteen.

    With no zone this is the plain wall-clock subtraction, which is what the
    roster's own preview and every test that does not care about March want.
    With a zone it is the elapsed time between two instants, so the two nights a
    year when those differ come out right.
    """
    if tz is None:
        first = start.hour * 60 + start.minute
        last = end.hour * 60 + end.minute
        if last <= first:
            last += MINUTES_PER_DAY
        return last - first

    began = at(date, start, tz)
    finished = at(date, end, tz)
    if end <= start:
        finished = at(date + dt.timedelta(days=1), end, tz)

    # **Converted to UTC before subtracting, and that line is the whole
    # module.** Python subtracts two aware datetimes that share a ``tzinfo`` by
    # ignoring the offset entirely — the documented behaviour, and it gives
    # exactly the wall-clock answer this function exists to avoid. The bug is
    # invisible: the code reads as timezone-aware, the objects *are*
    # timezone-aware, and the number is wrong twice a year. Going through UTC is
    # what makes it interzone arithmetic and therefore real elapsed time.
    span = finished.astimezone(dt.timezone.utc) - began.astimezone(dt.timezone.utc)
    return int(span.total_seconds() // 60)


def local_now(tz):
    """Now, on that clock, as an aware ``datetime``.

    Read from UTC and converted rather than from a naive ``datetime.now()``,
    because the container this runs in keeps whatever zone the NAS was set to
    and that is not necessarily the one the employee is standing in.
    """
    return dt.datetime.now(dt.timezone.utc).astimezone(tz)


def local_today(tz):
    """The date it is *there*, which is the date a clocked start belongs to.

    Not a formality. Somebody clocking off at 00:30 in Lisbon is clocking off on
    a date the Berlin server has already moved past, and filing that under the
    server's date puts the end of a night shift on the wrong day of the
    timesheet — where it reads as a second, unexplained half-hour shift.
    """
    return local_now(tz).date()


def all_zone_names():
    """Every zone key this machine's database carries, sorted.

    Offered as a select rather than a free text box: a mistyped key falls back
    silently to Berlin (see ``zone``), and a silent fallback is exactly what a
    settings page must not have.
    """
    from zoneinfo import available_timezones

    try:
        names = sorted(available_timezones())
    except Exception:  # noqa: BLE001 - a missing tzdata is not worth a 500
        names = []
    return names or [DEFAULT_ZONE, "UTC"]
