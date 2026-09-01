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


class DayLock(models.Model):
    """One date of one person's timesheet, closed to further change.

    **A row per day, and not a row per month**, although a month is what a
    manager locks. The question the app asks is always *"may this day be
    changed"* and never *"is this month locked"* — every write path, every cell
    on the page and every refusal is about one date. A month row with a table of
    per-day exceptions beside it would be two representations of that one
    answer, and the day they disagree is the day somebody edits a day they
    should not have. A month is thirty-one of these written at once, which is
    one query; unlocking a day is deleting one of them.

    **Who and when are on every row**, because the whole point of a lock is that
    somebody can be told who closed the month and when — and because a day
    unlocked and locked again afterwards was genuinely locked at two different
    moments by possibly two different people. Storing that once per month would
    be storing the first answer for all of them.

    Deleting is how a day is unlocked; there is no ``is_locked`` flag to go
    stale. A row exists or it does not.
    """

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="locks",
        verbose_name=_("employee"),
    )
    date = models.DateField(_("date"))

    locked_at = models.DateTimeField(auto_now_add=True)
    locked_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+", editable=False,
    )

    class Meta:
        ordering = ["date"]
        verbose_name = _("locked day")
        verbose_name_plural = _("locked days")
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"], name="one_lock_per_day",
            ),
        ]
        indexes = [models.Index(fields=["employee", "date"])]

    def __str__(self):
        return f"{self.employee} {self.date}"

    @classmethod
    def dates_between(cls, employee, first, last):
        """The locked dates in a range, as a set.

        One query for a whole month, which is what every page drawing a month
        needs — asking per row would be thirty-one.
        """
        return set(
            cls.objects
            .filter(employee=employee, date__gte=first, date__lte=last)
            .values_list("date", flat=True)
        )

    @classmethod
    def is_locked(cls, employee, date):
        return cls.objects.filter(employee=employee, date=date).exists()

    @classmethod
    def lock(cls, employee, dates, by):
        """Lock every one of ``dates`` that is not locked already.

        ``ignore_conflicts`` rather than check-then-write: two managers pressing
        the button in the same second would otherwise raise a unique constraint
        error on a page that had done nothing wrong, and the second press means
        the same thing as the first.

        Returns how many rows were new, which is what the message counts.
        """
        existing = set(
            cls.objects.filter(employee=employee, date__in=dates)
            .values_list("date", flat=True)
        )
        fresh = [date for date in dates if date not in existing]
        cls.objects.bulk_create(
            [cls(employee=employee, date=date, locked_by=by) for date in fresh],
            ignore_conflicts=True,
        )
        return len(fresh)


class LockedDay(ValidationError):
    """Raised by anything that would change a day somebody has closed.

    A ``ValidationError`` and not a ``PermissionDenied``, because that is what
    it is: the day is not somebody else's, it is *finished*. The message says
    what to do instead, which is to ask for it to be unlocked.
    """


def assert_unlocked(employee, date):
    """Refuse to touch a locked day. The one gate, called by every write path.

    A function rather than a check repeated in each view, because the exposure a
    forgotten one would create is exactly the one the lock exists to prevent —
    and it would be invisible, since the page would simply save. ``DayRecord``
    calls it on every save and delete as well, so a path that forgot it is
    caught by the model rather than by nobody.
    """
    if DayLock.is_locked(employee, date):
        raise LockedDay(_(
            "%(date)s is locked and cannot be changed. Ask a manager to unlock that "
            "day — locking a month is how the hours in it are signed off."
        ) % {"date": date.strftime("%d.%m.%Y")})


class FutureDay(ValidationError):
    """Raised by anything that would put hours on a day that has not happened.

    Separate from ``LockedDay`` because they are different sentences and the fix
    is different: a locked day is *finished* and a manager can reopen it, while
    a future day is *not yet* and nobody can do anything but wait.
    """


