"""What was actually worked.

A day is two rows, not one: a ``DayRecord`` (this person, this date, this break,
confirmed or not) and one or more ``WorkSegment``s inside it. The split is the
answer to "they should be able to set as many work hours as they want" — a split
shift is two segments of one day, and it has to be two, because a single
start-and-end pair cannot say that somebody went home between eleven and two.

**The break belongs to the day, not to the segment**, and that is the load-
bearing part of the shape. The break rules are thresholds on a *day's* working
time: somebody who works 08:00–11:00 and 14:00–17:00 has done six hours, and
whether that needs a break is a question about the six, not about either three.
Putting minutes on each segment would make a day's break the sum of two numbers
that were each below every threshold.

**A confirmed day is still editable, and confirmation is not a lock.** The
status says "I agree this is what I worked". A manager correcting a typo
afterwards is ordinary; what must not happen is that the correction is invisible,
which is why ``confirmed_at`` is cleared by any change to the hours and the
person is asked again.
"""

import datetime as dt

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.employees.models import Employee
from apps.organisation.models import OrgSettings
from apps.timesheets.zones import at as zone_at
from apps.timesheets.zones import elapsed_minutes, local_now, zone_for


class EntrySource(models.TextChoices):
    """Where a day's hours came from. Kept because it is the difference between
    "they agreed to what they were asked to work" and "they told us something
    else", and that distinction is the reason the roster and the timesheet are
    separate tables at all."""

    ROSTER = "roster", _("confirmed as rostered")
    MANUAL = "manual", _("entered by hand")


