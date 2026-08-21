"""Start and Stop: putting the time on the timesheet by pressing one button.

The typing form is for the days that need explaining. This is for the ordinary
one — you arrive, you press Start, you leave, you press Stop — and it exists
because the alternative is asking somebody at 06:58 to work out what 06:58 is.

**Only ever one of the two buttons is offered**, and that is the whole design
rather than a nicety. A page showing both has to be read before it can be used:
which one am I? Whereas a page showing exactly one is a page you press. The
state that decides it is not a flag anybody sets — it is whether there is a
stretch on today's record with no end on it, which is the same fact the day form
and the week view read. There is no second representation of "at work", so there
is no way for the button and the timesheet to disagree.

---- which day, and whose clock ----

The date is **today in the employee's own zone**, not the server's. Somebody
clocking off at 00:30 in Lisbon is clocking off on a date Berlin has already
left, and filing that under the server's date puts the end of their shift on the
wrong row — where it reads as a second, unexplained half-hour of work.

The stretch that Stop closes is looked for on **today and yesterday**, in that
order, and that is the night shift: a stretch started at 22:00 is still open at
02:00, and by then "today" is a different date from the one it belongs to.
Yesterday is as far back as it looks, because a stretch left open for two days
is not somebody still at work — it is somebody who forgot, and quietly closing
it forty hours later would write a working day nobody worked.

---- what it deliberately does not do ----

It does not round. A start of 07:58 is stored as 07:58, and an employer who
wants to round to the quarter hour can arrange that with their staff rather than
have an app do it to them silently — rounding always in the same direction is
how a minute a day becomes four hours a year, and §16 ArbZG expects the record
to be of the time actually worked.

It does not touch the break. The break comes from the rules the moment the day
has a length to compute one from, which is when Stop is pressed.
"""

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.organisation.models import OrgSettings
from apps.timesheets.models import DayRecord, EntrySource, WorkSegment
from apps.timesheets.zones import local_now, zone_for

# How far back Stop looks for the stretch it should close. One day, which is a
# night shift; see the module docstring for why it is not two.
LOOK_BACK = dt.timedelta(days=1)


class ClockError(ValidationError):
    """Refused, with a sentence saying what to do instead."""


def open_stretch(employee, now=None):
    """The stretch this person has started and not stopped, or ``None``.

    Looks at today and yesterday on their own clock. Returns the
    ``WorkSegment`` rather than a boolean, because every caller that wants to
    know *whether* also wants to know *since when* — the button says "Stop
    (since 07:58)" and the week row says how long it has been running.
    """
    tz = zone_for(employee)
    today = (now or local_now(tz)).date()
    return (
        WorkSegment.objects
        .filter(
            day__employee=employee,
            day__date__gte=today - LOOK_BACK,
            day__date__lte=today,
            end__isnull=True,
        )
        .select_related("day", "day__employee")
        .order_by("-day__date", "-start")
        .first()
    )


def state_for(employee, now=None):
    """What the button should say, as plain data for a template.

    One dictionary rather than three separate context keys, so that a page
    cannot render the Start button and the "running since" line from two
    different answers to the same question.
    """
    running = open_stretch(employee, now)
    tz = zone_for(employee)
    moment = now or local_now(tz)
    return {
        "employee": employee,
        "running": running,
        "can_start": running is None,
        "since": running.start if running else None,
        "since_date": running.day.date if running else None,
        "minutes_so_far": running.minutes_so_far(moment) if running else 0,
        "now": moment.time().replace(second=0, microsecond=0),
        "zone": str(tz),
        # True when the clock they are reading is not the workplace's, which is
        # the one case the page has to say out loud — otherwise a manager
        # looking at the team sees a start time that appears to be an hour wrong.
        "is_elsewhere": bool(getattr(employee, "time_zone", "")),
    }


@transaction.atomic
def start(employee, by, now=None):
    """Begin a stretch at the current minute. Returns the ``WorkSegment``.

    Refuses if one is already running, rather than starting a second — two open
    stretches is a state with no reading, and the caller has just rendered a
    page that said Stop.
    """
    tz = zone_for(employee)
    moment = now or local_now(tz)

    if open_stretch(employee, moment) is not None:
        raise ClockError(_(
            "A shift is already running. Stop that one before starting another."
        ))

    settings = OrgSettings.current()
    record, _created = DayRecord.objects.get_or_create(
        employee=employee, date=moment.date(),
        defaults={"source": EntrySource.MANUAL},
    )

    at = moment.time().replace(second=0, microsecond=0)
    _refuse_if_covered(record, at)

    segment = WorkSegment.objects.create(
        day=record, start=at, end=None,
        position=(record.segments.count()),
    )
    # The hours have changed, so an earlier agreement to them is no longer an
    # agreement to anything anybody has seen.
    record.refresh_from_db()
    record.unconfirm()
    record.apply_break_rules(settings=settings)
    record.save(update_fields=["break_minutes"])
    return segment


@transaction.atomic
def stop(employee, by, now=None):
    """Close the running stretch at the current minute. Returns it.

    The break is worked out here and not before, because this is the first
    moment the day has a length to work one out from.
    """
    tz = zone_for(employee)
    moment = now or local_now(tz)

    segment = open_stretch(employee, moment)
    if segment is None:
        raise ClockError(_("There is no shift running, so there is nothing to stop."))

    at = moment.time().replace(second=0, microsecond=0)
    if at == segment.start:
        # Zero-length is not a stretch, and the model refuses it. Somebody who
        # pressed both buttons inside a minute meant to press neither.
        raise ClockError(_(
            "That would be a shift of no length. If you started it by mistake, "
            "remove the stretch on the day instead."
        ))

    segment.end = at
    segment.save(update_fields=["end"])

    record = segment.day
    record.refresh_from_db()
    settings = OrgSettings.current()
    record.apply_break_rules(settings=settings)
    record.unconfirm()
    record.save(update_fields=["break_minutes"])
    return segment


def _refuse_if_covered(record, at):
    """Refuse a start inside a stretch already recorded on that day.

    The case is real and looks like nothing: somebody types 08:00–16:00 in the
    morning "so it is done", then presses Start out of habit at 09:15. Without
    this the day quietly holds two stretches covering the same hours and reports
    seven hours that were never worked — the exact double-count that
    ``_SegmentFormSet`` refuses on the typing form, arriving by the other door.
    """
    minute = at.hour * 60 + at.minute
    for existing in record.segments.all():
        if existing.end is None:
            continue
        first = existing.start.hour * 60 + existing.start.minute
        last = existing.end.hour * 60 + existing.end.minute
        if last <= first:
            last += 24 * 60
        if first <= minute < last:
            raise ClockError(_(
                "You already have %(span)s recorded today, and now is inside it. "
                "Correct the day by hand instead."
            ) % {"span": str(existing)})
