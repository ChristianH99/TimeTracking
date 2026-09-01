"""``{{ minutes|hhmm }}`` — the one way a template writes a duration.

A filter rather than a property on the models, because a duration is minutes
everywhere it is stored and a string only where it is read.

The rule this exists to enforce is that **no template ever divides by 60**. A
page that writes ``{{ record.worked_minutes }}`` puts a raw minute count where a
duration belongs — "455" instead of "07:35" — and it is not obviously wrong,
merely wrong, and it stays that way until somebody tries to add two of them up by
eye. ``config/tests.py`` has no way to catch that, so the filter is made
convenient enough that there is no reason to reach past it.

There were two more filters here, ``hours`` and ``hours_signed``, which took the
reader's own notation from ``Preferences.hours_format``. They went with the
preference: see ``apps/timesheets/hours.py``.
"""

from django import template

from apps.timesheets import hours as hours_module

register = template.Library()


@register.filter(name="hhmm")
def hhmm(minutes):
    """A duration as ``07:35``. The whole of how this app writes one.

    It began as the timesheet's own notation against a per-person preference
    everywhere else, and it is now the only one: ten columns of figures read
    down the page only line up when every one of them is the same width, and
    mixing 7,5 with 12,25 in a column somebody is scanning for a wrong number
    defeats the point of the column.
    """
    if minutes is None:
        return ""
    return hours_module.hhmm(minutes)


@register.filter(name="hhmm_signed")
def hhmm_signed(minutes):
    """The same, with a ``+`` in front of a surplus.

    For the saldo columns, where the sign *is* the message and the colour must
    not be the only thing carrying it — a reader who cannot tell red from green
    still has to get the right answer out of the column.
    """
    if minutes is None:
        return ""
    text = hours_module.hhmm(minutes)
    return f"+{text}" if minutes > 0 else text
