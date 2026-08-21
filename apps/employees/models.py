"""The people whose time this app tracks, and the contract each of them works.

**An employee is not an account, and that separation is the load-bearing part.**
The obvious model — put the weekly hours on ``auth.User`` — cannot express the
one thing this app has to do on its first day: a manager builds next month's
roster for eleven people, and not one of them has signed in yet. Identities
arrive here from the provider at the moment of somebody's *first token* and not
a second earlier (``apps/accounts/oidc.py`` says why), so an app that could only
roster an account could not be set up at all.

So ``Employee`` stands on its own and ``user`` is nullable. The link is made
either by hand or, far more often, by ``link_by_username`` at the first sign-in.
Until then the row is a perfectly ordinary employee who can be rostered, given
leave and have a timesheet — they simply cannot yet open it themselves.

**The key is the directory name, not an e-mail address.** Synology SSO reads its
accounts from LDAP and what LDAP carries is a username: ``anna.berger``. That is
what a manager types onto the contract and what the provider sends back in
``preferred_username``. An address was the wrong key and this is a correction —
one person may have several addresses, may share one with a spouse, and may not
have one at all, so the address version had to refuse to link in exactly the
cases a small organisation actually has. A directory name is single and stable
by construction.

The reverse also has to work: an account with no employee row is somebody who
can sign in and has nothing to look at. That is the right answer for an
administrator who does not work shifts, and the pages say so rather than
crashing on a missing relation.
"""

import datetime as dt
import re
import unicodedata
from decimal import Decimal

from django.conf import settings as django_settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.organisation.models import OrgSettings

# Monday-first, which is both the German week and ``date.weekday()``'s own
# numbering — so a weekday index never needs converting between the two. Every
# per-day list in this app is seven long and in this order.
WEEKDAYS = (
    (0, _("Monday")),
    (1, _("Tuesday")),
    (2, _("Wednesday")),
    (3, _("Thursday")),
    (4, _("Friday")),
    (5, _("Saturday")),
    (6, _("Sunday")),
)

# The seven field names, in weekday order, so that code can index rather than
# branch. `HOURS_FIELDS[date.weekday()]` is the whole of "how long does this
# person work on that day".
HOURS_FIELDS = ("hours_mon", "hours_tue", "hours_wed", "hours_thu",
                "hours_fri", "hours_sat", "hours_sun")


