"""§3 and §5 ArbZG — the two limits this app can answer from what it holds.

§4's break was always computed; these two never were, and they are the pair an
*Arbeitsschutzbehörde* actually asks about. The data has been sitting there the
whole time — a day's worked minutes, and the instant one day's work stopped
against the instant the next day's started — and nothing looked at it.

**Flagged, never refused, and that direction is the whole design.** The tempting
implementation refuses to save an eleven-hour day. It is wrong, and wrong in the
way that costs the most: §16 ArbZG requires a record of the time *actually
worked*, so software that refuses the entry does not prevent the eleventh hour —
somebody worked it either way — it destroys the only evidence that it happened,
and leaves the employer with a tidy timesheet and no answer. The unlawful day has
to be recordable. What the app owes is that nobody can say afterwards that it
went unnoticed, which is a flag on the row and a count in the footer.

That is also, as it happens, exactly what the June 2026 ArbZG draft asks for: an
employer running *Vertrauensarbeitszeit* must have measures that **detect**
breaches of the maximum hours and the rest period. Detect, not prevent.

**Two levels, because the two statutes say different things.**

*Caution* is a day over eight hours. §3 s.1 sets the working day at eight; s.2
permits ten, provided the average over six calendar months or 24 weeks comes back
to eight. So a nine-hour day is not unlawful — it is unlawful *unless* it is paid
back, and the app cannot yet say whether it was. Colouring it as a breach would
cry wolf on every busy Tuesday in Germany.

*Breach* is a day over ten hours, or a rest period under eleven. Both are
ceilings with no averaging behind them: §3 s.2's ten hours is the outer limit of
the averaging rule itself, and §5(1)'s eleven hours is per rest, not per average.

**The 24-week average is not here**, and it is the half that decides whether the
cautions were lawful. It needs a window that crosses months and contracts, and it
belongs with the balance rather than with a row. It is listed in `docs/AUDIT.md`.

**§5(2) is not modelled either, and flagging anyway is the right answer.** Care
homes, hospitals and — arguably — a *Kindergarten* may shorten the rest to ten
hours, but only against compensation within a calendar month. An employer inside
that exception still has to know *which* nights were short in order to show the
compensation, so a flag is what they want even where the day was permitted. The
message names §5 so that somebody who is inside the exception can read the flag
as the record it is rather than as an accusation.
"""

import datetime as dt

from django.utils.translation import gettext_lazy as _

from apps.timesheets.hours import hhmm
from apps.timesheets.zones import at as zone_at


# The statute, and deliberately not settings. The break table is configurable
# because §4 sets a floor an employer may be generous about; these two are
# ceilings, and a house that could raise them would be configuring its way out
# of the law rather than into it.
ORDINARY_DAY_MINUTES = 8 * 60      # §3 s.1
MAXIMUM_DAY_MINUTES = 10 * 60      # §3 s.2
MINIMUM_REST_MINUTES = 11 * 60     # §5(1)


CAUTION = "caution"
BREACH = "breach"


def _instants(record, tz):
    """``(first clock-in, last clock-out)`` of a day, as aware datetimes.

    Either may be ``None``: a day with no segments has no first, and a day whose
    last stretch is still running has no last.

    **Walked in ``position`` order with a day offset carried along**, the same
    way ``DayRecord.shape`` walks the gaps and for the same reason. A night
    shift's stretches read 22:00–02:00, 03:00–06:00 on the clock, and three of
    those four readings belong to the following date; taking each segment's own
    ``end <= start`` as the only test would put the second stretch back on the
    first date and make the day's last clock-out twenty hours before its first
    clock-in.
    """
    date = record.date
    first = last = None
    offset = 0
    previous_end = None

    for segment in record.segments.all():
        start = segment.start.hour * 60 + segment.start.minute
        # Beginning earlier on the clock than the last stretch ended means the
        # clock has gone round: this stretch is on the next date.
        if previous_end is not None and start < previous_end:
            offset += 1
        if first is None:
            first = zone_at(date + dt.timedelta(days=offset), segment.start, tz)
        if segment.end is None:
            # A running stretch. There is no clock-out yet, and guessing one
            # would put a rest period on the page that changes every refresh.
            break
        end = segment.end.hour * 60 + segment.end.minute
        if end <= start:
            offset += 1
        last = zone_at(date + dt.timedelta(days=offset), segment.end, tz)
        previous_end = end

    return first, last


