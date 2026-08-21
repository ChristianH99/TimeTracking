"""Reading a time the way somebody actually types it.

``8:30``, ``8,5``, ``8.5``, ``0830``, ``830`` and ``8`` are all half past eight,
and this module is the one place that knows it. **There is no format setting and
there must never be one.** Asking somebody which notation they are about to use
is asking them to do the computer's job, and the answer would be wrong the first
time a colleague borrowed the terminal.

---- what is accepted ----

    8:30   08:30   8.30      a colon or the German "8.30 Uhr"
    8,5    8.5     8,50      decimal hours
    0830   830     8         digits alone: HHMM, HMM, or whole hours
    8:30 h  8,5 Std.  17 Uhr  a unit on the end, ignored

---- the one ambiguity, and how it is settled ----

Two digits after a separator are genuinely ambiguous in German. ``8,30`` is
"acht Komma drei null Stunden" to a payroll clerk and "acht Uhr dreißig" to
everybody else, and both readings are ordinary German. So the *context* decides,
because the context is the thing that actually disambiguates it:

* a **time of day** prefers the clock — ``8.30`` is 08:30;
* a **duration** prefers decimal hours — ``8,30`` is 8 h 18.

One digit is not ambiguous in either direction (nobody writes ``8.5`` for five
past eight), so it is always decimal — and note that the two readings *converge*
for the common cases: ``8.5`` and ``8.30`` are both 08:30 as a time of day.
Anything that cannot be minutes falls back to decimal, so ``8.75`` is 8 h 45 in
both.

Being clever about this would still leave ``8.25`` genuinely undecidable, which
is why the rule is only half the answer. The other half is that **every field
normalises what it parsed as soon as you leave it** (``static/js/timeinput.js``),
so the interpretation is on the screen before the form is ever submitted. A
parser that guesses silently is the thing to avoid; one that guesses and shows
its guess is just a parser.

---- why not <input type="time"> ----

Because it rejects ``830`` — and rejects it by *emptying itself*, which is the
same trap as ``type="number"``: the control looks stricter and is the opposite,
because the page cannot even tell you what you typed. These are ``type="text"`` fields validated here.
"""

import datetime as dt
import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

MINUTES_PER_DAY = 24 * 60

# A unit somebody typed after the number. Stripped rather than refused: "8:30 h"
# and "17 Uhr" are what a person writes, and refusing them teaches nothing.
_UNIT = re.compile(
    r"\s*(?:h|hrs?|std\.?|stunden?|uhr|min\.?|minuten?)\s*$", re.IGNORECASE,
)
_CLOCK = re.compile(r"^(\d{1,2})\s*:\s*(\d{1,2})(?::\d{1,2})?$")
_DECIMAL = re.compile(r"^(\d{1,3})\s*[.,]\s*(\d{1,3})$")
_DIGITS = re.compile(r"^(\d{1,4})$")


class TimeFormatError(ValidationError):
    """Refused, with the text that was refused quoted back.

    A message that names the value is the difference between "fix your input"
    and "fix *this*", and on a form with seven boxes on it that is the whole
    difference.
    """

    def __init__(self, raw):
        super().__init__(
            _("“%(value)s” is not a time this app can read. Try 8:30, 8,5 or 830.")
            % {"value": raw},
            code="unreadable_time",
        )


def _clean(raw):
    """The typed text with whitespace and a trailing unit taken off."""
    text = str(raw or "").strip()
    text = text.replace(" ", " ")  # a non-breaking space, which Word pastes
    return _UNIT.sub("", text).strip()


def _split(text):
    """``(whole, fraction_or_None, style)`` for a cleaned string.

    ``style`` is what the *notation* said, before any context is applied:
    ``"clock"`` for a colon, ``"separator"`` for a dot or comma, ``"digits"``
    for bare digits. ``None`` means it is not a time at all.
    """
    if match := _CLOCK.match(text):
        return int(match.group(1)), int(match.group(2)), "clock"
    if match := _DECIMAL.match(text):
        return int(match.group(1)), match.group(2), "separator"
    if match := _DIGITS.match(text):
        return match.group(1), None, "digits"
    return None, None, None


def _from_digits(digits):
    """``(hours, minutes)`` for bare digits.

    ``"8"`` -> (8, 0); ``"830"`` -> (8, 30); ``"0830"`` -> (8, 30);
    ``"1730"`` -> (17, 30).

    One or two digits are whole hours; three or four are HMM and HHMM. That
    split is what makes ``8`` and ``0830`` both work without a setting, and it
    is unambiguous because there is no reading of ``830`` as eight hundred and
    thirty of anything.
    """
    if len(digits) <= 2:
        return int(digits), 0
    return int(digits[:-2]), int(digits[-2:])


