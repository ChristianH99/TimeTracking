"""The plan: who is expected in, on which day, between which hours.

A ``Shift`` is an *intention*. It is what the manager arranged and what the
employee agreed to; it is not a record of anything that happened. The record
lives in ``apps.timesheets`` and the two are deliberately separate rows.

The temptation is to make them one — the roster writes a row, the employee ticks
it, the same row is now the timesheet — and it is wrong in a way that only shows
up in an argument. Once the plan and the record are one row, confirming a shift
*overwrites the plan*, and the question "what were you actually asked to work?"
has no answer. A manager who edits a rostered shift after somebody has confirmed
it silently rewrites what they agreed to. Keeping them apart means the timesheet
can always say "you were rostered 08:00–14:00 and you have entered 08:00–15:30",
which is the sentence the whole app exists to be able to print.

So: the roster is copied *from*, never *into*. ``apps.timesheets.DayRecord``
holds the copy.
"""

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.employees.models import Employee


def minutes_between(start, end):
    """Length of a start–end pair in minutes, on the wall clock.

    An end at or before the start crosses midnight: a shift from 22:00 to 06:00
    is eight hours, not minus sixteen.

    **This is the date-free answer**, and it is the right one only where there is
    no date to be had — a roster preview of a pattern, a test about the rule
    itself. Anything that knows which date it is talking about should ask
    ``apps.timesheets.zones.elapsed_minutes`` instead, which measures between two
    instants and therefore gets the two nights a year the clocks move right.

    Kept as a name rather than deleted because it is the rule's plain statement
    and several docstrings point at it, but it **delegates** rather than
    reimplementing: two subtractions in two files is two chances to fix one and
    not the other, and the one that stays wrong is the night shift.
    """
    from apps.timesheets.zones import elapsed_minutes

    return elapsed_minutes(None, start, end, tz=None)


class Shift(models.Model):
    """One stretch of one day that one person is expected to work.

    Several per person per day is allowed and not an edge case: a split shift —
    in for the morning, back for the late afternoon — is the normal shape in a
    kindergarten. So there is no unique constraint on (employee, date), and
    anything counting a day's rostered hours has to sum the shifts rather than
    read one.
    """

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="shifts",
        verbose_name=_("employee"),
    )
    date = models.DateField(_("date"))
    start = models.TimeField(_("from"))
    end = models.TimeField(_("to"))
    note = models.CharField(
        _("note"), max_length=100, blank=True,
        help_text=_("Shown on the card — “group 2”, “outing”, anything the shift needs saying about."),
    )

    class Meta:
        ordering = ["date", "start", "employee__first_name"]
        verbose_name = _("shift")
        verbose_name_plural = _("shifts")
        indexes = [
            # The planner fetches one week for everybody; the timesheet fetches
            # one person's week. Both are covered by the first index, and the
            # second is what makes "my shifts" not a table scan once there are
            # a few years of them.
            models.Index(fields=["date"]),
            models.Index(fields=["employee", "date"]),
        ]

    def __str__(self):
        return f"{self.employee} {self.date} {self.start:%H:%M}–{self.end:%H:%M}"

    def clean(self):
        if self.start and self.end and self.start == self.end:
            raise ValidationError({"end": _("A shift needs a length.")})

    @property
    def minutes(self):
        """How long the shift is, in real elapsed minutes.

        Measured between instants rather than by subtracting clock readings, so
        that a night shift rostered across one of the two nights the clocks move
        is planned at what it will actually be worked — seven hours in March and
        nine in October, not eight both times. The plan and the record have to
        answer this the same way or the timesheet reports a difference from the
        roster that nobody made. See ``apps/timesheets/zones.py``.
        """
        from apps.timesheets.zones import elapsed_minutes, zone_for

        return elapsed_minutes(self.date, self.start, self.end, zone_for(self.employee))

    @property
    def crosses_midnight(self):
        """Whether this shift ends on the following date.

        Worth a property rather than a comparison written wherever it is needed:
        the planner has to draw such a card differently (it belongs to the day
        it *starts*, which is not obvious from a card reading 22:00–06:00) and
        the timesheet has to not treat it as an impossible entry.
        """
        return self.end <= self.start

    @classmethod
    def week(cls, monday, employees=None):
        """Every shift in the seven days from ``monday``, grouped for the planner.

        Returns ``{date: {employee_id: [shift, …]}}`` — two levels, because the
        planner draws a column per date and a card per shift stacked inside it,
        and doing that from a flat list means a scan of the whole week per cell.

        One query. The planner is the page most likely to grow slow, since it is
        the only one that shows everybody at once.
        """
        days = [monday + dt.timedelta(days=offset) for offset in range(7)]
        shifts = cls.objects.filter(date__gte=days[0], date__lte=days[-1])
        if employees is not None:
            shifts = shifts.filter(employee__in=employees)
        grouped = {day: {} for day in days}
        for shift in shifts.select_related("employee"):
            grouped[shift.date].setdefault(shift.employee_id, []).append(shift)
        return grouped

    @classmethod
    def copy_week(cls, source_monday, target_monday, employees=None):
        """Duplicate a week's shifts onto another week. Returns how many.

        The one bulk gesture the planner offers, and it exists because a roster
        is mostly the same week repeated — typing it out again is the single
        biggest waste of a manager's time this app can remove.

        It **adds** rather than replacing, and the page says so before doing it.
        Replacing would be the tidier implementation and would silently discard
        a fortnight somebody had already adjusted by hand; adding leaves a
        visible duplicate that takes one drag to fix. A destructive default with
        no undo is not one this app should choose for somebody.
        """
        offset = (target_monday - source_monday).days
        source = cls.objects.filter(
            date__gte=source_monday, date__lte=source_monday + dt.timedelta(days=6),
        )
        if employees is not None:
            source = source.filter(employee__in=employees)
        copies = [
            cls(employee_id=shift.employee_id, date=shift.date + dt.timedelta(days=offset),
                start=shift.start, end=shift.end, note=shift.note)
            for shift in source
        ]
        cls.objects.bulk_create(copies)
        return len(copies)
