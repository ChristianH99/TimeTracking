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


---- the grid ----

The planner is a grid: the week's **time slots** down the side, Monday to Friday
across the top, and in each cell the people placed there. A slot may be split
into **areas** (rooms, groups), and then the cell is one per area.

A person placed in a cell *is* a ``Shift`` — one row per placement, carrying the
slot and area it was placed in. There is deliberately no second table of
"placements" from which shifts are generated: two stored representations of the
plan is two chances for them to disagree, and the one that is wrong would be the
one the timesheet reads. The cost is that somebody placed in three consecutive
slots has three shifts, and anything that wants to say "08:00–12:00" has to join
them up — which is what ``planned_spans`` is for, and what the timesheet reads.
"""

import datetime as dt
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.employees.models import Employee

MINUTES_PER_DAY = 24 * 60

#: Monday to Friday. The grid shows five days, and the week still starts on
#: Monday (see ``apps.timesheets.models.week_monday``) — Saturday and Sunday are
#: simply not columns. A shift on a weekend is still a shift, and the timesheet
#: still reads it; the planner says so rather than hiding it.
GRID_DAYS = 5


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


def _offsets(start, end):
    """A start–end pair as minutes from the start of its own date.

    The end is pushed past 1440 when it is at or before the start, so a night
    shift reads as one stretch running into the next day rather than as two
    clock values in the wrong order. Comparisons between spans of the same date
    are then plain integer comparisons.
    """
    first = start.hour * 60 + start.minute
    last = end.hour * 60 + end.minute
    if last <= first:
        last += MINUTES_PER_DAY
    return first, last


def spans_overlap(a_start, a_end, b_start, b_end):
    """Whether two spans of one date share at least one minute.

    Touching is not overlapping: 07:00–08:00 and 08:00–09:00 are two
    consecutive slots, which is the commonest shape on the grid.
    """
    a_first, a_last = _offsets(a_start, a_end)
    b_first, b_last = _offsets(b_start, b_end)
    return a_first < b_last and b_first < a_last


class AreaIcon(models.TextChoices):
    """The pictures an area can carry.

    Drawn from one SVG sprite (``static/icons/areas.svg``), which is a single
    cached request for the whole page however many cells show an icon — and not
    emoji, which render differently on every device the staff own and cannot be
    coloured to match the page.
    """

    STAR = "star", _("Star")
    MOON = "moon", _("Moon")
    SUN = "sun", _("Sun")
    TREE = "tree", _("Tree")
    PLATE = "plate", _("Lunch plate")
    HEART = "heart", _("Heart")
    FLOWER = "flower", _("Flower")
    CLOUD = "cloud", _("Cloud")
    HOUSE = "house", _("House")
    BOOK = "book", _("Book")
    MUSIC = "music", _("Music")
    BALL = "ball", _("Ball")
    LEAF = "leaf", _("Leaf")
    FISH = "fish", _("Fish")
    APPLE = "apple", _("Apple")
    PALETTE = "palette", _("Palette")


class Area(models.Model):
    """Somewhere people work: a room, a group, the garden.

    Kept across weeks, because "room 1" is the same room every week and a
    manager naming it again each Monday would soon have three spellings of it.
    Which areas a *slot* is split into is decided per slot (``TimeSlot.areas``).
    """

    name = models.CharField(_("name"), max_length=60)
    icon = models.CharField(_("icon"), max_length=20, choices=AreaIcon.choices,
                            default=AreaIcon.STAR)
    position = models.PositiveSmallIntegerField(_("position"), default=0)
    is_active = models.BooleanField(
        _("in use"), default=True,
        help_text=_("Switching this off keeps every week it was used in and stops it being offered."),
    )

    class Meta:
        ordering = ["position", "name"]
        verbose_name = _("area")
        verbose_name_plural = _("areas")

    def __str__(self):
        return self.name

    @property
    def is_used(self):
        """Whether anything refers to it — the condition for refusing a delete."""
        return (
            self.slots.exists() or self.shifts.exists() or self.notes.exists()
        )


class TimeSlot(models.Model):
    """One row of one week's grid: a time range, optionally split into areas.

    Per week rather than fixed, because the manager edits them per week — a
    week with a parents' evening has a late slot the others do not. A new week
    starts from a copy of the last one planned (``views.draft_from``), so in
    practice they are fixed until somebody changes them.
    """

    week = models.DateField(_("week"), help_text=_("The Monday of the week."))
    start = models.TimeField(_("from"))
    end = models.TimeField(_("to"))
    areas = models.ManyToManyField(Area, blank=True, related_name="slots",
                                   verbose_name=_("areas"))

    class Meta:
        # By the clock: the grid is read top to bottom as the day goes by, and
        # an order that could disagree with the times would be a second thing to
        # keep right.
        ordering = ["week", "start", "end", "pk"]
        verbose_name = _("time slot")
        verbose_name_plural = _("time slots")
        indexes = [models.Index(fields=["week"])]

    def __str__(self):
        return f"{self.week} {self.start:%H:%M}–{self.end:%H:%M}"

    def clean(self):
        if self.week and self.week.weekday() != 0:
            raise ValidationError({"week": _("A week starts on a Monday.")})
        if self.start and self.end and self.start == self.end:
            raise ValidationError({"end": _("A time range needs a length.")})

    @classmethod
    def last_planned_before(cls, monday):
        """The most recent week before ``monday`` that has a grid, or ``None``.

        Not simply the week before: the week before may be the summer closure,
        and copying an empty grid forward would be copying nothing.
        """
        return (
            cls.objects.filter(week__lt=monday)
            .order_by("-week").values_list("week", flat=True).first()
        )


class PlannedWeek(models.Model):
    """That a week's grid has been saved at least once.

    The planner opens an unplanned week pre-filled from the last one planned,
    and "unplanned" cannot be read off the slots: a manager who deliberately
    clears a week (a closure, a training week) saves a week with no slots, and
    without this row the next visit would helpfully fill it in again.
    """

    week = models.DateField(_("week"), unique=True)
    saved_at = models.DateTimeField(_("saved"), auto_now=True)

    class Meta:
        verbose_name = _("planned week")
        verbose_name_plural = _("planned weeks")

    def __str__(self):
        return str(self.week)


class CellNote(models.Model):
    """Text in a cell — "Break", "Outing", "Parents' evening".

    One per cell at most: (slot, date, area). Not a unique constraint in the
    database because ``area`` is nullable and SQLite treats every null as
    distinct; ``apps.roster.forms.WeekGrid`` keeps it to one.
    """

    slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, related_name="notes",
                             verbose_name=_("time slot"))
    date = models.DateField(_("date"))
    area = models.ForeignKey(Area, on_delete=models.PROTECT, null=True, blank=True,
                             related_name="notes", verbose_name=_("area"))
    text = models.CharField(_("text"), max_length=100)

    class Meta:
        ordering = ["date", "slot__start", "area__position"]
        verbose_name = _("cell text")
        verbose_name_plural = _("cell texts")

    def __str__(self):
        return self.text


class Shift(models.Model):
    """One stretch of one day that one person is expected to work.

    Several per person per day is allowed and not an edge case: a split shift —
    in for the morning, back for the late afternoon — is the normal shape in a
    kindergarten, and on the grid somebody in three consecutive slots is three
    shifts. So there is no unique constraint on (employee, date), and anything
    counting a day's rostered hours has to sum the shifts rather than read one.

    ``start`` and ``end`` are always the times the person is expected,
    whatever the slot says. Somebody in the 07:15–08:00 slot who starts at
    07:30 has ``start = 07:30``; the slot is where they are drawn and the
    times are what they were asked to work, and the timesheet only ever reads
    the second.
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
    # CASCADE: a placement is drawn in a slot, and a slot the manager removes
    # takes its placements with it — that is what removing a row of the grid
    # means. Nullable because a shift written before the grid, or on a weekend,
    # belongs to no slot and is still a shift.
    slot = models.ForeignKey(
        TimeSlot, on_delete=models.CASCADE, null=True, blank=True,
        related_name="shifts", verbose_name=_("time slot"),
    )
    area = models.ForeignKey(
        Area, on_delete=models.PROTECT, null=True, blank=True,
        related_name="shifts", verbose_name=_("area"),
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
        """Whether this shift ends on the following date."""
        return self.end <= self.start


@dataclass
class PlannedSpan:
    """One unbroken stretch somebody is rostered for on one date.

    What the timesheet shows and copies: consecutive placements on the grid
    joined into the stretch the person will actually work. Somebody in the
    07:00–07:15, 07:15–08:00 and 08:00–12:00 slots was asked to work
    07:00–12:00, and a timesheet that printed three spans would report every
    honest single entry as *different from the roster* — the one line a
    manager reads first, lit up for nothing.

    Duck-types the parts of ``Shift`` the timesheet reads (``start``, ``end``,
    ``note``, ``minutes``), so ``DayRecord.from_shifts`` and
    ``DayRecord.matches_roster`` take either.
    """

    employee: Employee
    date: dt.date
    start: dt.time
    end: dt.time
    note: str = ""

    @property
    def minutes(self):
        from apps.timesheets.zones import elapsed_minutes, zone_for

        return elapsed_minutes(self.date, self.start, self.end, zone_for(self.employee))


def _label(shift):
    return shift.note or (shift.area.name if shift.area_id else "")


def join_shifts(shifts):
    """Join one person's shifts on one date into ``PlannedSpan`` stretches.

    Joined only where one ends exactly where the next begins. A gap is a gap —
    in for the morning and back in the afternoon is two stretches and must stay
    two, because the time between them is not work. Overlaps cannot reach here
    from the planner (``WeekGrid`` refuses somebody in two places at once), and
    are joined all the same if they do, since an hour planned twice is still
    one hour.
    """
    ordered = sorted(shifts, key=lambda s: _offsets(s.start, s.end))
    spans = []
    reach = None
    for shift in ordered:
        first, last = _offsets(shift.start, shift.end)
        label = _label(shift)
        if spans and reach is not None and first <= reach:
            current = spans[-1]
            if last > reach:
                current.end = shift.end
                reach = last
            if label and label not in current.note.split(", "):
                current.note = f"{current.note}, {label}" if current.note else label
            continue
        spans.append(PlannedSpan(
            employee=shift.employee, date=shift.date,
            start=shift.start, end=shift.end, note=label,
        ))
        reach = last
    return spans


def planned_spans(employee, first, last):
    """``{date: [PlannedSpan, …]}`` for one person between two dates inclusive.

    The one door the timesheet goes through to ask what was rostered, so the
    joining happens in exactly one place. One query.
    """
    by_date = {}
    shifts = (
        Shift.objects.filter(employee=employee, date__gte=first, date__lte=last)
        .select_related("employee", "area")
    )
    for shift in shifts:
        by_date.setdefault(shift.date, []).append(shift)
    return {day: join_shifts(rows) for day, rows in by_date.items()}