def _minutes_from_separator(whole, fraction, prefer_clock):
    """A dot or comma, resolved by context, as ``(hours, minutes)``.

    Both branches return the *same shape* as ``_from_digits`` and the clock
    branch, and that is not tidiness: the first version returned total minutes
    here and an (hours, minutes) pair everywhere else, so every decimal form
    arrived at the ``minutes >= 60`` guard with 510 in the minutes slot and was
    refused. Every single one of ``8,5``, ``8.5`` and ``7,75`` — which is most
    of the reason this module exists.

    See the module docstring for how ``prefer_clock`` settles the ambiguity.
    """
    if prefer_clock and len(fraction) == 2 and int(fraction) < 60:
        return whole, int(fraction)
    # Decimal hours. Decimal rather than float, because 8.1 hours is 486 minutes
    # and a float gets there via 485.99999999999994 — which truncates to 485 and
    # loses a minute of somebody's day, every time, in one direction.
    total = (Decimal(whole) + Decimal(f"0.{fraction}")) * 60
    return divmod(int(total.quantize(Decimal("1"))), 60)


def parse_time_of_day(raw, field_name=None):
    """A clock time, as minutes since midnight. Raises ``TimeFormatError``.

    ``24:00``, ``2400`` and ``24`` are accepted and mean midnight — as the *end*
    of a shift that is a real and common way to write it, and refusing it would
    make somebody write ``23:59`` and lose a minute a day.
    """
    text = _clean(raw)
    if not text:
        raise TimeFormatError(raw)

    whole, fraction, style = _split(text)
    if style is None:
        raise TimeFormatError(raw)

    if style == "digits":
        hours, minutes = _from_digits(whole)
    elif style == "clock":
        hours, minutes = whole, fraction
    else:
        hours, minutes = _minutes_from_separator(whole, fraction, prefer_clock=True)

    total = hours * 60 + minutes
    if minutes >= 60 or total < 0 or total > MINUTES_PER_DAY:
        raise TimeFormatError(raw)
    return total % MINUTES_PER_DAY


def parse_duration(raw, field_name=None):
    """A length of time, in minutes. Raises ``TimeFormatError``.

    Unlike a time of day this is not capped at a day: a contract is never more
    than 24 hours, but the cap belongs on the *field* (where the message can say
    "a day only has 24 hours") rather than here, where it would be a parse error
    for something that parsed perfectly well.
    """
    text = _clean(raw)
    if not text:
        raise TimeFormatError(raw)

    whole, fraction, style = _split(text)
    if style is None:
        raise TimeFormatError(raw)

    if style == "digits":
        hours, minutes = _from_digits(whole)
    elif style == "clock":
        hours, minutes = whole, fraction
    else:
        hours, minutes = _minutes_from_separator(whole, fraction, prefer_clock=False)

    if minutes >= 60:
        raise TimeFormatError(raw)
    return hours * 60 + minutes


# -- turning the answer back into something to look at ---------------------

def as_time(minutes):
    """Minutes since midnight as a ``datetime.time``.

    1440 (midnight at the *end* of a day) becomes 00:00, which is what the rest
    of the app already means by it: ``roster.minutes_between`` reads an end at
    or before the start as crossing midnight.
    """
    return dt.time((minutes // 60) % 24, minutes % 60)


def clock(minutes):
    """``510`` -> ``"08:30"``. The form every field normalises itself to."""
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def duration_clock(minutes):
    """``-840`` -> ``"-14:00"``; ``1500`` -> ``"25:00"``. A *length*, not a time.

    Kept apart from ``clock`` above, which is a time of day, because the two are
    wrong for each other in opposite directions and each is silently wrong:

    * ``clock`` wraps at 24 and drops the sign, because 25:00 is not a time and
      neither is minus half past eight. Used on a duration it renders 25 hours
      as ``01:00`` and fourteen hours *owed* as ``10:00`` — plausible numbers,
      both wrong, neither raising anything.
    * this one pads nothing and keeps the sign outside the colon, because a
      naive divmod gives ``-1:-15`` for a small shortfall.

    ``static/js/hours.js`` makes exactly the same split for the same reason, and
    calls the two halves ``clock`` and ``clockOfDay``. The Python names are the
    other way round for historical reasons and it is not worth a rename; what
    matters is that each has one job.
    """
    minutes = int(minutes)
    sign = "-" if minutes < 0 else ""
    hours, rest = divmod(abs(minutes), 60)
    return f"{sign}{hours}:{rest:02d}"


def hours_text(minutes):
    """``510`` -> ``"8,5"``, in the active language's decimal separator.

    What a *duration* field normalises to, because a contract is written in
    hours and normalising 7.75 to "07:45" would make somebody think they had
    typed a time of day.
    """
    from django.utils.formats import number_format

    value = (Decimal(int(minutes)) / 60).quantize(Decimal("0.01")).normalize()
    return number_format(value)
