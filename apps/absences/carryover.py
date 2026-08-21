"""What last year's untaken leave becomes this year, and when it stops existing.

Everything else in this app's leave accounting is derived — ``Balance`` is a
class and not a table precisely so that a stored figure can never fall out of
step with the absences behind it. **This is the one part that has to be stored**,
and it is worth being explicit about why the exception is not a lapse.

Expiry is an *event*, not a calculation. Three things follow from that and none
of them can be recovered from the absence rows:

* **It has a date.** "Six days lapsed on 31 March" is a thing that happened on a
  particular morning, and re-deriving it in June would answer with today's
  settings, today's contract and today's deadline — so a deadline extended
  afterwards would silently un-expire days that were already gone, and lowering
  the entitlement would expire days retrospectively.
* **Somebody may have extended it**, for one person, for a reason. That is not
  derivable from anything: it is a decision, and the reason is the only record
  there is of why this person's March is different from everybody's.
* **Under German law it may not have expired at all.** Since the
  Bundesarbeitsgericht's Hinweispflicht decisions, statutory leave lapses only
  if the employer demonstrably told the employee what was left and that it was
  about to. This module records whether that notice went out, because an
  employer who cannot show it does not get the expiry — and an app that expired
  the days anyway would be quietly destroying an entitlement that legally still
  exists.

So a ``LeaveCarryOver`` row is a **statement about a year that has closed**. It
is written once, by an explicit act — the year-end page or ``close_leave_year``
— and from then on it is history that a manager can amend and nothing
recalculates behind their back.

---- the two pots ----

Statutory and employer-granted leave are separate columns all the way through,
because they expire on different terms and an employee is always taken to spend
**the one that expires soonest first**. That last rule is not a nicety: spending
the durable pot first would let somebody's protected statutory days lapse while
their contractual extra sat safe, which is the opposite of what the protection
is for.
"""

import datetime as dt
from decimal import Decimal

