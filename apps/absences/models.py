"""Days somebody is not at work, and why.

One model for all four reasons rather than four models, because everything the
app does with an absence is the same regardless of which one it is: draw it on
a calendar, keep it off the roster, stop the timesheet asking for hours, and —
for two of the four — take a day off a balance. The differences are a column.

What separates them is **who may create one and whether it needs deciding**:

* ``HOLIDAY`` — requested by the employee, decided by a manager. Costs leave.
* ``SPECIAL`` — the same, against a named ``SpecialLeaveType`` balance.
* ``SICK`` — *stated* by the employee, then acknowledged by a manager. Costs no
  leave, and **counts from the moment it is reported**: the acknowledgement is a
  receipt, not a permission. An employer does not grant illness. What a manager
  can do is positively refuse to accept it — no Krankmeldung arrived, the dates
  are wrong — and that is a rare act with a note attached, not the default state
  of a report nobody has looked at yet.
* ``CLOSURE`` — created for everybody at once when the workplace shuts. Costs
  leave by default, which is what Betriebsferien normally means, but the
  closure carries a switch because it is not always what they mean.

**A day is only spent if it was a working day.** That single rule is why
``Employee.works_on`` exists and why ``working_days`` below walks the range one
date at a time instead of subtracting two dates. Somebody who does not work
Fridays and books the week off spends four days, not five; a week that contains
Karfreitag costs one fewer again; and somebody rostered nowhere in that week
spends nothing at all. Getting this wrong is not a rounding error — it is an
employee's leave balance, which they will check.
"""

import datetime as dt
from decimal import Decimal

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.absences.carryover import LeaveCarryOver  # noqa: F401  (re-exported)
from apps.employees.models import Employee


class AbsenceKind(models.TextChoices):
    HOLIDAY = "holiday", _("Holiday")
    SPECIAL = "special", _("Special leave")
    SICK = "sick", _("Sick")
    CLOSURE = "closure", _("Workplace closed")
    # Time off against hours already worked. Requested and approved like a
    # holiday and costs no leave — see LEAVE_KINDS below for why that is the
    # whole of it.
    OVERTIME = "overtime", _("Time off in lieu")


class RequestStatus(models.TextChoices):
    REQUESTED = "requested", _("Waiting for approval")
    APPROVED = "approved", _("Approved")
    # **An approved absence somebody has asked to have taken off again.** It is
    # still in force — it credits its hours and it still costs the leave — until
    # a manager agrees to remove it, which is the whole reason it is a status of
    # its own rather than a straight withdrawal. An employee who could withdraw
    # an approved absence unilaterally could take back a day the roster was
    # already built around; one who cannot ask at all has to find their manager
    # by other means and the app has no record that they tried.
    CANCELLING = "cancelling", _("Cancellation requested")
    REJECTED = "rejected", _("Declined")
    WITHDRAWN = "withdrawn", _("Withdrawn")


# The two statuses under which an absence actually counts. A cancellation that
# has been *asked for* changes nothing until it is granted — the day is still
# booked, the hours are still credited and the leave is still spent — so every
# question of the form "does this absence count" asks for this pair and not for
# APPROVED alone. Written once because the four places that ask are four chances
# to forget the second half, and forgetting it hands somebody their leave back
# the moment they ask to cancel it.
IN_FORCE = frozenset({RequestStatus.APPROVED, RequestStatus.CANCELLING})

# Everything a manager has still to answer. A cancellation is a decision like
# any other and belongs on the same list — one waiting on somebody's desk is
# exactly as unfinished as a request nobody has looked at.
UNDECIDED = frozenset({RequestStatus.REQUESTED, RequestStatus.CANCELLING})