class DayRecord(models.Model):
    """One person, one date. At most one of these per pair.

    Created only when there is something to say. A date with no row is not a
    day of zero hours — it is a day nobody has answered for yet, and the two
    have to look different on a timesheet or somebody's missing Tuesday reads
    as a Tuesday they did not work.
    """

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="days",
        verbose_name=_("employee"),
    )
    date = models.DateField(_("date"))

    break_minutes = models.PositiveSmallIntegerField(
        _("break"), default=0, help_text=_("In minutes."),
    )
    # The single most important boolean on this model. A break of 30 that the
    # rules produced and a break of 30 that somebody typed are the same number
    # and mean different things to whoever signs the timesheet off — so the
    # second is always drawn in --amber and never silently recomputed.
    break_is_override = models.BooleanField(
        _("break entered by hand"), default=False, editable=False,
    )

    source = models.CharField(
        max_length=10, choices=EntrySource.choices, default=EntrySource.MANUAL,
        editable=False,
    )
    note = models.CharField(_("note"), max_length=200, blank=True)

    confirmed_at = models.DateTimeField(null=True, blank=True, editable=False)
    confirmed_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+", editable=False,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["date"]
        verbose_name = _("day")
        verbose_name_plural = _("days")
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"], name="one_record_per_day",
            ),
        ]
        indexes = [models.Index(fields=["employee", "date"])]

    def __str__(self):
        return f"{self.employee} {self.date}"

    # -- what it adds up to ----------------------------------------------

    @property
    def gross_minutes(self):
        """Clock-in to clock-out, summed over the segments. Break not removed.

        A stretch still running contributes nothing — see ``WorkSegment.minutes``.
        """
        return sum(segment.minutes for segment in self.segments.all())

    @property
    def running_segment(self):
        """The stretch that has been started and not stopped, or ``None``.

        At most one, enforced by ``WorkSegmentForm``/``_SegmentFormSet``: two
        open stretches on one day is a state with no reading — pressing Stop
        would have to guess which of them it ended.
        """
        return next((s for s in self.segments.all() if s.end is None), None)

    @property
    def is_running(self):
        return self.running_segment is not None

    @property
    def worked_minutes(self):
        """What actually counts: the span less the break, never below zero.

        The floor matters. A break longer than the day is nonsense a manager can
        type, and letting it go negative would make a week's total quietly
        smaller than the days in it — a figure that is wrong and looks merely
        surprising.
        """
        return max(0, self.gross_minutes - self.break_minutes)

    def required_break(self, settings=None, rules=None):
        """What the rules say this day's break should be.

        Kept as a method rather than resolved into ``break_minutes`` on save,
        because the answer changes when an administrator edits the break table —
        and a timesheet from March should go on showing what March's rules
        produced, while the page can still say "the rules now say something
        else". The stored number is the truth about the day; this is the truth
        about the policy.
        """
        settings = settings or OrgSettings.current()
        return settings.required_break(self.gross_minutes, rules=rules)

    def apply_break_rules(self, settings=None, rules=None):
        """Set the break from the rules, unless somebody has overridden it.

        The guard is the whole method. Recomputing an overridden break is how an
        employee who deliberately entered 60 minutes finds 30 there the next
        time anybody touches the row — with nothing to show that it changed.
        """
        if self.break_is_override:
            return self.break_minutes
        self.break_minutes = self.required_break(settings=settings, rules=rules)
        return self.break_minutes

    @property
    def break_differs_from_rules(self):
        """Whether the stored break is not what the rules would now give.

        What the amber highlighting is driven by. Deliberately *not* the same as
        ``break_is_override``: a break somebody typed that happens to equal the
        computed one needs no highlight, and a break the rules produced under an
        older table does need one once the table changes.
        """
        return self.break_minutes != self.required_break()

    # -- confirming ------------------------------------------------------

    @property
    def is_confirmed(self):
        return self.confirmed_at is not None

    def confirm(self, by):
        """Agree to the day. **Refused while a stretch is still running.**

        Not a nicety: confirming means "this is what I worked", and a day with
        an open stretch has no such figure yet. Allowing it would record an
        agreement to a total that is going to change the moment somebody presses
        Stop — which is precisely the claim ``unconfirm`` exists to prevent
        being made silently.
        """
        if self.is_running:
            raise ValidationError(_(
                "That day is still running — stop the shift first, and then confirm it."
            ))
        self.confirmed_at = timezone.now()
        self.confirmed_by = by
        self.save(update_fields=["confirmed_at", "confirmed_by"])

    def unconfirm(self):
        """Withdraw the agreement, because the hours have changed underneath it.

        Called by every path that edits the times. Leaving a day confirmed after
        its hours were rewritten would make the record say somebody agreed to
        figures they have never seen — which is exactly the claim a timesheet
        exists to be able to make honestly.
        """
        if self.confirmed_at is None:
            return
        self.confirmed_at = None
        self.confirmed_by = None
        self.save(update_fields=["confirmed_at", "confirmed_by"])

    # -- building one from the plan --------------------------------------

    @classmethod
    def from_shifts(cls, employee, date, shifts, by, settings=None, rules=None):
        """Confirm a day *as rostered*: copy the shifts in and agree to them.

        A copy, not a reference. ``apps/roster/models.py`` says why at length —
        the short version is that a timesheet pointing at the plan cannot answer
        "what were you asked to work?" once somebody edits the plan.

        Returns ``None`` when there is nothing rostered, which is not an error:
        it is what "confirm this week" does for the days somebody was not on.
        """
        if not shifts:
            return None
        record, _created = cls.objects.get_or_create(employee=employee, date=date)
        record.segments.all().delete()
        WorkSegment.objects.bulk_create([
            WorkSegment(day=record, position=index, start=shift.start, end=shift.end)
            for index, shift in enumerate(sorted(shifts, key=lambda s: s.start))
        ])
        # The cached relation is stale after the bulk_create above, and
        # apply_break_rules reads it — without this the break is computed from
        # the segments the record had *before*, which for a new one is none at
        # all and gives every confirmed day a break of zero.
        record.refresh_from_db()
        record.source = EntrySource.ROSTER
        record.apply_break_rules(settings=settings, rules=rules)
        record.confirmed_at = timezone.now()
        record.confirmed_by = by
        record.save()
        return record

    def matches_roster(self, shifts):
        """Whether the entered times are exactly what was rostered.

        Drives the one line on the timesheet that a manager reads first: not
        "confirmed" but *"confirmed, and different from what was asked"*. A day
        that matches needs no attention; a day that does not is the whole reason
        anybody opens the page.
        """
        segments = list(self.segments.all())
        # A running stretch has no end to compare, and "still going" is not the
        # same statement as "different from the plan" — sorting a None into the
        # pairs would raise on the comparison anyway.
        if any(segment.end is None for segment in segments):
            return False
        planned = sorted((s.start, s.end) for s in shifts)
        entered = sorted((s.start, s.end) for s in segments)
        return planned == entered