from django.conf import settings as django_settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class LeaveCarryOver(models.Model):
    """One person, one year, and what came into it from the year before.

    ``year`` is the year the days were carried **into**. A row for 2026 says
    what was left over at the end of 2025 and when it stops being spendable.
    """

    employee = models.ForeignKey(
        "employees.Employee", on_delete=models.CASCADE, related_name="carried_leave",
        verbose_name=_("employee"),
    )
    year = models.PositiveSmallIntegerField(
        _("into the year"),
        help_text=_("The year these days were carried into, not the year they were earned."),
    )

    statutory_days = models.DecimalField(
        _("statutory days carried"), max_digits=5, decimal_places=1, default=Decimal("0"),
    )
    employer_days = models.DecimalField(
        _("the employer’s extra, carried"), max_digits=5, decimal_places=1, default=Decimal("0"),
    )

    # Null means "does not expire", which is a real configuration and not a
    # missing value: an employer who has switched expiry off, or one who knows
    # they never sent the notice, carries the days indefinitely.
    statutory_deadline = models.DateField(
        _("statutory days lapse on"), null=True, blank=True,
    )
    employer_deadline = models.DateField(
        _("the extra lapses on"), null=True, blank=True,
    )

    # **The Hinweispflicht record.** Whether the employee was actually told,
    # before the year ended, how many days they had left and that they were
    # about to lapse. Without it, German case law says the statutory days do not
    # expire — so this is not paperwork, it is the condition on the deadline
    # meaning anything.
    notice_given_on = models.DateField(
        _("they were told on"), null=True, blank=True,
        help_text=_(
            "When they were told what was left and that it would lapse. Without this "
            "the statutory days are treated as not expiring at all."
        ),
    )

    extended_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+", editable=False,
    )
    extended_at = models.DateTimeField(null=True, blank=True, editable=False)
    extension_reason = models.CharField(
        _("why it was extended"), max_length=200, blank=True,
        help_text=_("Required to move a deadline. It is the only record of why this person’s is different."),
    )

    # What was actually dropped, and when it was dropped. Written by the expiry
    # run rather than computed, for the whole reason in the module docstring:
    # a figure recomputed in June answers with June's settings.
    forfeited_statutory = models.DecimalField(
        _("statutory days lost"), max_digits=5, decimal_places=1, default=Decimal("0"),
    )
    forfeited_employer = models.DecimalField(
        _("extra days lost"), max_digits=5, decimal_places=1, default=Decimal("0"),
    )
    forfeited_on = models.DateField(_("lost on"), null=True, blank=True)

    note = models.CharField(_("note"), max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "employee__first_name"]
        verbose_name = _("carried-over leave")
        verbose_name_plural = _("carried-over leave")
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "year"], name="one_carry_over_per_year",
            ),
        ]
        indexes = [models.Index(fields=["employee", "year"])]

    def __str__(self):
        return f"{self.employee} → {self.year}: {self.total_days}"

    # -- what is left of it ----------------------------------------------

    @property
    def total_days(self):
        return Decimal(self.statutory_days) + Decimal(self.employer_days)

    @property
    def is_forfeited(self):
        return self.forfeited_on is not None

    def statutory_available_on(self, day):
        """Statutory days still spendable on that date.

        Zero once the deadline has passed **and the notice was given**. Without
        the notice the deadline does not bite at all, which is the German
        position since the Hinweispflicht decisions and the single most
        expensive thing this module gets right — an employer with no evidence of
        the reminder owes the days, and an app that had already zeroed them
        would have destroyed the only record that they existed.
        """
        if not self.expires_statutory:
            return Decimal(self.statutory_days)
        if self.statutory_deadline and day > self.statutory_deadline:
            return Decimal("0")
        return Decimal(self.statutory_days)

    def employer_available_on(self, day):
        """The employer's extra, still spendable on that date.

        No notice condition here, and that asymmetry is the point: the
        Hinweispflicht protects the *statutory* entitlement. Leave the employer
        granted on top is the employer's to define, and a contract that says it
        dies with the year is lawful.
        """
        if self.employer_deadline and day > self.employer_deadline:
            return Decimal("0")
        return Decimal(self.employer_days)

    @property
    def expires_statutory(self):
        """Whether the statutory deadline means anything for this row."""
        return self.statutory_deadline is not None and self.notice_given_on is not None

    def available_on(self, day):
        return self.statutory_available_on(day) + self.employer_available_on(day)

    @property
    def blocked_by_missing_notice(self):
        """A deadline that is set but cannot bite, because nobody was told.

        Surfaced on the page rather than left implicit. It is the state an
        employer most needs to see: the days are still owed, and they will go on
        being owed until somebody either sends the reminder or writes them off
        deliberately.
        """
        return (
            self.statutory_deadline is not None
            and self.notice_given_on is None
            and Decimal(self.statutory_days) > 0
        )

    def clean(self):
        if self.extension_reason and not (self.statutory_deadline or self.employer_deadline):
            raise ValidationError({
                "extension_reason": _("There is no deadline to extend."),
            })

    def extend(self, by, statutory=None, employer=None, reason=""):
        """Move one or both deadlines, recording who and why.

        The reason is required and that is deliberate. An extension is a
        decision about one person that differs from what everybody else gets,
        and "why is hers 30 June" is a question somebody will ask months later —
        at which point the answer exists only in the head of whoever pressed the
        button.

        Refuses to move a deadline **backwards** past days that have already
        been forfeited: that would be un-recording an event, and the forfeiture
        is the record of a morning on which somebody's days stopped existing.
        """
        if not (reason or "").strip():
            raise ValidationError({"extension_reason": _(
                "Say why. An extension nobody can explain is one nobody can defend."
            )})
        if self.is_forfeited:
            raise ValidationError(_(
                "Those days have already lapsed. Grant new days instead — moving the "
                "deadline now would erase the record of when they went."
            ))
        if statutory is not None:
            self.statutory_deadline = statutory
        if employer is not None:
            self.employer_deadline = employer
        self.extension_reason = reason.strip()
        self.extended_by = by
        self.extended_at = timezone.now()
        self.save()
        return self

    @transaction.atomic
    def forfeit(self, statutory, employer, on=None):
        """Record that these days stopped existing on that date."""
        self.forfeited_statutory = Decimal(statutory)
        self.forfeited_employer = Decimal(employer)
        self.forfeited_on = on or dt.date.today()
        self.save(update_fields=[
            "forfeited_statutory", "forfeited_employer", "forfeited_on", "updated_at",
        ])
        return self

    # -- building the row ------------------------------------------------

    @classmethod
    def for_employee(cls, employee, year):
        """The stored row for that year, or ``None``.

        Never creates. A year that has not been closed has no carry-over, and
        inventing one on a page load would put a write inside a GET and would
        answer with today's settings — see the module docstring.
        """
        return cls.objects.filter(employee=employee, year=year).first()

    @classmethod
    @transaction.atomic
    def close_year(cls, employee, year, settings=None, notice_given_on=None):
        """Work out what ``year`` leaves behind and write the row for ``year + 1``.

        Called by the year-end page and by ``close_leave_year``, never by a page
        that is only reading. It reads the closing year's balance once and turns
        it into two numbers and two dates.

        **What is left is split back into the two pots by spending the perishable
        one first.** Somebody entitled to 30 days of which 20 are statutory, who
        took 12, has 18 left — and those 18 are 8 statutory and 10 employer,
        not 18 of one thing. Assuming the employee spent the statutory days
        first is the reading that protects them: it leaves the *durable* pot
        standing, and getting it the other way round would let protected days
        lapse while the contractual extra sat safe.

        Returns the row, or ``None`` when there is nothing to carry — a row of
        zeros is noise on every page that lists these.
        """
        from apps.absences.models import Balance
        from apps.organisation.models import OrgSettings

        settings = settings or OrgSettings.current()
        balance = Balance(employee, year, settings)

        remaining = balance.remaining
        if remaining <= 0:
            cls.objects.filter(employee=employee, year=year + 1).delete()
            return None

        statutory_entitlement = balance.statutory_entitlement
        taken = balance.taken
        # Perishable first: the statutory pot is drawn down before the extra.
        #
        # **Capped at what is actually left.** Without the `min` the two halves
        # can add up to more than `remaining` — which happens whenever the
        # statutory share is not smaller than the whole, and it is not smaller
        # whenever rounding or an override has brought the total down to meet
        # it. The row then claims more days than the year ever held.
        statutory_left = min(remaining, max(Decimal("0"), statutory_entitlement - taken))
        employer_left = max(Decimal("0"), remaining - statutory_left)

        row, _created = cls.objects.update_or_create(
            employee=employee, year=year + 1,
            defaults={
                "statutory_days": statutory_left,
                "employer_days": employer_left,
                "statutory_deadline": (
                    settings.statutory_deadline(year + 1)
                    if settings.statutory_expires else None
                ),
                "employer_deadline": (
                    settings.employer_deadline(year + 1)
                    if settings.employer_expires else None
                ),
                "notice_given_on": notice_given_on,
            },
        )
        return row