# The kinds that come off a leave balance. Sickness does not, and neither does a
# closure the employer has said it will pay for — `Absence.costs_leave` is the
# whole answer and this is the half of it that does not depend on a row.
#
# **Time off in lieu is deliberately absent from this set**, and it is worth
# saying why it is not simply missing. It costs no leave because it is not leave:
# it is hours already worked, being taken back. The app does not credit it
# against a balance either, and it does not need to — a day with no hours entered
# already counts as a shortfall against the contracted hours, which is exactly
# the arithmetic that "using up overtime" is. Recording the kind only *names*
# what the shortfall was for, so a manager reading the week sees a day that was
# agreed rather than a day somebody failed to answer for. Building an overtime
# account on top of that would be inventing a second set of figures to disagree
# with the first.
LEAVE_KINDS = frozenset({AbsenceKind.HOLIDAY, AbsenceKind.SPECIAL, AbsenceKind.CLOSURE})


class BankHoliday(models.Model):
    """One public holiday, as a row.

    A table rather than a call to ``bankholidays.holidays()`` on every page, and
    the reason is not performance. The computation is Land-level and two of the
    thirteen days are decided *municipally* — Fronleichnam in parts of Saxony
    and Thuringia, Mariä Himmelfahrt in Catholic Bavaria. A business in one of
    those four Länder needs to be able to correct the answer, so the calculation
    generates a first draft and the administrator has the last word. A computed
    property could not be corrected at all.

    ``is_generated`` marks the ones that came from the calculation, so
    regenerating a year can replace those and leave a hand-added row alone.
    """

    date = models.DateField(_("date"), unique=True)
    name = models.CharField(_("name"), max_length=100)
    is_generated = models.BooleanField(
        default=True, editable=False,
        help_text=_("Generated rows are replaced when the year is generated again; added ones are not."),
    )

    class Meta:
        ordering = ["date"]
        verbose_name = _("public holiday")
        verbose_name_plural = _("public holidays")

    def __str__(self):
        return f"{self.date} {self.name}"

    @classmethod
    def dates_between(cls, first, last):
        """The set of public holiday dates in a range.

        A set, and fetched once per calculation rather than per day: the leave
        balance walks a year one date at a time and would otherwise run about
        260 queries to answer one number.
        """
        return set(
            cls.objects.filter(date__gte=first, date__lte=last)
            .values_list("date", flat=True)
        )

    @classmethod
    def generate(cls, year, land):
        """Write the year's holidays for a Land. Returns ``(added, removed)``.

        Only ever touches generated rows. A holiday somebody added by hand —
        the municipal Fronleichnam this app cannot know about — survives being
        regenerated, which is the entire point of the ``is_generated`` column.
        A hand-added row on a date the calculation also produces wins: the
        generated one is not written, because the administrator has already
        answered that date.
        """
        from apps.absences.bankholidays import holidays

        first = dt.date(year, 1, 1)
        last = dt.date(year, 12, 31)

        kept = set(
            cls.objects.filter(date__gte=first, date__lte=last, is_generated=False)
            .values_list("date", flat=True)
        )
        removed = cls.objects.filter(
            date__gte=first, date__lte=last, is_generated=True,
        ).delete()[0]

        rows = [
            cls(date=day, name=name, is_generated=True)
            for day, name in holidays(year, land)
            if day not in kept
        ]
        cls.objects.bulk_create(rows)
        return len(rows), removed