def rest_minutes(previous, record, tz):
    """Minutes between the end of one day's work and the start of the next's.

    ``None`` when either side has nothing to measure from — no previous record,
    no segments on it, a stretch still running, or a day nobody has clocked into
    yet. That is an absence of evidence and not a rest of nought: a day with no
    row is a day nobody has answered for, and inventing eleven hours for it would
    be the app agreeing with a record that does not exist.

    **Only the immediately preceding calendar day is consulted.** Walking further
    back would answer for somebody who worked Monday, was off Tuesday and came in
    Wednesday — a rest of two days, which is not a question anybody has. The one
    case it misses is a night shift two rows up, and that shift's own row is
    where it is flagged.

    Converted to UTC before subtracting, for the reason ``zones.elapsed_minutes``
    spells out at length: Python subtracts two aware datetimes sharing a
    ``tzinfo`` by ignoring the offset, which gives the wall-clock answer on
    exactly the two nights this is worth getting right.
    """
    if previous is None or record is None:
        return None
    _, ended = _instants(previous, tz)
    began, _ = _instants(record, tz)
    if ended is None or began is None:
        return None
    span = began.astimezone(dt.timezone.utc) - ended.astimezone(dt.timezone.utc)
    return int(span.total_seconds() // 60)


def for_day(record, previous, tz, worked_minutes=None):
    """Every §3 or §5 flag one date carries, worst first.

    A list of ``{"code", "level", "text"}``. Empty is the ordinary answer and is
    what thirty of thirty-one rows get — which is the point: a marking that
    appeared on every row would be a marking nobody reads.

    ``worked_minutes`` is passed in rather than read off the record because the
    row builder has already computed it and because a day with no hours is
    ``None`` there rather than nought — the two are different statements and only
    one of them is a day to judge.

    **A running day is not judged on its length.** ``worked_minutes`` counts a
    running stretch as nothing, so an eleven-hour shift still in progress reads
    as nought and would be silently fine; flagging it at Stop rather than during
    is the honest moment. The rest period *is* still checked, because its
    question is about when the day began and that is already known.
    """
    flags = []

    running = bool(record and record.is_running)
    if worked_minutes and not running:
        if worked_minutes > MAXIMUM_DAY_MINUTES:
            flags.append({
                "code": "over-maximum",
                "level": BREACH,
                "text": _(
                    "%(worked)s worked. §3 ArbZG allows ten hours at the very most, "
                    "and no average makes an eleventh hour lawful."
                ) % {"worked": hhmm(worked_minutes)},
            })
        elif worked_minutes > ORDINARY_DAY_MINUTES:
            flags.append({
                "code": "over-ordinary",
                "level": CAUTION,
                "text": _(
                    "%(worked)s worked. §3 ArbZG sets the day at eight hours and "
                    "allows ten only if the average across 24 weeks comes back to "
                    "eight — so this day needs a shorter one behind it."
                ) % {"worked": hhmm(worked_minutes)},
            })

    rest = rest_minutes(previous, record, tz)
    if rest is not None and rest < MINIMUM_REST_MINUTES:
        flags.append({
            "code": "short-rest",
            "level": BREACH,
            "text": _(
                "Only %(rest)s off since the previous day’s work ended. §5 ArbZG "
                "requires eleven hours of uninterrupted rest."
            ) % {"rest": hhmm(max(0, rest))},
        })

    return flags


def worst(flags):
    """The severity of a list of flags: ``"breach"``, ``"caution"`` or ``""``.

    What a cell keys its colour off, so the template never has to loop to find
    out whether anything on the row is serious.
    """
    if any(flag["level"] == BREACH for flag in flags):
        return BREACH
    if flags:
        return CAUTION
    return ""
