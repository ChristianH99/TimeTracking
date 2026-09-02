"""Form fields that read a time however it was typed.

They differ only in what they hand back and what they refuse:
``TimeOfDayField`` gives a ``datetime.time``; ``DurationField``,
``SignedDurationField`` and ``BreakMinutesField`` give whole minutes;
``ContractHoursField`` gives a ``Decimal`` of hours. Only the signed one accepts
a leading minus, and only the break one reads bare digits as minutes.

All of them render as ``type="text"``. That is deliberate, and it is the same
lesson ``type="number"`` teaches: the native widgets look like the stricter
choice and are the opposite. ``type="time"``
silently *empties itself* when it cannot read what was typed, so ``830`` becomes
an empty box and the page cannot even tell you what you entered — the one thing
a validation message needs to be able to say.
"""

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.timesheets.timeparse import (
    MINUTES_PER_DAY, TimeFormatError, as_time, clock, duration_clock, hours_text,
    parse_duration,
    parse_time_of_day,
)


class _TextTimeWidget(forms.TextInput):
    """A plain text box that says what it will accept.

    ``autocomplete="off"`` because a browser offering last week's start time
    from a saved-form cache over a box somebody is typing into is noise on the
    one page they use every day. ``data-time-input`` is what
    ``static/js/timeinput.js`` binds to for the normalise-on-blur.
    """

    def __init__(self, kind, attrs=None):
        defaults = {
            "autocomplete": "off",
            "spellcheck": "false",
            "data-time-input": kind,
            "placeholder": "08:30" if kind == "clock" else "8:30",
        }
        defaults.update(attrs or {})
        super().__init__(defaults)


class TimeOfDayField(forms.Field):
    """A clock time. Returns ``datetime.time``."""

    widget = _TextTimeWidget

    def __init__(self, **kwargs):
        kwargs.setdefault("widget", _TextTimeWidget("clock"))
        kwargs.setdefault(
            "help_text", "",
        )
        super().__init__(**kwargs)

    def prepare_value(self, value):
        """What goes into the box.

        A ``time`` is rendered as ``HH:MM``; a string is handed back *exactly as
        typed*. The second half is what makes a rejected form usable: re-showing
        the parsed value would either blank the box or quietly correct it, and
        the message above it says “«830o» is not a time this app can read” about
        something the box no longer contains.
        """
        if hasattr(value, "hour"):
            return f"{value.hour:02d}:{value.minute:02d}"
        return value

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if hasattr(value, "hour"):
            return value
        return as_time(parse_time_of_day(value))


class DurationField(forms.Field):
    """A length of time. Returns whole minutes as an ``int``."""

    widget = _TextTimeWidget

    def __init__(self, *, max_minutes=None, **kwargs):
        kwargs.setdefault("widget", _TextTimeWidget("duration"))
        self.max_minutes = max_minutes
        super().__init__(**kwargs)

    def prepare_value(self, value):
        # `duration_clock`, not `clock`. The latter wraps at 24 hours and would
        # render a 24-hour break tier as "00:00" — a number that is not merely
        # ugly but wrong, and wrong in a way that reads as a value nobody set.
        if isinstance(value, int):
            return duration_clock(value)
        return value

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, int):
            return value
        minutes = parse_duration(value)
        if self.max_minutes is not None and minutes > self.max_minutes:
            raise ValidationError(
                _("That is longer than %(cap)s.")
                % {"cap": duration_clock(self.max_minutes)},
                code="too_long",
            )
        return minutes


class SignedDurationField(forms.Field):
    """A length of time that may be negative. Whole minutes, as an ``int``.

    The one field in the app where a leading ``-`` means something, and it exists
    for exactly one thing: the hours somebody arrives with. Everything else that
    measures a duration measures a stretch of work, and a stretch of work that
    lasted minus two hours is not a case worth being able to express — but a
    person who arrives owing two hours certainly is, and a field that could not
    say so would push that case into a fake week of negative shifts.

    The sign is stripped, the rest is read by ``parse_duration`` exactly as any
    other duration — so ``-14``, ``-14:00``, ``-14,0`` and ``−14`` (with the
    Unicode minus, which is what a spreadsheet pastes) are all the same fourteen
    hours owed. A leading ``+`` is accepted and ignored, because somebody
    writing a balance out by hand will often write one.
    """

    widget = _TextTimeWidget

    # U+2212 MINUS SIGN and U+2013 EN DASH alongside the ASCII hyphen. Both turn
    # up in text pasted out of Excel and out of a PDF, and refusing them means
    # refusing a value whose sign is perfectly legible on the screen.
    _MINUS = ("-", "\u2212", "\u2013")

    def __init__(self, *, max_minutes=None, **kwargs):
        kwargs.setdefault("widget", _TextTimeWidget("duration"))
        self.max_minutes = max_minutes
        super().__init__(**kwargs)

    def prepare_value(self, value):
        """Written back as ``-14:00``, sign outside the colon.

        ``clock`` already does that — it is the same rule the balance column
        follows, and the reason it exists: a naive divmod gives ``-1:-15`` for a
        small shortfall, which is the sort of thing somebody reads twice and
        then reports.
        """
        if isinstance(value, int):
            return duration_clock(value)
        return value

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, int):
            return value

        text = str(value).strip()
        sign = 1
        if text[:1] in self._MINUS:
            sign, text = -1, text[1:].strip()
        elif text[:1] == "+":
            text = text[1:].strip()
        if not text:
            raise TimeFormatError(value)

        minutes = parse_duration(text)
        if self.max_minutes is not None and minutes > self.max_minutes:
            raise ValidationError(
                _("That is longer than %(cap)s.")
                % {"cap": duration_clock(self.max_minutes)},
                code="too_long",
            )
        return sign * minutes