def assert_not_future(date, today=None):
    """Refuse hours on a day that has not happened yet.

    Bookings are a record of when somebody was demonstrably at work (§16 ArbZG)
    and nobody has been at work tomorrow. A correction is the same claim with
    the clock left out of it, so it is refused on the same dates — and the
    comment goes with them, because it sits on the row and saves through the
    same door.

    **A status is not covered**, deliberately: "I am on holiday next week" is a
    sentence about a day that has not happened and is the whole point of booking
    leave in advance.

    **Not enforced in ``DayRecord.save``**, which is where the lock's backstop
    is, and the difference is worth stating. A lock is a promise that a signed-off
    month cannot be altered, so it is worth catching a forgotten view from the
    model. This is a rule about what a *person may type*: the seeder writes the
    current week — including tomorrow, when today is a Monday — and a fixture
    dated relative to today is not somebody entering hours in advance. Guarding
    the model would turn that into a seeder that fails one day in seven.
    """
    today = today or dt.date.today()
    if date > today:
        raise FutureDay(_(
            "%(date)s has not happened yet, so there are no hours to record for it. "
            "A status — time off, sickness — can be set for a future day; hours "
            "cannot."
        ) % {"date": date.strftime("%d.%m.%Y")})


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

    # **A correction is not a booking, and it is stored apart from one.**
    #
    # Somebody who forgot to clock out, drove to a second site, or was sent home
    # and paid for the afternoon has time that belongs on the day and was never
    # read off a clock. Writing it into the bookings would be the tidier
    # implementation and it would destroy the one thing the bookings are for:
    # they are a record of when this person was demonstrably here (§16 ArbZG),
    # and a stretch nobody stood through is not that.
    #
    # Signed, because the correction that matters most is the one that takes
    # time *off* a day somebody over-recorded, and an unsigned field would make
    # the only way to do that a doctored booking.
    #
    # **A reason is required for every non-zero value**, enforced in ``clean``
    # and by the form. A number added to a timesheet with nothing saying why is
    # the one entry nobody can defend afterwards, and the person who has to
    # defend it is usually not the person who typed it.
    correction_minutes = models.SmallIntegerField(
        _("correction"), default=0,
        help_text=_("Minutes added to — or taken off — this day by hand."),
    )
    correction_reason = models.CharField(
        _("why"), max_length=200, blank=True,
        help_text=_("Required whenever there is a correction."),
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

    def save(self, *args, force=False, **kwargs):
        """Refused on a locked day, unless the caller says it means it.

        **The backstop, not the gate.** Every view that writes a day calls
        ``assert_unlocked`` first, because that is where a useful message can be
        put on the page somebody is looking at. This is here because a view that
        forgot to would otherwise save in silence — and a lock one forgotten
        line can be walked past is not a lock.

        ``force`` is for callers that are not somebody editing a day: a fixture,
        a data migration, or a seeder.
        """
        if not force:
            assert_unlocked(self.employee, self.date)
        return super().save(*args, **kwargs)

    def delete(self, *args, force=False, **kwargs):
        """The same. Clearing a day is a change to it — the largest one."""
        if not force:
            assert_unlocked(self.employee, self.date)
        return super().delete(*args, **kwargs)

    def clean(self):
        """A correction with nothing saying why is refused.

        Checked here rather than only on the form, because the form is not the
        only door — a management command, a fixture or the admin can all write
        one, and a figure on a timesheet that nobody can account for is exactly
        the entry that gets asked about years later.
        """
        if self.correction_minutes and not (self.correction_reason or "").strip():
            raise ValidationError({
                "correction_reason": _(
                    "Say why the day was corrected. A correction nobody can account "
                    "for is the one entry on a timesheet that cannot be defended."
                ),
            })

    # -- what it adds up to ----------------------------------------------

    @property
    def gross_minutes(self):
        """Clock-in to clock-out, summed over the segments. Break not removed.

        A stretch still running contributes nothing — see ``WorkSegment.minutes``.
        """
        return sum(segment.minutes for segment in self.segments.all())

    @property
    def shape(self):
        """``(blocks, gaps)`` — how the day was actually split up.

        ``blocks`` is the length of each unbroken stretch of work and ``gaps``
        is the time between them, so ``len(gaps)`` is one less than
        ``len(blocks)``. **The break rules need the shape and not the totals**:
        a day of 08:30–15:00 and then 16:00–17:00 has an hour off in it and
        still contains six and a half hours worked straight through, and a
        break taken afterwards cannot pay for one that was never taken. See
        ``OrgSettings.required_break``.

        Walked in ``position`` order — the order the stretches happened — and
        not in clock order. A night shift's second stretch starts earlier on the
        clock than its first, so sorting by time would put the day back to front
        and read the gap as nineteen hours; ``position`` is a field rather than
        an ordering by ``start`` for exactly this.

        A gap that comes out negative crossed midnight and is pushed into the
        next day, the same rule ``elapsed_minutes`` follows. A stretch with no
        end stops the walk: it is worth nothing yet, and nothing has happened
        after it to measure a gap to.
        """
        blocks, gaps = [], []
        previous_end = None
        for segment in self.segments.all():
            if segment.end is None:
                break
            if previous_end is not None and segment.start is not None:
                gap = (
                    (segment.start.hour * 60 + segment.start.minute)
                    - (previous_end.hour * 60 + previous_end.minute)
                )
                if gap < 0:
                    gap += 24 * 60
                gaps.append(gap)
            blocks.append(segment.minutes)
            previous_end = segment.end
        return blocks, gaps

    @property
    def break_taken_minutes(self):
        """Break the person demonstrably took, in minutes.

        The gaps between one going and the next coming — but only those long
        enough to *be* a break. §4 ArbZG lets one be split "in Zeitabschnitte
        von jeweils mindestens 15 Minuten", so a five-minute pause counts
        towards nothing. It is still not worked time: somebody who clocked out
        was not there, and it is out of ``gross_minutes`` either way.
        """
        from apps.organisation.models import MIN_BREAK_CHUNK

        return sum(gap for gap in self.shape[1] if gap >= MIN_BREAK_CHUNK)

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
    def net_minutes(self):
        """The bookings less the break, never below zero.

        The floor matters. A break longer than the day is nonsense a manager can
        type, and letting it go negative would make a week's total quietly
        smaller than the days in it — a figure that is wrong and looks merely
        surprising.

        Kept apart from ``worked_minutes`` because it is the figure the *day*
        was measured at, before anybody corrected it — which is the column the
        timesheet prints beside the correction so the two can be told apart.
        """
        return max(0, self.gross_minutes - self.break_minutes)

    @property
    def worked_minutes(self):
        """What the day is worth: bookings, less the break, plus the correction.

        The order is the whole of it. The break comes off the *bookings*,
        because the break rules are thresholds on time spent here and a
        correction is not time spent here — adding it first would push a day of
        5h50 plus a ten-minute correction over the six-hour tier and deduct a
        break nobody took. The correction goes on afterwards, where it reads as
        what it is.

        Floored at nought for the same reason as ``net_minutes``: a correction
        larger than the day is a typo, and a negative day would make a month's
        total smaller than the days in it.
        """
        return max(0, self.net_minutes + self.correction_minutes)

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
        blocks, gaps = self.shape
        return settings.required_break(blocks, gaps, rules=rules)

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


    # -- bookings ---------------------------------------------------------
    #
    # The timesheet reads a day as a column of **bookings** — a coming, a going,
    # a coming, a going — because that is what somebody standing at a terminal
    # does and what a punch clock prints. The database keeps *segments*, which
    # are the same information with the pairs already made.
    #
    # The two are one representation, not two: ``bookings`` derives the list
    # from the segments and ``set_bookings`` folds a list back into them, so
    # there is nowhere for a stored list of punches and a stored list of
    # segments to disagree. Pairs are what everything else in this app is built
    # on — the break rules, the overlap check, the comparison against the
    # roster, ``elapsed_minutes`` across a clock change — and a flat punch table
    # would have made every one of those re-derive the pairing first.
    #
    # A trailing coming with no going is not a special case here. It is the
    # segment with a null ``end``, which is exactly what a shift in progress
    # already was.

    @property
    def bookings(self):
        """``[{"kind": "in"|"out", "time": time}, …]`` in the order they happened.

        Derived, never stored. A running stretch contributes its coming and no
        going, which is what the page draws as an open row.
        """
        rows = []
        for segment in self.segments.all():
            rows.append({"kind": "in", "time": segment.start})
            if segment.end is not None:
                rows.append({"kind": "out", "time": segment.end})
        return rows

    def set_bookings(self, pairs):
        """Replace the day's segments with ``[(start, end|None), …]``.

        Wholesale rather than a diff, and that is deliberate: the pop-up edits
        the whole column of a day at once, so "these are the bookings now" is
        the statement being made. Reconciling row by row would need a stable
        identity for a punch, which a punch does not have — two people typing
        08:00 twice have not edited one booking.

        Refreshes afterwards for the reason ``from_shifts`` does: the cached
        relation is stale after the write, and anything that reads it — the
        break rules, above all — would compute from the segments that were here
        before.
        """
        self.segments.all().delete()
        WorkSegment.objects.bulk_create([
            WorkSegment(day=self, position=index, start=start, end=end)
            for index, (start, end) in enumerate(pairs)
        ])
        self.refresh_from_db()


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
