"""The rules the rest of the app computes against.

Four things live here, and they have one property in common: every one of them
is a **policy somebody set**, not a fact somebody recorded. A timesheet says
what happened; these say what should follow from it. Keeping them in one app
means there is exactly one place to look when a figure on a page is not the
figure somebody expected — and one place where changing it is a decision with a
date on it rather than an edit to a constant.

* ``OrgSettings`` — the singleton. Full-time hours and leave, and which Land's
  public holidays apply.
* ``BreakRule`` — how long a break the law and the house require for a given
  day's work. The resolution is not the obvious one; see ``required_break``.
* ``SpecialLeaveType`` / ``SpecialLeaveThreshold`` — extra leave that is not the
  statutory entitlement, and the three different ways it can be worked out.
"""

import datetime as dt
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Land(models.TextChoices):
    """The sixteen Länder, because public holidays are not federal.

    Nine of the thirteen days in ``apps/absences/bankholidays.py`` depend on
    this and four do not, which is why it is a required setting rather than
    something inferred: an app that guessed Bavaria would hand every employee in
    Hamburg three days they do not have, and the error is invisible until
    somebody is marked absent on a working day.
    """

    BW = "BW", _("Baden-Württemberg")
    BY = "BY", _("Bavaria")
    BE = "BE", _("Berlin")
    BB = "BB", _("Brandenburg")
    HB = "HB", _("Bremen")
    HH = "HH", _("Hamburg")
    HE = "HE", _("Hesse")
    MV = "MV", _("Mecklenburg-Vorpommern")
    NI = "NI", _("Lower Saxony")
    NW = "NW", _("North Rhine-Westphalia")
    RP = "RP", _("Rhineland-Palatinate")
    SL = "SL", _("Saarland")
    SN = "SN", _("Saxony")
    ST = "ST", _("Saxony-Anhalt")
    SH = "SH", _("Schleswig-Holstein")
    TH = "TH", _("Thuringia")


class LeaveRounding(models.TextChoices):
    """What to do with the fraction a pro-rata entitlement produces.

    24 days for somebody working four days out of five is exact. 30 × 3/5 is
    18, also exact. 30 × 4/6 is 20. But 28 × 3/5 is 16.8, and that is a number
    no holiday calendar can express — so what happens to the 0.8 is a policy,
    and it is one an employer may not decide case by case without it becoming a
    different entitlement for two people on the same contract.

    Rounding **up** is the safe default and is what most works agreements say:
    the fraction is the employee's, not the employer's.
    """

    UP = "up", _("always up — 16.8 days becomes 17")
    HALF = "half", _("to the nearest half day — 16.8 becomes 17, 16.6 becomes 16.5")
    EXACT = "exact", _("leave the fraction — 16.8 stays 16.8")