class WorkSegment(models.Model):
    """One continuous stretch of work inside a day.

    ``position`` is a field rather than an ordering by ``start``, for the same
    reason a formset's order is a field: a night shift's second segment can
    start earlier in the clock than its first, and sorting by time would put
    them back to front on the one page where the order is the story.
    """

    day = models.ForeignKey(
        DayRecord, on_delete=models.CASCADE, related_name="segments",
    )
    position = models.PositiveSmallIntegerField(default=0)
    start = models.TimeField(_("from"))

    # **Nullable, and that is the running shift.** Somebody who has pressed
    # Start and not yet pressed Stop is at work right now, and the row has to be
    # able to say so — the alternative is writing a guessed end and correcting
    # it later, which means the timesheet is briefly wrong on purpose and stays
    # wrong for anybody who forgets. A null end is honest: it says the stretch
    # has begun and has no length yet.
    end = models.TimeField(
        _("to"), null=True, blank=True,
        help_text=_("Leave empty while the shift is still running."),
    )

    class Meta:
        ordering = ["position", "start"]
        verbose_name = _("work segment")
        verbose_name_plural = _("work segments")

    def __str__(self):
        if self.end is None:
            return f"{self.start:%H:%M}–…"
        return f"{self.start:%H:%M}–{self.end:%H:%M}"

    def clean(self):
        if self.start and self.end and self.start == self.end:
            raise ValidationError({"end": _("This stretch has no length.")})

    @property
    def is_running(self):
        """Started and not yet stopped."""
        return self.end is None

    @property
    def minutes(self):
        """How long this stretch was, in real elapsed minutes.

        **Zero while it is still running**, deliberately. The tempting answer is
        "up to now", and it is wrong for the one job this property has: it is
        summed into the day's gross, which the break rules and the balance are
        computed from, and a number that changes every time the page is
        refreshed is not something anybody can sign off. What is running is
        shown as running; ``minutes_so_far`` is what a page prints beside it.

        The elapsed time is measured between two *instants* rather than by
        subtracting clock readings, so a shift across the night the clocks move
        comes out at what was actually worked. ``apps/timesheets/zones.py`` says
        why that is worth the two extra queries a page pays for it.
        """
        if self.end is None:
            return 0
        return elapsed_minutes(
            self.day.date, self.start, self.end, zone_for(self.day.employee),
        )

    def minutes_so_far(self, now=None):
        """How long a running stretch has been going. Zero for a finished one.

        Never stored and never summed into anything a form saves — it is a
        number to look at, and it is different by the time the page has
        rendered.
        """
        if self.end is not None:
            return 0
        tz = zone_for(self.day.employee)
        began = zone_at(self.day.date, self.start, tz)
        now = now or local_now(tz)
        # Through UTC, for the reason spelled out in `zones.elapsed_minutes`:
        # subtracting two aware datetimes that share a tzinfo ignores the offset
        # and gives the wall-clock answer, which on the night the clocks go back
        # is an hour short of how long somebody has actually been at work.
        span = now.astimezone(dt.timezone.utc) - began.astimezone(dt.timezone.utc)
        return max(0, int(span.total_seconds() // 60))


def week_monday(day):
    """The Monday of the week ``day`` falls in.

    The week starts on Monday everywhere in this app and is never a setting.
    Germany's week starts on Monday, ``date.weekday()`` numbers it that way, and
    a configurable first day would mean every seven-long list in the codebase
    needing to know which rotation it is in — for a business that will never
    change the answer.
    """
    return day - dt.timedelta(days=day.weekday())