class Employee(models.Model):
    """One person's contract: which days they work and how long each one is.

    The hours are **seven columns, not one weekly total**, and that is a
    decision rather than denormalisation. A weekly total cannot answer either of
    the two questions the app is built on: whether a given date is a working day
    for this person (which decides whether an absence costs them a day of leave)
    and how long that day is (which is what a rostered shift is measured
    against). Storing 20 hours and a separate "days per week" of 3 loses the
    fact that it is 8, 8 and 4 — and the person who books the Wednesday off has
    then lost eight hours instead of four.
    """

    # Nullable, and the reason is the whole module docstring. SET_NULL rather
    # than CASCADE: deleting an account must never take a timesheet with it.
    # Somebody who has left still worked the hours, and payroll may need them
    # for years after the account is gone.
    user = models.OneToOneField(
        django_settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="employee",
        verbose_name=_("account"),
        help_text=_("Filled in by itself when they first sign in, if the e-mail addresses match."),
    )

    first_name = models.CharField(_("first name"), max_length=100)
    last_name = models.CharField(_("surname"), max_length=100, blank=True)

    # **The sign-in name from the directory, and the key the link is made on.**
    #
    # Not an e-mail address, and that is a correction rather than a preference:
    # Synology SSO takes its accounts from LDAP, and what LDAP carries is a
    # username. An address is something a person may have several of, may share
    # with a spouse, and may not have at all — matching on one meant the app
    # refused to guess in exactly the cases a small organisation actually has.
    # A directory username is single, stable and already unique over there.
    #
    # Unique here (case-insensitively, see Meta) because it *is* the identity:
    # two employees claiming one directory name is a state where the first token
    # to arrive decides who somebody is.
    username = models.CharField(
        _("sign-in name"), max_length=150, unique=True,
        help_text=_(
            "The name from the directory — usually firstname.surname. This is what "
            "recognises them the first time they sign in."
        ),
    )

    is_manager = models.BooleanField(
        _("manages the team"), default=False,
        help_text=_("May plan the roster, see everybody’s timesheets and decide requests."),
    )
    is_active = models.BooleanField(
        _("employed"), default=True,
        help_text=_("Switching this off keeps every hour they have worked and takes them off the roster."),
    )

    # Blank means the house clock, which is what it says for everybody in an
    # ordinary business. Filled in it is the remote colleague: they clock in at
    # nine *their* time, and a start button that wrote the office's nine would
    # be recording a lie about when they were at work.
    time_zone = models.CharField(
        _("time zone"), max_length=64, blank=True,
        help_text=_("Leave empty unless they work in a different one from the workplace."),
    )

    started_on = models.DateField(_("started on"), null=True, blank=True)
    ended_on = models.DateField(
        _("left on"), null=True, blank=True,
        help_text=_("After this date they are not rostered and their leave stops accruing."),
    )

    # -- what they arrived with ------------------------------------------
    #
    # **Nobody starts at nought**, and the app was previously unable to say so.
    # Somebody moving from another contract — a different employer, a different
    # branch of the same one, a spell on an agency payroll — arrives with a
    # figure already agreed: fourteen hours in hand, six days of leave not yet
    # taken. Without somewhere to put it, the only ways to record it are to
    # invent a week of hours they did not work, or to leave the balance wrong
    # and remember the difference. Both are worse than a field.
    #
    # Stored as **minutes, and signed**, like every other duration in this app.
    # Negative is not an error state: somebody can perfectly well arrive owing
    # hours, and a field that could not express it would push that case back
    # into the same two bad workarounds.
    opening_balance_minutes = models.IntegerField(
        _("hours brought with them"), default=0,
        help_text=_(
            "Hours already owed to them, or by them, when they started here. "
            "Leave at nought unless something was agreed."
        ),
    )
    opening_leave_days = models.DecimalField(
        _("leave days brought with them"), max_digits=5, decimal_places=1,
        default=Decimal("0"),
        help_text=_("Days of leave carried in from wherever they were before."),
    )
    # The date both of the above are true *as at*. Almost always the day they
    # started, and that is what the form fills in — but not always: a figure
    # agreed at a contract change part-way through is the same kind of thing,
    # and dating it is what stops it being counted into a year it does not
    # belong to.
    opening_balance_on = models.DateField(
        _("as at"), null=True, blank=True,
        help_text=_("The date those figures were true. Usually the day they started."),
    )

    # An agreed figure that is not the pro-rata one — a contract from before the
    # current policy, or a negotiated extra. Null means "compute it", which is
    # what almost every row says; a number here means the computation is not
    # consulted at all rather than added to.
    leave_days_override = models.DecimalField(
        _("leave days"), max_digits=4, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Leave empty to work it out from the working days. Fill it in only for a contract that says something else."),
    )

    class Meta:
        ordering = ["-is_active", "first_name", "last_name"]
        verbose_name = _("employee")
        verbose_name_plural = _("employees")
        constraints = [
            # Case-insensitive, because a directory does not distinguish
            # `Anna.Berger` from `anna.berger` and neither may this: two rows
            # differing only in case would both match one arriving token, and
            # `link_by_username` would refuse the link for an ambiguity that is
            # really one person typed twice.
            models.UniqueConstraint(
                Lower("username"), name="one_employee_per_sign_in_name",
            ),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username or "—"

    @staticmethod
    def suggest_username(first_name, last_name):
        """``firstname.surname``, folded and stripped of what a directory will not take.

        A *suggestion*, filled into the box when somebody types a name and never
        applied behind their back — the directory is the authority on what an
        account is called, and a house whose convention is `aberger` or
        `berger_a` has to be able to say so. Umlauts are transliterated the way
        German directories usually do (ä → ae), not dropped, because `mller` is
        nobody's account name.
        """
        folded = f"{first_name}.{last_name}".strip(".").lower()
        for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
            folded = folded.replace(source, target)
        folded = unicodedata.normalize("NFKD", folded)
        folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
        return re.sub(r"[^a-z0-9._-]+", "", folded).strip(".")

    @property
    def initials(self):
        """Two letters for the roster card, which is about eleven ems wide."""
        first = (self.first_name or " ")[0]
        second = (self.last_name or " ")[0]
        return (first + second).strip().upper() or "?"

    # -- the contract ----------------------------------------------------
    #
    # The seven columns used to live here and now live on `ContractPeriod`, one
    # row per change with a date on it. Everything below is a question asked *as
    # at a date*, and the date is not optional in spirit even where it defaults:
    # "how many hours on a Wednesday" has a different answer in January and in
    # May for anybody whose contract moved in between, and the version that
    # could not tell them apart rewrote the past every time somebody's hours
    # changed. See `ContractPeriod` for the whole argument.

    def contract_on(self, day=None):
        """The contract in force on that date, or ``None`` before the first one.

        ``None`` is a real answer and every caller treats it as "no hours": it
        is a date before this person's earliest contract, which for a row
        created without a start date is no date at all, and for one created with
        one is the days before they were employed.
        """
        day = day or dt.date.today()
        periods = getattr(self, "_prefetched_objects_cache", {}).get("contract_periods")
        if periods is not None:
            # Ordered newest first by Meta, so the first one that has begun is
            # the one in force. Walking the prefetched list rather than querying
            # is what keeps the balance page — which asks this once per date of
            # the year — down to one query per employee.
            return next((p for p in periods if p.valid_from <= day), None)
        return self.contract_periods.filter(valid_from__lte=day).first()

    @property
    def current_contract(self):
        """What they are on today. The row the contract page shows at the top."""
        return self.contract_on(dt.date.today())

    @property
    def weekly_hours(self):
        contract = self.current_contract
        return contract.weekly_hours if contract else Decimal("0")

    def hours_on_weekday(self, weekday, on=None):
        """Contracted hours for a ``date.weekday()`` index, 0 = Monday.

        ``on`` is the date being asked about. Omitted, it is today's contract —
        which is right for "what is this person on" and wrong for anything
        looking at a past week, so every caller that has a date passes it.
        """
        contract = self.contract_on(on)
        return contract.hours_on_weekday(weekday) if contract else Decimal("0")

    def works_on(self, day):
        """Whether ``day`` is a working day for this person under the contract.

        This is the question the whole leave calculation turns on. Somebody who
        does not work Fridays books a week off and spends four days of leave,
        not five — and the four is *this* method five times, not a division.

        Asked against the contract that was in force *on that day*, so somebody
        who dropped their Wednesdays in April does not retrospectively stop
        having worked them in February.
        """
        if self.ended_on and day > self.ended_on:
            return False
        if self.started_on and day < self.started_on:
            return False
        return self.hours_on_weekday(day.weekday(), on=day) > 0

    @property
    def working_days_per_week(self):
        contract = self.current_contract
        return contract.working_days_per_week if contract else 0

    def working_days_per_week_on(self, day):
        contract = self.contract_on(day)
        return contract.working_days_per_week if contract else 0

    @property
    def weekly_pattern(self):
        """``[(weekday, label, hours), …]``, seven long, for the templates.

        A list rather than seven template lookups, so a page cannot render six
        days by forgetting one — which is exactly the sort of thing that looks
        fine until the one person who works Saturdays opens it.
        """
        contract = self.current_contract
        if contract is None:
            return [(index, label, Decimal("0")) for index, label in WEEKDAYS]
        return contract.weekly_pattern

    def set_hours(self, hours, valid_from=None, note=""):
        """Put this person on these hours from that date. Returns the period.

        ``hours`` is seven ``Decimal``s in weekday order. Writing to the period
        that already starts on that date rather than adding a second one, so
        that correcting a change made this morning is a correction and not a
        second change — two periods starting on one date is a state with no
        reading, and the constraint refuses it anyway.
        """
        valid_from = valid_from or self.started_on or dt.date.today()
        values = {name: Decimal(value or 0) for name, value in zip(HOURS_FIELDS, hours)}
        period, _created = ContractPeriod.objects.update_or_create(
            employee=self, valid_from=valid_from,
            defaults={**values, "note": note},
        )
        return period

    # -- entitlement -----------------------------------------------------

    def annual_leave_days(self, settings=None):
        """What a *full year* of the current contract is worth.

        The figure on the contract page and in the People list — "this contract
        buys 24 days" — and deliberately not the figure the balance uses. It
        knows nothing about when somebody joined or whether their hours changed
        in April; ``leave_days_in_year`` is the one that does.

        The override is checked first and *replaces* rather than adds. A model
        where both applied would make "30 days" on a contract mean 30 plus
        whatever the policy currently says, and the day somebody raises the
        full-time entitlement, every overridden contract moves too.
        """
        if self.leave_days_override is not None:
            return Decimal(self.leave_days_override)
        settings = settings or OrgSettings.current()
        return settings.leave_days_for(self.working_days_per_week)

    def statutory_days_in_year(self, year, settings=None):
        """The protected part of this year's entitlement.

        Weighted across contract changes and clipped to the employment exactly
        as ``leave_days_in_year`` is, because it has to be a *share of that same
        number*. The version that used the full-year statutory figure here gave
        somebody who joined in July an entitlement of 14 days of which "20" were
        statutory — a carry-over row that added up to more than the entitlement
        it came from, and a page that could not be made to balance.

        Never more than the total, for the same reason
        ``OrgSettings.statutory_days_for`` caps: erring towards protection
        cannot cost an employee a day and erring the other way can.
        """
        settings = settings or OrgSettings.current()
        total = self.leave_days_in_year(year, settings)
        if self.leave_days_override is not None:
            # An overridden entitlement says nothing about how much of it is
            # statutory. The safe reading is that the protected minimum still
            # applies up to whatever was agreed.
            return min(total, settings.statutory_days_for(self.working_days_per_week))
        return min(total, self._weighted_in_year(
            year, settings, settings.statutory_days_for,
        ))

    def leave_days_in_year(self, year, settings=None):
        """What they are actually entitled to *in that year*.

        Two things the full-year figure cannot express, and both of them are
        ordinary rather than edge cases:

        * **the contract changed.** Somebody who went from five days to three in
          April is entitled to a quarter of a five-day year plus three quarters
          of a three-day one. Applying today's contract to the whole year is the
          mistake in both directions — it overpays somebody who went up and
          short-changes somebody who went down, and the second is the one that
          gets litigated.
        * **the year is not whole for them.** Somebody who started in October is
          entitled to a twelfth of a year for each full month, which is the
          shape of Paragraph 5 BUrlG. The version that showed them a full year
          was not generous; it was wrong, and wrong on the page they use to
          decide whether they can afford a fortnight at Christmas.

        Each period gets the entitlement its own pattern buys, weighted by how
        much of the year it covered, and the rounding happens **once at the
        end** — rounding each slice up would hand somebody an extra day for
        every time their contract was ever touched.

        An override still replaces the lot: a contract that says 30 days says 30
        days, and second-guessing it by month is not what it agreed to.
        """
        settings = settings or OrgSettings.current()
        if self.leave_days_override is not None:
            return Decimal(self.leave_days_override)

        first = dt.date(year, 1, 1)
        last = dt.date(year, 12, 31)
        if self.started_on and self.started_on > first:
            first = self.started_on
        if self.ended_on and self.ended_on < last:
            last = self.ended_on
        if first > last:
            return Decimal("0.0")

        return settings.round_leave(
            self._weighted_in_year(year, settings, settings.leave_days_for)
        )

    def _weighted_in_year(self, year, settings, full_year_days):
        """Sum of ``full_year_days(pattern)`` over the year, weighted by coverage.

        Factored out because the annual entitlement and the statutory share have
        to be weighted *identically* — they are two readings of one year, and a
        share computed a different way from the total it is a share of is a pair
        of numbers that cannot be made to add up. Unrounded: the caller rounds
        once, at the end.
        """
        first = dt.date(year, 1, 1)
        last = dt.date(year, 12, 31)
        if self.started_on and self.started_on > first:
            first = self.started_on
        if self.ended_on and self.ended_on < last:
            last = self.ended_on
        if first > last:
            return Decimal("0")

        days_in_year = (dt.date(year, 12, 31) - dt.date(year, 1, 1)).days + 1
        earned = Decimal("0")
        for period, from_date, to_date in self.contract_spans(first, last):
            covered = Decimal((to_date - from_date).days + 1)
            earned += (
                full_year_days(period.working_days_per_week)
                * covered / Decimal(days_in_year)
            )
        return earned

    def contract_spans(self, first, last):
        """``[(period, from_date, to_date), …]`` covering ``first``-``last``.

        The clipping, in one place. A period runs until the next one begins, and
        the last one runs to the end of the range; both ends are clipped to the
        range asked about, so a caller never has to think about a contract that
        started in 2019 while it is looking at 2026.

        Dates before the earliest contract are simply not covered — they are
        dates this person had no contract on, which is exactly what a row
        created without a start date says about the years before it.
        """
        periods = list(
            self.contract_periods.filter(valid_from__lte=last).order_by("valid_from")
        )
        spans = []
        for index, period in enumerate(periods):
            begins = max(period.valid_from, first)
            if index + 1 < len(periods):
                ends = min(periods[index + 1].valid_from - dt.timedelta(days=1), last)
            else:
                ends = last
            if begins <= ends:
                spans.append((period, begins, ends))
        return spans

    def special_leave_days(self, settings=None, year=None):
        """``[(grant, days), …]`` for every special leave type this person has.

        Only granted types appear. A type that exists in the organisation but
        has not been given to this person is not "zero days of it" — it is not
        theirs, and listing it at zero on their page invites the question of why
        they have none.
        """
        settings = settings or OrgSettings.current()
        return [
            (grant, grant.days(settings=settings, year=year))
            for grant in self.special_leave.select_related("leave_type")
            if grant.leave_type.is_active
        ]

    @property
    def opening_date(self):
        """The date the opening figures apply from.

        Falls back to the start date and then to the first contract, so that a
        row where nobody filled the field in still has *a* date — an opening
        balance with no date could not be attributed to a year, and would either
        be counted every year or none.
        """
        if self.opening_balance_on:
            return self.opening_balance_on
        if self.started_on:
            return self.started_on
        first = self.contract_periods.order_by("valid_from").first()
        return first.valid_from if first else None

    def opening_leave_in_year(self, year):
        """The leave days brought in, if they belong to ``year``. Otherwise nought.

        **Counted once, in the year the figure was true**, and never again. The
        obvious mistake is to add it to every year's entitlement, which hands
        somebody their joining bonus of six days again every January; the other
        one is to add it to no year at all, which is what happens if the date is
        allowed to be null. After that first year it is not lost — whatever is
        left of it carries forward through ``LeaveCarryOver`` like any other
        untaken day, which is the same path everybody else's remainder takes.
        """
        if not self.opening_leave_days:
            return Decimal("0")
        on = self.opening_date
        if on is None or on.year != year:
            return Decimal("0")
        return Decimal(self.opening_leave_days)

    # -- finding the account ---------------------------------------------

    @classmethod
    def link_by_username(cls, user, directory_name=None):
        """Attach the employee row whose sign-in name matches this account.

        Called at every sign-in. ``directory_name`` is the ``preferred_username``
        the provider sent — the LDAP account name, which is the thing a manager
        typed into the contract. It falls back to the local username, which is
        right for a **local** account (somebody typed that name themselves) and
        harmlessly wrong for an SSO one, where the local username is the opaque
        ``sub`` and simply will not match anything.

        Three conditions, each a way of being wrong this refuses to be:

        * a **non-empty** name — otherwise every unnamed row matches every
          unnamed account, and the first administrator to sign in becomes
          whichever employee was created first;
        * that employee **not already linked** to a different account;
        * that account **not already linked** to a different employee.

        There is no "exactly one match" condition any more and that is the point
        of the change: a directory name is unique by construction and by the
        constraint in ``Meta``, so the ambiguity the e-mail version had to
        refuse — two people sharing a family address — cannot arise. What used
        to be a refusal is now simply a link.

        Anything unmatched leaves a manager to make the link by hand on the
        employee page, which is visible and undoable rather than silent and
        wrong.
        """
        name = (directory_name or getattr(user, "username", "") or "").strip()
        if not name or getattr(user, "employee", None) is not None:
            return None
        employee = cls.objects.filter(
            username__iexact=name, user__isnull=True,
        ).first()
        if employee is None:
            return None
        employee.user = user
        employee.save(update_fields=["user"])
        return employee

    @classmethod
    def for_user(cls, user):
        """The employee behind a signed-in account, or ``None``.

        ``None`` is an ordinary answer, not an error: an administrator who does
        not work shifts has an account and no contract. Every page that shows
        somebody their own time handles it by saying so.
        """
        if not user or not user.is_authenticated:
            return None
        return getattr(user, "employee", None)


class ContractPeriod(models.Model):
    """The seven columns, as they stood from one date onwards.

    **Why history, rather than seven columns that a manager edits in place.**
    Somebody goes from five days to three in April. Editing the columns rewrites
    the whole year: January's Wednesday becomes a day they never worked, the
    leave they were entitled to in March becomes the leave a three-day week
    buys, and a timesheet printed in February no longer reproduces. None of that
    shows an error — every page still renders, with different numbers than it
    had yesterday and nothing to say why.

    So a change is a **new row with a date on it**, and every question that
    depends on the contract is asked *as at a date*:

    * "is this a working day" — the period covering that date;
    * "how long is it" — the same;
    * "how much leave for the year" — every period that touches the year, each
      weighted by how much of the year it covered (``annual_leave_days``).

    The row in force today is the contract. There is always at least one, from
    the moment the employee exists, and ``valid_from`` on the first is the day
    they started or — for a row created before anybody said — the earliest date
    there is, so that no date is ever uncovered.

    ``valid_from`` is unique per employee. Two periods starting on one date is a
    state with no reading: whichever the ordering returned first would be the
    contract, and that is an ordering nobody chose.
    """

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="contract_periods",
        verbose_name=_("employee"),
    )
    valid_from = models.DateField(
        _("in force from"),
        help_text=_("The first date these hours apply. Everything before it keeps the previous ones."),
    )

    hours_mon = models.DecimalField(_("Monday"), max_digits=4, decimal_places=2, default=Decimal("0"),
                                    validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))])
    hours_tue = models.DecimalField(_("Tuesday"), max_digits=4, decimal_places=2, default=Decimal("0"),
                                    validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))])
    hours_wed = models.DecimalField(_("Wednesday"), max_digits=4, decimal_places=2, default=Decimal("0"),
                                    validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))])
    hours_thu = models.DecimalField(_("Thursday"), max_digits=4, decimal_places=2, default=Decimal("0"),
                                    validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))])
    hours_fri = models.DecimalField(_("Friday"), max_digits=4, decimal_places=2, default=Decimal("0"),
                                    validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))])
    hours_sat = models.DecimalField(_("Saturday"), max_digits=4, decimal_places=2, default=Decimal("0"),
                                    validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))])
    hours_sun = models.DecimalField(_("Sunday"), max_digits=4, decimal_places=2, default=Decimal("0"),
                                    validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("24"))])

    note = models.CharField(
        _("why it changed"), max_length=200, blank=True,
        help_text=_("Shown beside the change on their contract — “went to three days”, “parental leave”."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Newest first, which is the order the contract page lists them in and
        # the order `for_date` walks. `.first()` on a filtered queryset is then
        # the period in force.
        ordering = ["-valid_from"]
        verbose_name = _("contract")
        verbose_name_plural = _("contracts")
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "valid_from"], name="one_contract_per_start_date",
            ),
        ]

    def __str__(self):
        return f"{self.employee} from {self.valid_from}"

    @property
    def weekly_hours(self):
        return sum((getattr(self, name) for name in HOURS_FIELDS), Decimal("0"))

    @property
    def working_days_per_week(self):
        return sum(1 for name in HOURS_FIELDS if getattr(self, name) > 0)

    def hours_on_weekday(self, weekday):
        return getattr(self, HOURS_FIELDS[weekday])

    @property
    def weekly_pattern(self):
        return [
            (index, label, getattr(self, HOURS_FIELDS[index]))
            for index, label in WEEKDAYS
        ]