class OrgSettings(models.Model):
    """One row, or none. ``pk`` is pinned to 1.

    The same singleton-as-a-table shape as ``accounts.SSOConfiguration``, and
    for the same two reasons: it can be edited through a form, and a change is
    atomic. Half-applied working time rules are a payroll question nobody can
    answer.

    ``current()`` returns an **unsaved** instance when the table is empty rather
    than creating one, so that a fresh checkout computes against the defaults
    below and no page takes a write lock to answer a read.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    # What "full time" means here. Both are the denominator of a pro-rata sum:
    # an employee's entitlement is this many days scaled by how much of a full
    # week they work, so getting either wrong moves everybody's leave at once.
    full_time_days_per_week = models.PositiveSmallIntegerField(
        _("full-time working days per week"), default=5,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
        help_text=_("The divisor for everybody’s leave. Five for a Monday-to-Friday business."),
    )
    full_time_leave_days = models.DecimalField(
        _("full-time leave days per year"), max_digits=4, decimal_places=1,
        default=Decimal("30.0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("What somebody working a full week is entitled to. The statutory minimum is 20 on a five-day week."),
    )
    leave_rounding = models.CharField(
        _("rounding"), max_length=10,
        choices=LeaveRounding.choices, default=LeaveRounding.UP,
        help_text=_("What happens to the fraction when the entitlement does not come out whole."),
    )

    # -- the statutory half, and when each half expires ------------------
    #
    # **The two halves of somebody's leave are not the same thing and do not
    # expire on the same terms**, and an app that treats them as one number gets
    # the answer wrong in whichever direction its single rule happens to point.
    #
    # The statutory minimum — 24 working days on a six-day week under Paragraph 3
    # BUrlG, which is 20 on the five-day week almost everybody actually works —
    # is protected. It carries into the following year only for an urgent
    # operational or personal reason, and then only until 31 March; and since
    # the Bundesarbeitsgericht's Hinweispflicht decisions it does not expire at
    # all unless the employer demonstrably told the employee what was left and
    # that it was about to lapse.
    #
    # Everything the employer grants on top of that is the employer's to define.
    # Most contracts let it die with the year, which is lawful precisely because
    # it is not the statutory entitlement.
    #
    # So: two figures, two deadlines, and a switch on each for the employer that
    # carries everything over indefinitely.
    statutory_leave_days = models.DecimalField(
        _("of which statutory, per year"), max_digits=4, decimal_places=1,
        default=Decimal("20.0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_(
            "The protected part, for somebody working a full week. 20 days on a "
            "five-day week is the statutory minimum. Anything above it is the "
            "employer’s own and may expire on the employer’s own terms."
        ),
    )

    statutory_expires = models.BooleanField(
        _("statutory leave expires"), default=True,
        help_text=_("Switch off to carry it indefinitely, which is what an employer who does not send the reminder should assume."),
    )
    statutory_deadline_month = models.PositiveSmallIntegerField(
        _("statutory carry-over deadline — month"), default=3,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    statutory_deadline_day = models.PositiveSmallIntegerField(
        _("statutory carry-over deadline — day"), default=31,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )

    employer_expires = models.BooleanField(
        _("the employer’s extra expires"), default=True,
    )
    employer_deadline_month = models.PositiveSmallIntegerField(
        _("the employer’s deadline — month"), default=12,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    employer_deadline_day = models.PositiveSmallIntegerField(
        _("the employer’s deadline — day"), default=31,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )

    land = models.CharField(
        _("federal state"), max_length=2, choices=Land.choices, default=Land.BW,
        help_text=_("Which public holidays apply. Nine of the thirteen differ by Land."),
    )

    # The house clock. Distinct from Django's TIME_ZONE, which is the *server's*
    # — the NAS may be set to anything and is not a statement about where the
    # staff stand. This is what a clocked start is read against, what decides
    # which date it lands on, and what makes a night shift across the last
    # Sunday in October come out at nine hours rather than eight.
    # apps/timesheets/zones.py is the whole of the reasoning.
    time_zone = models.CharField(
        _("time zone"), max_length=64, default="Europe/Berlin",
        help_text=_(
            "The clock the workplace keeps. Somebody who works elsewhere can be given "
            "their own on their contract."
        ),
    )

    # Where "fill the week from the contracts" starts everybody. Only ever a
    # starting point for a draft the manager then drags around — a contract says
    # how *long* somebody works and never when, so this is the one piece of
    # information the roster needs that no other model holds. Without it the
    # fill button could not exist, and building a repeating week by hand is the
    # largest single cost this app can take off a manager.
    day_start = models.TimeField(
        _("the day usually starts at"), default=dt.time(8, 0),
        help_text=_("Used only when filling a week from the contracts, as the first draft."),
    )

    class Meta:
        verbose_name = _("working time settings")
        verbose_name_plural = _("working time settings")

    def __str__(self):
        return str(_("Working time settings"))

    @classmethod
    def current(cls):
        """The stored row, or an unsaved instance carrying the defaults.

        Never creates. This is called while rendering nearly every page in the
        app — a create here would put SQLite's single write lock inside a GET,
        which is the read-must-not-write rule broken on the hottest path there
        is.
        """
        return cls.objects.filter(pk=1).first() or cls()

    @property
    def is_stored(self):
        """Whether this instance came from the database.

        **Not ``self.pk``**, and that trap is the whole reason this exists: the
        primary key is pinned to 1 with a *default*, so an unsaved instance
        already has ``pk == 1`` and every ``if self.pk`` reads as True. Code
        guarded that way then follows ``self.break_rules`` on a row that was
        never saved — which does not raise, and quietly returns the rules
        belonging to whatever is stored under id 1.

        ``_state.adding`` is Django's own answer and is set correctly by both
        ``cls()`` and a queryset.
        """
        return not self._state.adding

    def save(self, *args, **kwargs):
        from apps.timesheets.zones import forget_org_zone

        self.pk = 1
        result = super().save(*args, **kwargs)
        # The house zone is cached for a minute (apps/timesheets/zones.py), and
        # it is the one setting where waiting that minute would be visible: the
        # page you land on after saving would still be clocking people in on the
        # old clock, which reads as the save not having worked.
        forget_org_zone()
        return result

    # -- breaks ----------------------------------------------------------

    def required_break(self, blocks, gaps=(), rules=None):
        """What still has to come off a day, given how the day was actually shaped.

        ``blocks`` is the length of each unbroken stretch of work, in minutes,
        in the order it happened; an ``int`` is taken as a single stretch.
        ``gaps`` is the time between them, so ``len(gaps)`` is one less than
        ``len(blocks)``. The **shape matters and the totals are not enough** —
        which is the whole reason this does not simply take two numbers.

        ----

        **First: the obvious implementation is wrong**, and wrong in the
        direction that underpays a break. Reading the rules as "worked over six
        hours, so take thirty minutes" gives a day of 6h05 a thirty-minute break
        — but the rule is about *working* time, and 6h05 minus thirty is 5h35,
        which is not over six hours at all. Applying them to the net time
        instead is circular: the net time depends on the break, which is what is
        being worked out.

        The way out is to read each rule as the constraint it is: *either the
        working time is inside the tier, or the total break reaches it.* Writing
        D for what still has to come off, T for what was already taken and P for
        the time at work, one tier is satisfied when

            D >= P - over        (the working time drops inside the tier)
            or  D >= break - T   (the total break reaches what the tier wants)

        so the least D that satisfies it is the smaller of those two, floored at
        nought, and the day's answer is the largest over the tiers.

        **Second: a break somebody actually took is not deducted again.**
        09:30–15:30 and 16:00–18:00 is eight hours at work with thirty minutes
        off in the middle, which is precisely what §4 ArbZG asks of an
        eight-hour day. Deducting another thirty charges them twice for a break
        they took.

        **Third — and this is what the two above miss — a break only counts if
        it broke the work up.** §4 ArbZG has two sentences, not one: the day
        needs thirty minutes in total *and* nobody may work "länger als sechs
        Stunden hintereinander ohne Ruhepause". A day of 08:30–15:00 and then
        16:00–17:00 has an hour off in it and still contains six and a half
        hours worked straight through. Counting the later hour against the
        earlier stretch lets a break taken *afterwards* pay for one that was
        never taken — which is how adding an evening hour made the deduction
        disappear.

        So each stretch owes its own break as well:

            inside  = sum over stretches of  max over rules of
                          min(break, max(0, stretch - over))
            overall = max over rules of
                          min(max(0, gross - over), max(0, break - taken))
            D       = max(inside, overall)

        Both are "D must be at least this", so the larger of the two is the
        least D that satisfies both.

        **Fourth: a gap under fifteen minutes is not a break.** §4 lets the
        break be split "in Zeitabschnitte von jeweils mindestens 15 Minuten", so
        a five-minute pause is neither a Ruhepause nor an interruption: it does
        not count towards the thirty, and the stretches either side of it are
        one stretch for the purpose above. It is still not *worked* — somebody
        who clocked out was not there — so it stays out of the gross either way.

        ``rules`` may be passed in by a caller that has already fetched them —
        the month view resolves this for thirty-one days and would otherwise run
        thirty-one identical queries.

        **An empty table means the defaults, not "no breaks", and that is
        deliberate.** It is the one place this app overrides what the database
        literally says, so it is worth being explicit about the direction: a
        break not deducted *overstates* hours worked, which is the side an
        employer is answerable for. Erring towards the statutory break is the
        safe failure; erring away from it ships an installation that quietly
        records everybody as working through, and nobody finds out until an
        inspection. The settings page says the same thing in as many words and
        offers to write the rows.

        The cost is that "no breaks at all" cannot be expressed. In Germany it
        is not a configuration anybody needs, and an escape hatch nobody needs
        is not worth the failure mode it opens.
        """
        if isinstance(blocks, int):
            blocks = [blocks]
        blocks = [max(0, int(block)) for block in blocks]
        gaps = [max(0, int(gap)) for gap in gaps]

        if rules is None:
            rules = list(self.break_rules.all()) if self.is_stored else []
        if not rules:
            rules = [BreakRule(over_minutes=over, break_minutes=length)
                     for over, length in DEFAULT_BREAK_RULES]

        gross = sum(blocks)
        taken = sum(gap for gap in gaps if gap >= MIN_BREAK_CHUNK)

        inside = sum(
            max(
                (min(rule.break_minutes, max(0, stretch - rule.over_minutes))
                 for rule in rules),
                default=0,
            )
            for stretch in unbroken_stretches(blocks, gaps)
        )
        overall = max(
            (min(max(0, gross - rule.over_minutes),
                 max(0, rule.break_minutes - taken))
             for rule in rules),
            default=0,
        )
        return max(inside, overall)

    # -- deadlines -------------------------------------------------------

    def statutory_deadline(self, year):
        """When last year's statutory days lapse, in ``year``.

        A month and a day rather than a stored date, because it is a rule that
        applies to every year and a date would have to be re-entered each
        January — and the January nobody remembers is the January everybody's
        leave silently stops expiring, or starts.

        Clamped rather than refused when the day does not exist in that month:
        an administrator who types 31 for February means the end of February,
        and refusing it in the following leap year would be the settings page
        breaking on its own stored value.
        """
        return _month_day(year, self.statutory_deadline_month, self.statutory_deadline_day)

    def employer_deadline(self, year):
        """When last year's employer-granted extra lapses, in ``year``.

        Defaults to 31 December of the year the leave was *earned*, which is
        what most contracts say — so for leave earned in 2025 this returns 31
        December 2025 when asked about 2025, and the carry-over calculation
        never has any extra to carry.
        """
        return _month_day(year, self.employer_deadline_month, self.employer_deadline_day)

    # -- entitlement -----------------------------------------------------

    def statutory_days_for(self, working_days_per_week):
        """The protected part of one person's entitlement.

        Scaled by working days exactly as the whole entitlement is, and for the
        same reason — the statutory minimum is expressed in *working days*, so
        somebody on three days a week has three fifths of it and not three
        fifths of nothing.

        Never more than the total. An administrator who sets the statutory
        figure above the full-time one has said something contradictory, and the
        safe reading is that all of it is protected: erring towards protection
        cannot cost an employee a day, and erring the other way can.
        """
        total = self.leave_days_for(working_days_per_week)
        full_days = self.full_time_days_per_week or 5
        if working_days_per_week <= 0:
            return Decimal("0.0")
        raw = (Decimal(self.statutory_leave_days)
               * Decimal(working_days_per_week) / Decimal(full_days))
        return min(total, self.round_leave(raw))

    def leave_days_for(self, working_days_per_week):
        """The annual leave somebody working that many days a week is entitled to.

        Pro rata by *days*, not by hours, and that is the legally load-bearing
        part rather than a simplification. A day of leave buys a day off; how
        long that day is does not change how many of them a year holds. Somebody
        working three ten-hour days has the same number of days off as somebody
        working three six-hour days, and scaling by hours would quietly give the
        second person fewer — which is the discrimination case every works
        agreement on part-time leave exists to avoid.
        """
        full_days = self.full_time_days_per_week or 5
        if working_days_per_week <= 0:
            return Decimal("0.0")
        raw = (Decimal(self.full_time_leave_days)
               * Decimal(working_days_per_week) / Decimal(full_days))
        return self.round_leave(raw)

    def round_leave(self, value):
        """Apply ``leave_rounding``. Shared with the special leave types, which
        produce fractions the same way and must not round differently — two
        rounding rules in one app is two entitlements nobody can reconcile."""
        value = Decimal(value)
        if self.leave_rounding == LeaveRounding.EXACT:
            return value.quantize(Decimal("0.1"))
        if self.leave_rounding == LeaveRounding.HALF:
            return (value * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2
        return value.quantize(Decimal("1"), rounding=ROUND_CEILING)


def _month_day(year, month, day):
    """``date(year, month, day)``, with the day clamped to the month's length.

    31 February is a thing somebody types into a settings page, and the useful
    reading of it is "the end of February". A ``ValueError`` here would be the
    page failing on a value it had already accepted and stored, in a year it
    happened not to be tested in.
    """
    import calendar

    last = calendar.monthrange(year, month)[1]
    return dt.date(year, month, min(day, last))


# What a database with no BreakRule rows computes against, and what the settings
# page offers to create. **The statute, exactly**: §4 ArbZG asks thirty minutes
# of a day over six hours and forty-five of one over nine.
#
# The second row was eight hours rather than nine for a while, on the argument
# that a default may only err towards the employee. It was changed back because
# the argument does not survive contact with the page: a house that wants
# forty-five minutes at eight hours can say so in one edit, whereas everybody
# else was reading a timesheet whose figures did not match the law they had
# looked up. A default that has to be explained is not a safe default.
DEFAULT_BREAK_RULES = ((360, 30), (540, 45))

# The shortest pause that is a break at all. §4 ArbZG lets the break be split
# "in Zeitabschnitte von jeweils mindestens 15 Minuten", so anything shorter is
# neither a Ruhepause nor an interruption of the work: it counts towards
# nothing, and the stretches either side of it are one stretch.
#
# A constant rather than a setting. It is a number in a statute, and an
# organisation that could edit it could only edit it *wrong* — the direction
# that would help an employer is the direction the law does not allow.
MIN_BREAK_CHUNK = 15


def unbroken_stretches(blocks, gaps):
    """``blocks`` merged across any gap too short to be a break.

    Working four hours, pausing five minutes and working two and a half more is
    six and a half hours *hintereinander* however it was clocked — the five
    minutes did not interrupt anything. Merging them is what makes the stretch
    owe its own break.
    """
    merged = []
    for index, block in enumerate(blocks):
        joined = (
            index > 0
            and index - 1 < len(gaps)
            and gaps[index - 1] < MIN_BREAK_CHUNK
        )
        if joined and merged:
            merged[-1] += block
        else:
            merged.append(block)
    return merged


class BreakRule(models.Model):
    """One tier of the break table.

    Rows rather than two settings fields, because the number of tiers is not
    fixed: a house rule with a third step at twelve hours is an ordinary thing
    and must not need a migration.
    """

    settings = models.ForeignKey(
        OrgSettings, on_delete=models.CASCADE, related_name="break_rules",
    )
    over_minutes = models.PositiveSmallIntegerField(
        _("working time over"),
        help_text=_("In minutes. 360 is six hours."),
    )
    break_minutes = models.PositiveSmallIntegerField(
        _("break"), help_text=_("In minutes."),
    )

    class Meta:
        ordering = ["over_minutes"]
        verbose_name = _("break rule")
        verbose_name_plural = _("break rules")
        constraints = [
            models.UniqueConstraint(
                fields=["settings", "over_minutes"], name="one_rule_per_threshold",
            ),
        ]

    def __str__(self):
        return f"> {self.over_minutes} min → {self.break_minutes} min"


class AssignmentMode(models.TextChoices):
    """How much of a special leave type somebody gets.

    Three modes rather than one, because the three exist in real agreements and
    produce genuinely different numbers. A single "pro rata" mode would be the
    tidy choice and would silently turn "everybody gets their birthday off" into
    "everybody gets three fifths of their birthday off".
    """

    FIXED = "fixed", _("the same for everybody who has it")
    PRO_RATA = "pro_rata", _("scaled by working days, like the annual leave")
    THRESHOLD = "threshold", _("from a table of working days per week")


class SpecialLeaveType(models.Model):
    """Leave that is not the statutory annual entitlement.

    Named by the administrator because the names are the point — "Kur",
    "Bildungsurlaub", "Geburtstag", "Jubiläumstage" are four different things
    with four different rules, and an app that called them all "extra leave"
    would make the balance on somebody's page unreadable.

    Having a type does **not** grant it. ``employees.SpecialLeaveGrant`` is the
    row that says a particular person has this one, which is what makes it
    possible to offer a type to some employees and not others without inventing
    a second type for the people who do not get it.
    """

    name = models.CharField(_("name"), max_length=100)
    mode = models.CharField(
        _("how it is worked out"), max_length=12,
        choices=AssignmentMode.choices, default=AssignmentMode.PRO_RATA,
    )
    days = models.DecimalField(
        _("days"), max_digits=4, decimal_places=1, default=Decimal("1.0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("For “the same for everybody”, the number itself. For “scaled”, what a full-time employee would get."),
    )
    is_active = models.BooleanField(
        _("offered"), default=True,
        help_text=_("Switching this off keeps the leave already taken and stops it being granted to anybody new."),
    )

    class Meta:
        ordering = ["name"]
        verbose_name = _("special leave type")
        verbose_name_plural = _("special leave types")

    def __str__(self):
        return self.name

    def clean(self):
        # A threshold type's `days` is never read — the table answers instead —
        # and a page showing both would be showing one number that does nothing.
        # The form hides it; this is what stops a fixture setting it anyway.
        if self.mode == AssignmentMode.THRESHOLD and self.pk:
            if not self.thresholds.exists():
                raise ValidationError({
                    "mode": _("A leave type worked out from a table needs at least one row in it."),
                })

    def days_for(self, working_days_per_week, settings=None):
        """How many days of this type somebody working that week gets.

        Returns ``Decimal("0.0")`` for a threshold type whose table does not
        reach down to this many days — which is a real answer and the reason
        the mode exists. "Five days a week gets two, three days a week gets one"
        implies that two days a week gets none, and inventing 0.8 for that
        person is precisely what the employer did not agree to.
        """
        from apps.organisation.models import OrgSettings as _Settings  # local: same module

        settings = settings or _Settings.current()
        if working_days_per_week <= 0:
            return Decimal("0.0")

        if self.mode == AssignmentMode.FIXED:
            return Decimal(self.days).quantize(Decimal("0.1"))

        if self.mode == AssignmentMode.PRO_RATA:
            full = settings.full_time_days_per_week or 5
            return settings.round_leave(
                Decimal(self.days) * Decimal(working_days_per_week) / Decimal(full)
            )

        # THRESHOLD: the most generous row this person clears. Ordered ascending
        # by the model's Meta, so the last match wins rather than the first.
        earned = Decimal("0.0")
        for row in self.thresholds.all():
            if working_days_per_week >= row.min_days_per_week:
                earned = Decimal(row.days)
        return earned.quantize(Decimal("0.1"))


    def days_in_year(self, employee, year, settings=None):
        """This type's entitlement for one person in one year, weighted.

        The same shape as ``Employee.leave_days_in_year`` and for the same
        reason — somebody whose working days changed in April is not on one
        pattern for the year. It matters most for the threshold mode, where the
        step is the whole point: five days a week gets two and three days gets
        one, so half a year of each is one and a half, and applying either
        pattern to the whole year is a whole day wrong.
        """
        from apps.organisation.models import OrgSettings as _Settings

        settings = settings or _Settings.current()
        first = dt.date(year, 1, 1)
        last = dt.date(year, 12, 31)
        if employee.started_on and employee.started_on > first:
            first = employee.started_on
        if employee.ended_on and employee.ended_on < last:
            last = employee.ended_on
        if first > last:
            return Decimal("0.0")

        days_in_year = (dt.date(year, 12, 31) - dt.date(year, 1, 1)).days + 1
        earned = Decimal("0")
        for period, from_date, to_date in employee.contract_spans(first, last):
            covered = Decimal((to_date - from_date).days + 1)
            earned += (
                self.days_for(period.working_days_per_week, settings=settings)
                * covered / Decimal(days_in_year)
            )
        # Rounded once, at the end. Rounding each slice would hand somebody an
        # extra day for every time their contract was ever touched.
        return settings.round_leave(earned)


class SpecialLeaveThreshold(models.Model):
    """One row of a threshold table: work this many days a week, get this many.

    A step function, deliberately — the whole reason an employer writes one is
    to *avoid* the pro-rata fraction. "Three days or more gets one, five days
    gets two" is two rows, and everything below three gets nothing.
    """

    leave_type = models.ForeignKey(
        SpecialLeaveType, on_delete=models.CASCADE, related_name="thresholds",
    )
    min_days_per_week = models.PositiveSmallIntegerField(
        _("working days per week, at least"),
        validators=[MinValueValidator(1), MaxValueValidator(7)],
    )
    days = models.DecimalField(
        _("days"), max_digits=4, decimal_places=1,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        ordering = ["min_days_per_week"]
        verbose_name = _("threshold")
        verbose_name_plural = _("thresholds")
        constraints = [
            models.UniqueConstraint(
                fields=["leave_type", "min_days_per_week"],
                name="one_threshold_per_day_count",
            ),
        ]

    def __str__(self):
        return f"≥ {self.min_days_per_week} → {self.days}"