class CompanyClosure(models.Model):
    """A period when the workplace is shut and nobody is expected in.

    Distinct from a public holiday because it applies to *this* organisation
    and because it usually costs the staff leave: two weeks of Betriebsferien in
    August is two weeks nobody may book elsewhere, and the normal arrangement is
    that it comes out of the annual entitlement. ``deducts_leave`` exists
    because that is normal rather than universal — a day the employer closes for
    its own reasons and pays for is a real thing, and an app that could not say
    so would force it to be recorded as something it is not.

    Saving one **materialises an ``Absence`` for every employee it touches**
    rather than being consulted at read time. Two reasons, and the second is the
    important one: the balance page can then show the closure beside the days
    somebody chose, in one list, without a second code path; and an employee who
    joins in September does not retroactively acquire the August closure.
    """

    name = models.CharField(_("name"), max_length=100)
    start_date = models.DateField(_("from"))
    end_date = models.DateField(_("to"))
    deducts_leave = models.BooleanField(
        _("comes out of their leave"), default=True,
        help_text=_("Off for a day the employer closes and pays for."),
    )

    class Meta:
        ordering = ["-start_date"]
        verbose_name = _("closure")
        verbose_name_plural = _("closures")

    def __str__(self):
        return f"{self.name} ({self.start_date} – {self.end_date})"

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("The end is before the start.")})

    def apply(self):
        """Create or refresh the absence rows this closure implies.

        Idempotent: running it again after the dates change moves the rows
        rather than adding a second set, and an employee who has since left
        loses theirs. Employees are filtered to those actually employed across
        the period, because ``Employee.works_on`` already answers "not yet
        started" and "already left" and this only avoids writing rows that would
        all be worth zero days.
        """
        self.absences.exclude(employee__is_active=True).delete()
        for employee in Employee.objects.filter(is_active=True):
            Absence.objects.update_or_create(
                closure=self, employee=employee,
                defaults={
                    "kind": AbsenceKind.CLOSURE,
                    "start_date": self.start_date,
                    "end_date": self.end_date,
                    "status": RequestStatus.APPROVED,
                    "reason": self.name,
                },
            )