class SpecialLeaveGrant(models.Model):
    """This employee has this special leave type.

    The row's *existence* is the grant; ``days_override`` only changes the
    amount. That is why there is no ``is_granted`` boolean — a switched-off
    grant and a deleted one would mean the same thing and drift apart, and the
    page would have to explain the difference to somebody who does not have one.
    """

    employee = models.ForeignKey(
        Employee, on_delete=models.CASCADE, related_name="special_leave",
    )
    leave_type = models.ForeignKey(
        "organisation.SpecialLeaveType", on_delete=models.CASCADE, related_name="grants",
        verbose_name=_("leave type"),
    )
    days_override = models.DecimalField(
        _("days"), max_digits=4, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Leave empty to use the type’s own rule."),
    )

    class Meta:
        ordering = ["leave_type__name"]
        verbose_name = _("special leave")
        verbose_name_plural = _("special leave")
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "leave_type"], name="one_grant_per_type",
            ),
        ]

    def __str__(self):
        return f"{self.employee} — {self.leave_type}"

    def days(self, settings=None, year=None):
        """How many days this grant is worth, override first.

        ``year`` weights it across a contract change exactly as the annual leave
        is weighted, and for the same reason: a type worked out from the working
        days has to move when the working days do, or somebody who halved their
        week keeps a full week's entitlement for the rest of the year. Left out,
        it answers for today's contract, which is what the contract page asks.
        """
        if self.days_override is not None:
            return Decimal(self.days_override)
        if year is None:
            return self.leave_type.days_for(
                self.employee.working_days_per_week, settings=settings,
            )
        return self.leave_type.days_in_year(self.employee, year, settings=settings)