class ContractHoursField(forms.Field):
    """Hours per weekday on a contract. Returns a ``Decimal`` of hours.

    A ``Decimal`` rather than minutes because that is what ``Employee`` stores
    and what a contract is written in — ``apps/timesheets/hours.py`` explains
    why that one model is the exception to the everything-is-minutes rule.

    Empty is **zero**, not ``None``: a weekday with nothing in it is a day the
    person does not work, which is a real answer and the one every leave
    calculation reads. Requiring seven boxes to be filled with 0 would be asking
    somebody to type the default five times.
    """

    widget = _TextTimeWidget

    def __init__(self, **kwargs):
        kwargs.setdefault("widget", _TextTimeWidget("duration", {"placeholder": "0"}))
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def prepare_value(self, value):
        if isinstance(value, (Decimal, float, int)) and not isinstance(value, bool):
            return hours_text(int(Decimal(str(value)) * 60))
        return value

    def to_python(self, value):
        if value in self.empty_values:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        minutes = parse_duration(value)
        if minutes > MINUTES_PER_DAY:
            raise ValidationError(
                _("A day only has 24 hours."), code="too_long",
            )
        return (Decimal(minutes) / 60).quantize(Decimal("0.01"))


class BreakMinutesField(forms.Field):
    """A break, in minutes. Returns an ``int``.

    The one field where bare digits mean **minutes** rather than hours, and it
    is not an inconsistency: the label says minutes, and nobody has ever meant
    forty-five hours by typing 45 into a box marked "break". Anything with a
    separator in it is still read as a duration, so ``0:45`` and ``0,75`` both
    work for the person who thinks in those.
    """

    widget = _TextTimeWidget

    def __init__(self, **kwargs):
        kwargs.setdefault("widget", _TextTimeWidget("minutes", {"placeholder": "30"}))
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def prepare_value(self, value):
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        return value

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        text = str(value).strip()
        if text.isdigit():
            minutes = int(text)
        else:
            minutes = parse_duration(text)
        if minutes < 0 or minutes > MINUTES_PER_DAY:
            raise ValidationError(
                _("A break cannot be longer than a day."), code="too_long",
            )
        return minutes


class SignedMinutesField(forms.Field):
    """A correction, in minutes, which may be negative. Returns an ``int``.

    ``BreakMinutesField`` with a sign, and both halves of that are deliberate.

    Bare digits are **minutes**, for the same reason they are in a break box:
    the label says minutes and nobody has ever meant thirty hours by typing 30
    into a box marked "correction". Anything with a separator is read as a
    duration, so ``0:30`` and ``1:15`` work for whoever thinks in those.

    The sign is the point of the field. The correction that matters most is the
    one that takes time *off* a day somebody over-recorded, and a field that
    could only add would leave a doctored booking as the only way to do it — a
    booking claiming somebody left earlier than they did, which is the one thing
    the bookings must never be made to say.
    """

    widget = _TextTimeWidget

    # The same three the signed duration field takes, and for the same reason:
    # a Unicode minus is what a spreadsheet pastes and its sign is perfectly
    # legible on the screen.
    _MINUS = ("-", "−", "–")

    def __init__(self, **kwargs):
        kwargs.setdefault(
            # `0:30` and not `30`. Both are read as thirty minutes — bare digits
            # are minutes in this box, as the docstring above says — but a
            # placeholder is an example of the answer, and every duration this
            # app prints is hh:mm. "30" beside a column of 0:30 reads as thirty
            # of something the column never shows.
            "widget", _TextTimeWidget("signed-minutes", {"placeholder": "0:30"}),
        )
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def prepare_value(self, value):
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        return value

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, int) and not isinstance(value, bool):
            return value

        text = str(value).strip()
        sign = 1
        if text[:1] in self._MINUS:
            sign, text = -1, text[1:].strip()
        elif text[:1] == "+":
            text = text[1:].strip()
        if not text:
            raise TimeFormatError(value)

        minutes = int(text) if text.isdigit() else parse_duration(text)
        if minutes > MINUTES_PER_DAY:
            raise ValidationError(
                _("A correction cannot be longer than a day."), code="too_long",
            )
        return sign * minutes


__all__ = [
    "BreakMinutesField", "ContractHoursField", "DurationField",
    "SignedDurationField", "SignedMinutesField", "TimeOfDayField",
    "TimeFormatError",
]
