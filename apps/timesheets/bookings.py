"""Turning a column of comings and goings into the day's segments.

The timesheet's bookings cell is a punch list: 08:00 coming, 12:00 going, 12:30
coming, 17:00 going. The database keeps pairs (``WorkSegment``), because every
rule in this app is about a *stretch* — the break thresholds, the overlap check,
the comparison against the roster, and ``elapsed_minutes`` measuring across the
night the clocks move. This module is the one door between the two, and
``DayRecord.bookings`` is the other direction.

**A punch list is not free-form and the pairing is what makes it a day.** Two
comings in a row is not a day with a longer first stretch; it is a missing
going, and the honest answer is to say so rather than to guess which of the two
was meant. Every refusal below is a state the pairing cannot read:

* a going with no coming before it,
* two comings with no going between them,
* a coming and a going at the same moment, which is a stretch with no length.

Two unfinished comings — the state ``_SegmentFormSet._check_one_running``
refuses on the day form — cannot arise here at all: the second one is already
"two comings in a row", and the alternation makes it unrepresentable rather
than merely refused.

The one thing that is *not* an error is a trailing coming with no going. That is
a shift in progress, and it is stored as it always was: a segment with a null
``end``.

**The list is read in the order it is given, not sorted.** A night shift's going
is at 06:00 and its coming at 22:00, and sorting by the clock would put the day
back to front — the same reason ``WorkSegment.position`` is a field rather than
an ordering by ``start``.
"""

import datetime as dt

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from apps.timesheets.timeparse import (
    TimeFormatError, as_time, clock, parse_time_of_day,
)

COMING = "in"
GOING = "out"


def parse(rows):
    """``[("in", "08:00"), ("out", "1230"), …]`` → ``[(time, time|None), …]``.

    Each row is a ``(kind, raw)`` pair straight off the POST. The times are read
    by ``apps.timesheets.timeparse``, so ``830``, ``8:30``, ``8,5`` and ``8.30``
    all mean half past eight here exactly as they do in every other box in the
    app — there is no format setting and this is not the place to invent one.

    Blank rows are dropped rather than refused. The pop-up leaves an empty row
    at the bottom for the next punch, and making somebody delete it before they
    can save would be the app complaining about its own affordance.
    """
    punches = []
    for kind, raw in rows:
        text = (raw or "").strip()
        if not text:
            continue
        if kind not in (COMING, GOING):
            raise ValidationError(_(
                "Every booking has to say whether it is a coming or a going."
            ))
        try:
            minutes = parse_time_of_day(text)
        except TimeFormatError as error:
            raise ValidationError(_(
                "“%(value)s” is not a time this app can read. Try 8:30, 8,5 or 830."
            ) % {"value": text}) from error
        punches.append((kind, as_time(minutes)))
    return _pair(punches)


def _pair(punches):
    """Fold an alternating list into ``(start, end|None)`` pairs.

    The error messages name the time rather than the row number. On a day with
    six punches on it "the third one" is the start of a hunt, and the person
    reading the message is looking at a column of times.
    """
    pairs = []
    open_at = None

    for kind, value in punches:
        if kind == COMING:
            if open_at is not None:
                raise ValidationError(_(
                    "There are two comings in a row — %(first)s and %(second)s — with "
                    "no going between them. Add the going, or remove one of them."
                ) % {"first": clock(_minutes(open_at)), "second": clock(_minutes(value))})
            open_at = value
            continue

        if open_at is None:
            raise ValidationError(_(
                "The going at %(time)s has no coming before it. A day starts with a "
                "coming."
            ) % {"time": clock(_minutes(value))})
        if value == open_at:
            raise ValidationError(_(
                "The coming and the going at %(time)s are the same moment, so that "
                "stretch has no length."
            ) % {"time": clock(_minutes(value))})
        pairs.append((open_at, value))
        open_at = None

    if open_at is not None:
        # Not an error. This is the shift somebody is standing in, and it is the
        # same state the Start button writes — a segment with no end, worth zero
        # minutes until it has one.
        pairs.append((open_at, None))

    return pairs


def _minutes(value):
    return value.hour * 60 + value.minute


def spans(pairs):
    """The pairs as ``(from, to)`` minute offsets on one timeline.

    An end at or before its start crosses midnight and is pushed into the next
    day, and a stretch with no end runs to the end of time. Both are the rules
    ``_SegmentFormSet._check_overlaps`` uses and they are here for the same
    reason: comparing ``time`` objects reports every night shift as an overlap
    and lets the one real overlap through whenever a night shift is on the day.
    """
    out = []
    for start, end in pairs:
        first = _minutes(start)
        if end is None:
            out.append((first, None))
            continue
        last = _minutes(end)
        if last <= first:
            last += 24 * 60
        out.append((first, last))
    return out


def check_overlaps(pairs):
    """Refuse two stretches covering the same minute.

    Two overlapping stretches double-count the overlap into the day's gross,
    which is what the break rules and the balance are computed from — so the
    error is silent and arrives as an unexplained surplus at the end of the
    month.
    """
    ordered = sorted(spans(pairs), key=lambda pair: pair[0])
    for index, (first_start, first_end) in enumerate(ordered):
        for second_start, _second_end in ordered[index + 1:]:
            if first_end is not None and second_start >= first_end:
                break
            raise ValidationError(_(
                "Two of those stretches overlap. The overlapping time would be "
                "counted twice, so the day cannot be added up."
            ))


def check_clock_change(date, pairs, tz):
    """Refuse a clock reading the spring-forward skipped on that date.

    02:30 on the last Sunday in March is not a time that happened, and a shift
    claiming to have started then is a shift measuring an hour short. ``ZoneInfo``
    resolves it and carries on without raising, so this is the only place
    anybody finds out. The same check ``_SegmentFormSet._check_clock_change``
    makes, against the same nights.
    """
    from apps.timesheets.zones import nonexistent

    for start, end in pairs:
        if nonexistent(date, start, tz):
            raise ValidationError(_(
                "The clocks went forward on %(date)s, so %(time)s did not happen that "
                "night. Use the time you actually looked at."
            ) % {"date": date.strftime("%d.%m.%Y"), "time": start.strftime("%H:%M")})
        if end is None:
            continue
        # A stretch running past midnight ends on the following date, so it is
        # that date's clock change that could have skipped its going.
        on = date + dt.timedelta(days=1) if end <= start else date
        if nonexistent(on, end, tz):
            raise ValidationError(_(
                "The clocks went forward on %(date)s, so %(time)s did not happen that "
                "night. Use the time you actually looked at."
            ) % {"date": on.strftime("%d.%m.%Y"), "time": end.strftime("%H:%M")})


def clean(date, rows, tz):
    """Everything above, in the order a day has to satisfy it.

    Returns the pairs ready for ``DayRecord.set_bookings``. Raises
    ``ValidationError`` with a message naming the times involved, because the
    person reading it is looking at a column of times and not at row numbers.
    """
    pairs = parse(rows)
    check_overlaps(pairs)
    check_clock_change(date, pairs, tz)
    return pairs