def expire_due(year, on=None, settings=None):
    """Forfeit every carried-over day whose deadline has passed. Returns the rows.

    Run from ``close_leave_year --expire`` or the year-end page. Deliberately a
    separate act from closing the year, because they happen months apart and for
    different reasons: closing records what was left on 31 December, and expiry
    happens on 31 March to whatever of it is still there.

    **Only rows whose deadline can actually bite.** A statutory deadline with no
    notice against it is skipped and reported, not quietly enforced — see
    ``statutory_available_on``.
    """
    from apps.absences.models import Balance
    from apps.organisation.models import OrgSettings

    settings = settings or OrgSettings.current()
    on = on or dt.date.today()
    touched = []

    rows = (
        LeaveCarryOver.objects
        .filter(year=year, forfeited_on__isnull=True)
        .select_related("employee")
    )
    for row in rows:
        balance = Balance(row.employee, year, settings)
        # Only what is *still* unspent can lapse. Somebody who used their
        # carried days in February has nothing left to lose in March, and
        # forfeiting the original figure would take days off a balance that had
        # already been reduced by the same absences.
        unspent = max(Decimal("0"), row.total_days - balance.taken)
        if unspent <= 0:
            continue

        statutory_gone = Decimal("0")
        employer_gone = Decimal("0")
        if row.expires_statutory and row.statutory_deadline and on > row.statutory_deadline:
            statutory_gone = min(unspent, Decimal(row.statutory_days))
        if row.employer_deadline and on > row.employer_deadline:
            employer_gone = min(
                unspent - statutory_gone, Decimal(row.employer_days),
            )
        if statutory_gone <= 0 and employer_gone <= 0:
            continue

        row.forfeit(statutory_gone, max(Decimal("0"), employer_gone), on=on)
        touched.append(row)
    return touched
