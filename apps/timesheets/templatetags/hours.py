"""``{{ minutes|hours:hours_style }}`` — the one way a template writes a duration.

A filter rather than a property on the models, because the answer depends on
*who is reading* and a model does not know that. ``hours_style`` comes from the
``apps.employees.context.who`` processor, so every template has it without
asking.

The rule this exists to enforce is that **no template ever divides by 60**. A
page that writes ``{{ record.worked_minutes }}`` puts a raw minute count where a
duration belongs — "455" instead of "7:35" — and it is not obviously wrong,
merely wrong, and it stays that way until somebody tries to add two of them up
by eye. ``config/tests.py`` has no way to catch that, so the filter is made
convenient enough that there is no reason to reach past it.
"""

from django import template

from apps.accounts.models import HoursFormat
from apps.timesheets import hours as hours_module

register = template.Library()


@register.filter(name="hours")
def hours(minutes, style=HoursFormat.DECIMAL):
    """A duration in minutes, written for this reader. Blank for ``None``.

    ``None`` is not zero and must not print as ``0:00``: it is the answer for a
    day nobody has entered anything for, and a timesheet showing a row of zeros
    for an unanswered week reads as a week somebody worked none of.
    """
    if minutes is None:
        return ""
    return hours_module.format_minutes(minutes, style)


@register.filter(name="hours_signed")
def hours_signed(minutes, style=HoursFormat.DECIMAL):
    """The same, with a ``+`` in front of a surplus.

    Only for the balance column, where the sign is the whole message. A bare
    ``0:45`` in a column headed "difference" does not say which way, and reading
    it as overtime when it is a shortfall is the mistake this prevents.
    """
    if minutes is None:
        return ""
    text = hours_module.format_minutes(minutes, style)
    return f"+{text}" if minutes > 0 else text