class Absence(models.Model):
    """One person away for one continuous stretch of dates.

    Inclusive of both ends, which is how everybody says it out loud — "off from
    the 3rd to the 7th" is five dates — and a half-open range here would be an
    off-by-one waiting to be introduced by whoever writes the next page.
    """

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="absences",
        verbose_name=_("employee"),
    )
    kind = models.CharField(
        _("reason"), max_length=10, choices=AbsenceKind.choices, default=AbsenceKind.HOLIDAY,
    )
    # Only for SPECIAL, and required for it — a special leave day that does not
    # say which entitlement it came out of cannot be counted against one.
    special_type = models.ForeignKey(
        "organisation.SpecialLeaveType", null=True, blank=True,
        on_delete=models.PROTECT, related_name="absences",
        verbose_name=_("which"),
    )
    closure = models.ForeignKey(
        CompanyClosure, null=True, blank=True,
        on_delete=models.CASCADE, related_name="absences", editable=False,
    )

    start_date = models.DateField(_("from"))
    end_date = models.DateField(_("to"))

    # **A half day, and only on a single date.** Somebody taking the Friday
    # afternoon off spends half a day of leave and works the morning, and an app
    # that could only book whole days would make them choose between losing half
    # a day they did work and losing half a day of entitlement they did not
    # spend.
    #
    # Restricted to a one-date absence on purpose. The general version — half at
    # the start of a range, half at the end — is four more states and every one
    # of them has to be right in ``working_days``, in the timesheet's credited
    # hours and in the closure materialiser. "Wednesday afternoon, then Thursday
    # and Friday" is two rows here, which is one more click and no ambiguity at
    # all about what was booked.
    is_half_day = models.BooleanField(
        _("half a day"), default=False,
        help_text=_("Half of that one day. Only for a single date."),
    )

    status = models.CharField(
        _("status"), max_length=10,
        choices=RequestStatus.choices, default=RequestStatus.REQUESTED,
    )
    reason = models.CharField(_("note"), max_length=200, blank=True)

    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True, editable=False)
    decided_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+", editable=False,
    )
    decision_note = models.CharField(_("reply"), max_length=200, blank=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = _("absence")
        verbose_name_plural = _("absences")
        indexes = [
            # The two lookups every page does: one person's year, and everybody
            # on one date (the roster and the team week).
            models.Index(fields=["employee", "start_date"]),
            models.Index(fields=["start_date", "end_date"]),
        ]

    def __str__(self):
        return f"{self.employee} {self.get_kind_display()} {self.start_date}–{self.end_date}"

    def clean(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": _("The end is before the start.")})
        if self.kind == AbsenceKind.SPECIAL and self.special_type_id is None:
            raise ValidationError({
                "special_type": _("Say which special leave this is, or it cannot be counted."),
            })
        if self.is_half_day and self.start_date != self.end_date:
            raise ValidationError({
                "is_half_day": _(
                    "A half day is one date. Book the whole days as one absence and the "
                    "half day as another."
                ),
            })
        if self.kind != AbsenceKind.SPECIAL and self.special_type_id is not None:
            # Not merely untidy: the balance page counts SPECIAL rows per type,
            # and a holiday carrying a type would be subtracted from a balance
            # it was never meant to touch.
            raise ValidationError({
                "special_type": _("Only special leave names a leave type."),
            })

    # -- what it costs ---------------------------------------------------

    @property
    def costs_leave(self):
        """Whether this absence comes off an entitlement.

        Sickness never does, and neither does time off in lieu — one is not a
        choice and the other is hours already worked. A closure does unless the
        employer said otherwise. A request that was declined or withdrawn does
        not — and neither does one still waiting, which is why the balance page
        shows "pending" as a separate figure rather than folding it into what is
        left. Somebody whose request is refused must not find that they have
        already spent the days.

        An absence somebody has asked to *cancel* still costs the leave. The
        days come back when the manager agrees, not when the asking starts —
        otherwise the balance would move on a press nobody had answered yet.
        """
        if self.status not in IN_FORCE:
            return False
        if self.kind in (AbsenceKind.SICK, AbsenceKind.OVERTIME):
            return False
        if self.kind == AbsenceKind.CLOSURE:
            return bool(self.closure and self.closure.deducts_leave)
        return True

    def dates(self):
        """Every date in the range, both ends included."""
        span = (self.end_date - self.start_date).days
        return [self.start_date + dt.timedelta(days=offset) for offset in range(span + 1)]

    def portion_of(self, day):
        """How much of that day this absence takes: ``1``, ``0.5`` or ``0``.

        The one place the half day turns into a number. Everything that counts
        days and everything that credits hours goes through it, so a half day
        cannot be half in the balance and whole on the timesheet.
        """
        if not (self.start_date <= day <= self.end_date):
            return Decimal("0")
        return Decimal("0.5") if self.is_half_day else Decimal("1")

    def working_days(self, holiday_dates=None):
        """How much entitlement this absence actually spends, as a ``Decimal``.

        The three subtractions, in one place:

        * a date the contract gives no hours is not a day off — somebody who
          does not work Fridays loses nothing by being away on one;
        * a public holiday is not a day off either, for the same reason: they
          were not due in;
        * a date outside their employment does not count, which
          ``Employee.works_on`` already answers.

        …and then the half day halves whatever is left, which for a half day is
        always exactly one date.

        A ``Decimal`` rather than an ``int``, and that is the change a half day
        forces: 0.5 has to survive being added to 2 and compared against an
        entitlement, and doing that in floats is how a balance page ends up
        reading 17.499999999999996 days.

        ``holiday_dates`` is passed in by anything looping — the balance walks a
        whole year and must not run a query per day.
        """
        if holiday_dates is None:
            holiday_dates = BankHoliday.dates_between(self.start_date, self.end_date)
        total = Decimal("0")
        for day in self.dates():
            if day in holiday_dates or not self.employee.works_on(day):
                continue
            total += self.portion_of(day)
        return total

    def days_charged(self, holiday_dates=None):
        """``working_days`` if it costs leave, otherwise zero.

        The two are separate because the *length* of a sick absence is worth
        showing on a page even though it costs nothing, and a single method
        returning zero for it would make the timesheet say somebody was ill for
        no days.
        """
        if not self.costs_leave:
            return Decimal("0")
        return self.working_days(holiday_dates)

    # -- what it is worth in hours ---------------------------------------

    @property
    def credits_hours(self):
        """Whether a day of this counts as time worked on the timesheet.

        **Yes for everything except time off in lieu**, and each half of that is
        load-bearing:

        * Sickness credits the contracted hours because §3 EFZG says the
          employee is paid as though they had worked them — an app that showed a
          fortnight's flu as a hundred hours of shortfall would be reporting a
          debt that does not exist.
        * Holiday credits them for the same reason under §11 BUrlG, and a
          closure the employer declared credits them because the employer is the
          one who shut the door.
        * **Time off in lieu credits nothing, and that is its entire mechanism.**
          It is hours already worked being taken back, so the day *must* read as
          a shortfall — that shortfall is the overtime being spent. Crediting it
          would cancel the draw-down and leave the app inventing a second set of
          figures to disagree with the first.

        **Nothing credits until it is approved, sickness included.** That is a
        deliberate reversal of an earlier decision, which credited a reported
        sick day immediately on the argument that illness is a fact rather than
        a permission. It is one absence type behaving unlike every other, and
        the cost of that was paid twice over: the timesheet had to say two
        different things about what a pending pill meant, and a report entered
        against the wrong dates credited hours until somebody noticed. One rule
        for every kind is worth more than the days between reporting an illness
        and a manager pressing the button — and it makes that button matter,
        which is the point of asking for it.

        **The consequence is real and is the price of the rule**: a fortnight's
        flu shows as a shortfall for as long as it takes a manager to answer.
        `docs/COMPLIANCE.md` records that under §3 EFZG, because the figure a
        timesheet shows in the meantime is not a debt the employee owes.
        """
        if self.kind == AbsenceKind.OVERTIME:
            return False
        return self.status in IN_FORCE

    def credited_minutes(self, day, contracted_minutes_for_day):
        """Contracted minutes this absence hands back for that one date.

        Half of them for a half day, which is the point of ``portion_of`` being
        one method: the hours and the balance are two readings of one number and
        must not be able to disagree.
        """
        if not self.credits_hours:
            return 0
        portion = self.portion_of(day)
        if not portion:
            return 0
        return int((Decimal(contracted_minutes_for_day) * portion).quantize(Decimal("1")))

    # -- deciding --------------------------------------------------------

    @property
    def is_decidable(self):
        """Anything still waiting on a manager — a request, or a cancellation."""
        return self.status in UNDECIDED

    @property
    def is_cancelling(self):
        return self.status == RequestStatus.CANCELLING

    def _record_decision(self, status, by, note):
        self.status = status
        self.decided_at = timezone.now()
        self.decided_by = by
        self.decision_note = note
        self.save(update_fields=["status", "decided_at", "decided_by", "decision_note"])

    def decide(self, approved, by, note=""):
        """Approve or decline a request, recording who and when.

        Records the decider even for an approval, because "who agreed to this"
        is the question asked months later when a balance is disputed, and it is
        unanswerable from a status column alone.
        """
        self._record_decision(
            RequestStatus.APPROVED if approved else RequestStatus.REJECTED, by, note,
        )

    def decide_cancellation(self, agreed, by, note=""):
        """Answer a request to take an approved absence off again.

        Agreeing withdraws it; refusing puts it back exactly as it was, which is
        why refusing is ``APPROVED`` and not a state of its own — an absence
        whose cancellation was declined is an ordinary approved absence, and
        inventing "approved, but somebody once asked to cancel it" would be a
        state nothing else in the app knows how to read.

        Withdrawn rather than deleted, the same as every other route out: the
        record still says the conversation happened.
        """
        self._record_decision(
            RequestStatus.WITHDRAWN if agreed else RequestStatus.APPROVED, by, note,
        )

    def cancel(self, by):
        """Take it off outright — a manager acting rather than answering.

        The employee's own route is to *ask* (``CANCELLING``); this is the other
        end of it, for a manager who would only be answering their own request a
        press later. It still records who, because "who took this off" is the
        same question as "who agreed to it" and is asked in the same argument.
        """
        self._record_decision(RequestStatus.WITHDRAWN, by, self.decision_note)


def year_bounds(year):
    """The first and last date of a leave year.

    A calendar year, stated in one place rather than assumed in five. German
    leave entitlement is annual and almost always the calendar year; the
    carry-over rules that make it not quite (§7 BUrlG's 31 March) are about when
    *last* year's days expire, which this app deliberately does not model — see
    the standing decision in CLAUDE.md.
    """
    return dt.date(year, 1, 1), dt.date(year, 12, 31)


class Balance:
    """What one employee's leave year looks like. Not a model — it is derived.

    Storing a balance would mean keeping it in step with every absence written,
    withdrawn, approved and declined, and with every change to the contract that
    moves the entitlement underneath it. Every one of those is a chance for the
    stored figure and the absences to disagree, and when they do, the number on
    the page is wrong with nothing on the page to show it. Derived, they cannot
    disagree — the cost is one query per employee per year, which is nothing.
    """

    def __init__(self, employee, year, settings=None):
        from apps.organisation.models import OrgSettings

        self.employee = employee
        self.year = year
        self.settings = settings or OrgSettings.current()
        first, last = year_bounds(year)

        holiday_dates = BankHoliday.dates_between(first, last)
        # Overlapping rather than contained: an absence from 28 December to 3
        # January belongs to both years, and each year counts the days that fall
        # in it. `working_days` walks dates, so it does the clipping itself as
        # long as the row is fetched at all.
        absences = list(
            employee.absences
            .filter(start_date__lte=last, end_date__gte=first)
            .select_related("special_type", "closure")
        )

        # The *year's* entitlement, not the contract's full-year figure. It
        # differs whenever somebody joined mid-year or their hours changed, and
        # in both cases the full-year figure is the wrong number on the one page
        # people use to decide whether they can afford a fortnight off.
        # The *year's* entitlement, not the contract's full-year figure. It
        # differs whenever somebody joined mid-year or their hours changed, and
        # in both cases the full-year figure is the wrong number on the one page
        # people use to decide whether they can afford a fortnight off.
        self.this_year = employee.leave_days_in_year(year, self.settings)
        # The *year's* protected share, weighted the same way `this_year` is.
        # The full-year figure here made a July joiner's 14-day entitlement
        # carry "20 statutory days" — a row adding up to more than it came from.
        self.statutory_entitlement = employee.statutory_days_in_year(year, self.settings)

        # What last year left behind, if the year has been closed. `None` is the
        # ordinary state for a year nobody has closed yet, and it means zero —
        # never "unknown", because a page that could not say would be a page
        # showing a balance it does not stand behind.
        self.carried = LeaveCarryOver.for_employee(employee, year)
        today = dt.date.today()
        # Asked "as at today" rather than "as at the end of the year", so that
        # the figure on the page is what is spendable *now*. Days that lapsed on
        # 31 March are gone in April and the page says so; asking as at 31
        # December would go on showing them all year.
        as_at = min(max(today, first), last) if first <= last else today
        self.carried_days = self.carried.available_on(as_at) if self.carried else Decimal("0")
        self.carried_lost = (
            Decimal(self.carried.forfeited_statutory) + Decimal(self.carried.forfeited_employer)
            if self.carried else Decimal("0")
        )
        # Days brought in from a previous contract, counted **only** in the year
        # the figure was true. Adding it every year would hand somebody their
        # joining figure again each January; adding it to no year loses it.
        # After that first year whatever is left of it carries forward through
        # `LeaveCarryOver` like anybody else's remainder.
        self.opening_days = employee.opening_leave_in_year(year)
        self.entitlement = self.this_year + self.carried_days + self.opening_days
        self.taken = Decimal("0")
        self.pending = Decimal("0")
        self.sick_days = Decimal("0")
        self.pending_sick_days = Decimal("0")
        self.overtime_days = Decimal("0")
        self.pending_overtime_days = Decimal("0")
        self.special_taken = {}

        for absence in absences:
            days = absence.working_days(holiday_dates)
            if absence.kind == AbsenceKind.SICK:
                # Counted once it has been agreed, the same as everything else.
                # A day still waiting is counted into `pending_sick_days` so the
                # page can say it was reported without claiming it as taken —
                # sickness is asked for now, and the figure must not move before
                # somebody answers. See `Absence.credits_hours` for the reversal
                # this belongs to.
                if absence.status in IN_FORCE:
                    self.sick_days += days
                elif absence.status == RequestStatus.REQUESTED:
                    self.pending_sick_days += days
                continue
            if absence.kind == AbsenceKind.OVERTIME:
                # Counted so the page can say how much was taken, and counted
                # into `pending` while it waits so a manager sees it is asked
                # for — but never into `taken`, which is the leave figure.
                if absence.status in IN_FORCE:
                    self.overtime_days += days
                elif absence.status == RequestStatus.REQUESTED:
                    self.pending_overtime_days += days
                continue
            if absence.kind == AbsenceKind.SPECIAL:
                if absence.status in IN_FORCE:
                    key = absence.special_type_id
                    self.special_taken[key] = self.special_taken.get(key, Decimal("0")) + days
                continue
            if absence.status == RequestStatus.REQUESTED:
                self.pending += days
            elif absence.costs_leave:
                self.taken += days

    @property
    def remaining(self):
        """Entitlement minus what has been approved. **Pending is not
        subtracted**, and that is deliberate: a request that has not been
        decided has not been spent, and showing it as spent means somebody whose
        request is declined sees their days come back — which reads as the app
        having lost them. The page shows pending as its own figure beside this.

        ``entitlement`` here already includes whatever was carried in and is
        still spendable today, and already excludes whatever has lapsed — see
        ``LeaveCarryOver.available_on``.
        """
        return self.entitlement - self.taken

    @property
    def statutory_remaining(self):
        """How much of what is left is the protected part.

        Assumes the perishable pot is spent first, which is the same assumption
        ``LeaveCarryOver.close_year`` makes and for the same reason: it is the
        reading that protects the employee. Getting it the other way round would
        let statutory days lapse while contractual extra sat safe.
        """
        return max(Decimal("0"), self.statutory_entitlement - self.taken)

    @property
    def expiring_soon(self):
        """Carried days with a deadline inside the next eight weeks, or ``None``.

        Eight weeks because the deadline that matters is 31 March and the
        conversation that avoids losing the days has to happen in February. A
        warning that appears on 30 March is a warning about something nobody can
        now do anything about.
        """
        if not self.carried or self.carried.is_forfeited:
            return None
        today = dt.date.today()
        deadlines = [
            day for day in (self.carried.statutory_deadline, self.carried.employer_deadline)
            if day and today <= day <= today + dt.timedelta(weeks=8)
        ]
        if not deadlines or self.remaining <= 0:
            return None
        return min(deadlines)

    @property
    def notice_is_missing(self):
        """Carried statutory days with a deadline nobody can enforce.

        Shown to a manager, not to the employee: the days are still owed, and
        they go on being owed until somebody either sends the reminder or writes
        them off deliberately. It is the state an employer most needs to see and
        the one nothing else on the page would reveal.
        """
        return bool(self.carried and self.carried.blocked_by_missing_notice)

    @property
    def remaining_if_all_approved(self):
        """What is left if everything waiting is granted. The figure somebody
        actually wants before booking one more day."""
        return self.entitlement - self.taken - self.pending

    def special(self):
        """``[(grant, entitled, taken, remaining), …]`` for each granted type."""
        rows = []
        for grant, entitled in self.employee.special_leave_days(self.settings, year=self.year):
            taken = self.special_taken.get(grant.leave_type_id, Decimal("0"))
            rows.append((grant, entitled, taken, entitled - taken))
        return rows
