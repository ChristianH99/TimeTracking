"""How long each kind of record is kept, and what removes it afterwards.

**Both directions, and everybody builds one.** "Delete once the period is up" is
the DSGVO half (Art. 5(1)(e), storage limitation) and it is the one people mean
when they say retention policy. "Keep until the period is up" is the AO and ArbZG
half, and an app that has only the first destroys evidence its employer is
required to hold. This app had neither: it kept everything forever, which is the
wrong answer to both at once — lawful-looking, because nothing is ever lost, and
unlawful, because nothing is ever erased either.

``docs/AUDIT.md`` carries the numbers and which auditor each comes from. This is
what enforces them.

----

**Five classes, because the periods genuinely differ.** One number for the whole
database would have to be the longest of them, which is exactly the over-retention
the DSGVO is about. The split is not arbitrary: each line below is a different
statute answering a different question.

The last two are one table and two policies, and that split is the payoff of a
decision already made. ``AuditEntry.is_security_event`` exists so that "is this
the record trail or the sign-in log" is decided in one place; here is the second
place that asks. A sign-in log kept for ten years is the thing a
*Datenschutzbeauftragter* objects to first, and it is the one class with a data
protection argument and no tax-law argument on the other side.

----

**The period runs from the end of the calendar year, not from the record's own
date.** §147(4) AO: *"Die Aufbewahrungsfrist beginnt mit dem Schluss des
Kalenderjahres, in dem …"*. So a record from 15 March 2024 with a two-year period
is kept through 31 December 2026 and may go on 1 January 2027 — not on 15 March
2026. The naive subtraction deletes up to eleven months early, and it errs in the
direction that costs somebody evidence rather than the direction that costs an
apology. ``cutoff_for`` is that rule and is the only place it is written.

**A person is erased last.** Their name is frozen onto every audit entry about
them (``employee_label``), because a ``SET_NULL`` key would otherwise say *nobody
did this* the day their account went. That text is personal data, and the table
it sits in cannot be edited — so the only way erasure reaches it is for the
entries to *expire* on their own schedule. The ``Employee`` row therefore goes
when nothing else about them is left: no day, no absence, no shift, no entry.
Their retention is not a number, it is "after everything else", and the audit
trail — the longest class — is what sets it.

**The sweep does not audit itself row by row.** The signal handlers are suppressed
while it runs and it writes **one** entry per class instead. The alternative is a
sweep that grows the table it is shrinking, filling it with rows about records
that no longer exist — and on the first run over ten years of data, that is
hundreds of thousands of them.
"""

import dataclasses
import datetime as dt

from django.utils.translation import gettext_lazy as _


# --------------------------------------------------------------------------
# What the statute requires, which is the floor and never the answer
# --------------------------------------------------------------------------
#
# These are minimums the employer may not go below, not recommendations. The
# *setting* beside each one is what the employer actually keeps, and it starts
# well above the floor: over-retention is a conversation with a data protection
# officer, and under-retention is a conversation with the Zoll.

# §16(2) ArbZG and §17 MiLoG both say two years. The Lohnkonto they support is
# six under §41 EStG and §147(3) AO, and §28f SGB IV runs to a date nobody can
# compute in advance — the end of the calendar year following the next audit.
# The floor here is the two everybody agrees on; the default is ten, which
# clears every one of the others.
FLOOR_WORKING_TIME = 2
FLOOR_ABSENCES = 3
# A roster is a *plan*. Nothing requires keeping one, and the app keeps it only
# because "what were you asked to work" is half the sentence BAG 5 AZR 359/21
# makes valuable — which stops mattering once the timesheet beside it has gone.
FLOOR_ROSTER = 0
# Nothing requires a sign-in log at all. Art. 32 DSGVO wants one to exist; no
# statute says how long, and the longer it is the harder it is to justify.
FLOOR_SECURITY_LOG = 0


@dataclasses.dataclass(frozen=True)
class RetentionClass:
    """One kind of record, its floor, and the setting that names its ceiling."""

    key: str
    label: object
    setting: str
    floor_years: int
    why: object
    # Returns ``[(model, queryset), …]`` for everything anchored before ``cutoff``.
    # A callable rather than a list of models, because the anchor field differs
    # per model — a day is anchored on its date and a carry-over on its year —
    # and a table of field names would be a second place to get that wrong.
    matcher: object

    def cutoff(self, settings, today=None):
        return cutoff_for(self.years(settings), today)

    def years(self, settings):
        """What the employer keeps, never below the floor.

        Clamped here as well as validated on the form, because a row written
        before the validation existed — or by a data migration, or by hand —
        must not be able to shorten a statutory period by being loaded.
        """
        return max(self.floor_years, int(getattr(settings, self.setting, 0) or 0))

    def due(self, settings, today=None):
        return self.matcher(self.cutoff(settings, today))


def cutoff_for(years, today=None):
    """The first date that is *out* of a period of ``years``.

    §147(4) AO: the period begins at the **end of the calendar year** in which
    the record arose. So with two years, a record from any date in 2024 is kept
    through 31 December 2026 and is out on 1 January 2027 — and on any day in
    2027 the cutoff is 1 January 2025, because 2024 and everything before it has
    now had its two full years.

    Written once, here, because the version that subtracts ``years`` from today's
    *date* deletes up to eleven months early — and early is the direction that
    loses evidence rather than the one that loses an argument.
    """
    today = today or dt.date.today()
    return dt.date(today.year - years, 1, 1)


# --------------------------------------------------------------------------
# The classes
# --------------------------------------------------------------------------

def _working_time(cutoff):
    from apps.timesheets.models import DayLock, DayRecord

    # `WorkSegment` is not listed and does not need to be: it cascades from the
    # day, so a day going takes its punches with it. Listing it would delete
    # segments whose day is still in period the moment somebody got the filter
    # wrong, which is a timesheet with its hours silently removed.
    return [
        (DayRecord, DayRecord.objects.filter(date__lt=cutoff)),
        (DayLock, DayLock.objects.filter(date__lt=cutoff)),
    ]


def _absences(cutoff):
    from apps.absences.carryover import LeaveCarryOver
    from apps.absences.models import Absence

    return [
        # `end_date`, not `start_date`: a fortnight beginning in December ends in
        # January, and the period runs from the later one.
        (Absence, Absence.objects.filter(end_date__lt=cutoff)),
        (LeaveCarryOver, LeaveCarryOver.objects.filter(year__lt=cutoff.year)),
    ]


def _roster(cutoff):
    from apps.roster.models import Shift

    return [(Shift, Shift.objects.filter(date__lt=cutoff))]


def _audit_trail(cutoff):
    from apps.audit.models import AuditEntry, SECURITY_ACTIONS

    return [(AuditEntry, AuditEntry.objects.filter(at__date__lt=cutoff)
             .exclude(action__in=SECURITY_ACTIONS))]


def _security_log(cutoff):
    from apps.audit.models import AuditEntry, SECURITY_ACTIONS

    return [(AuditEntry, AuditEntry.objects.filter(
        at__date__lt=cutoff, action__in=SECURITY_ACTIONS,
    ))]


CLASSES = [
    RetentionClass(
        key="working_time",
        label=_("Working time"),
        setting="keep_working_time_years",
        floor_years=FLOOR_WORKING_TIME,
        why=_(
            "Days, bookings and closed months. §16(2) ArbZG and §17 MiLoG both "
            "require two years; the wage account they support is six (§41 EStG, "
            "§147(3) AO) and social insurance runs to the end of the year after "
            "the next audit, which is a date nobody can work out in advance."
        ),
        matcher=_working_time,
    ),
    RetentionClass(
        key="absences",
        label=_("Time off and sickness"),
        setting="keep_absences_years",
        floor_years=FLOOR_ABSENCES,
        why=_(
            "Leave, sickness and what was carried over. Three years is the "
            "ordinary limitation period for a claim (§195 BGB); leave that was "
            "never expired for want of a reminder can outlive it, which is why "
            "the setting starts well above the floor."
        ),
        matcher=_absences,
    ),
    RetentionClass(
        key="roster",
        label=_("The roster"),
        setting="keep_roster_years",
        floor_years=FLOOR_ROSTER,
        why=_(
            "What people were asked to work. No statute requires keeping a plan; "
            "it is kept because “you were rostered 08:00–14:00 and entered "
            "08:00–15:30” is the sentence this app exists to be able to say — and "
            "that stops mattering once the timesheet beside it has gone."
        ),
        matcher=_roster,
    ),
    RetentionClass(
        key="audit",
        label=_("The audit trail"),
        setting="keep_audit_years",
        floor_years=0,  # replaced by `audit_floor` below — see `floors_for`
        why=_(
            "Every change to a record, who made it, and who looked at whose "
            "hours. It cannot be set shorter than the records it explains: a "
            "trail that dies first leaves them unexplained, which is worse than "
            "having kept neither."
        ),
        matcher=_audit_trail,
    ),
    RetentionClass(
        key="security_log",
        label=_("Sign-ins"),
        setting="keep_security_log_years",
        floor_years=FLOOR_SECURITY_LOG,
        why=_(
            "Who signed in, who was refused, who signed out. Art. 32 DSGVO wants "
            "the log to exist and no statute says how long — so this is the one "
            "period where longer is harder to defend rather than easier, and it "
            "is the only class that is short by default."
        ),
        matcher=_security_log,
    ),
]

BY_KEY = {entry.key: entry for entry in CLASSES}

# The three whose length the audit trail must clear. Named rather than "every
# class except the audit ones", because that phrasing quietly includes the
# security log — and a sign-in log kept one year would then be allowed to drag
# the whole trail down with it.
RECORD_CLASSES = ("working_time", "absences", "roster")


def audit_floor(settings):
    """The shortest the audit trail may be kept: as long as the longest record.

    A trail that expires before the records it describes leaves a timesheet
    nobody can account for — which is worse than never having kept one, because
    the gap looks like an answer. Computed rather than written down, so it moves
    by itself the day somebody lengthens one of the others.
    """
    return max(BY_KEY[key].years(settings) for key in RECORD_CLASSES)


def floors_for(settings):
    """``{key: floor}`` with the audit trail's derived floor filled in."""
    return {
        entry.key: (audit_floor(settings) if entry.key == "audit" else entry.floor_years)
        for entry in CLASSES
    }


def years_for(settings, entry):
    """What ``entry`` is actually kept for, floors applied.

    The audit trail's floor is not a constant, so it cannot live on the
    dataclass — this is the one place that knows both halves.
    """
    wanted = int(getattr(settings, entry.setting, 0) or 0)
    return max(floors_for(settings)[entry.key], wanted)


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------

def survey(settings=None, today=None):
    """What each class holds, how far back, and what is out of period.

    The page and the command both render this, so what somebody reads before
    pressing the button is computed by the same code as what the button does.
    A dry run that took a different path from the real one is a dry run that
    reassures about something else.
    """
    from apps.organisation.models import OrgSettings

    settings = settings or OrgSettings.current()
    today = today or dt.date.today()
    rows = []
    for entry in CLASSES:
        years = years_for(settings, entry)
        cutoff = cutoff_for(years, today)
        matches = entry.matcher(cutoff)
        rows.append({
            "entry": entry,
            "key": entry.key,
            "label": entry.label,
            "why": entry.why,
            "years": years,
            "floor": floors_for(settings)[entry.key],
            "wanted": int(getattr(settings, entry.setting, 0) or 0),
            # True when the employer asked for less than the statute allows and
            # the floor overrode them. Shown on the page, because a setting that
            # is quietly ignored is worse than one that is refused.
            "raised_to_floor": int(getattr(settings, entry.setting, 0) or 0) < floors_for(settings)[entry.key],
            "cutoff": cutoff,
            "due": sum(queryset.count() for _model, queryset in matches),
            "oldest": _oldest(entry),
        })
    rows.append(_people_row(settings, today))
    return rows


def _oldest(entry):
    """The earliest record this class still holds, or ``None``.

    On the page beside the cutoff, so "we keep two years" can be *checked*
    rather than asserted — which is the question an auditor asks and the one an
    employee asks, from opposite directions.
    """
    # A cutoff far enough back to match everything: the matcher is reused rather
    # than a second set of querysets written, so the two cannot disagree about
    # which rows belong to a class.
    everything = dt.date(dt.MINYEAR, 1, 1)
    oldest = None
    for _model, queryset in entry.matcher(dt.date(9999, 12, 31)):
        field = _anchor_of(queryset)
        if field is None:
            continue
        first = queryset.exclude(**{f"{field}__isnull": True}).order_by(field).first()
        if first is None:
            continue
        value = getattr(first, field)
        if isinstance(value, int):  # LeaveCarryOver.year
            value = dt.date(value, 1, 1)
        if hasattr(value, "date"):  # a datetime
            value = value.date()
        if value and (oldest is None or value < oldest):
            oldest = value
    return None if oldest == everything else oldest


def _anchor_of(queryset):
    for name in ("date", "end_date", "year", "at"):
        try:
            queryset.model._meta.get_field(name)
        except Exception:  # noqa: BLE001 — the model simply has no such field
            continue
        return name
    return None


def _people_row(settings, today):
    """People whose records have all gone, and who can therefore be erased.

    Not a class with a period of its own, and the row says so: a person is
    erased *after everything else*, because their name is frozen onto audit
    entries that cannot be edited. The longest class is what decides when.
    """
    return {
        "entry": None,
        "key": "people",
        "label": _("People who have left"),
        "why": _(
            "Somebody who has left is erased once nothing about them is left — no "
            "day, no time off, no roster entry and no audit entry. Their name is "
            "written into the audit trail and that cannot be edited, so the only "
            "way to remove it is to let the trail expire first. The longest period "
            "above is what decides when."
        ),
        "years": max(years_for(settings, entry) for entry in CLASSES),
        "floor": max(years_for(settings, entry) for entry in CLASSES),
        "wanted": None,
        "raised_to_floor": False,
        "cutoff": None,
        "due": erasable_people().count(),
        "oldest": None,
    }


def erasable_people():
    """Employees who have left and about whom nothing at all is still held.

    Everything is checked, including the audit trail — which in practice means
    this stays empty until the longest period has run. That is the point: it is
    what makes "erase this person" reach the one table that cannot be edited.

    An employee still linked to an account is included; the account is not
    touched. Deleting a login is a decision about who may sign in and belongs on
    the People page, and ``SET_NULL`` means the two were never joined at the hip.
    """
    from apps.employees.models import Employee

    return (
        Employee.objects
        .filter(ended_on__isnull=False)
        .exclude(days__isnull=False)
        .exclude(absences__isnull=False)
        .exclude(shifts__isnull=False)
        .exclude(audit_entries__isnull=False)
        .exclude(locks__isnull=False)
        .exclude(carried_leave__isnull=False)
        .distinct()
    )


# --------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------

def sweep(settings=None, today=None, dry_run=True, actor=None):
    """Delete everything out of period. Returns what went, per class.

    **A dry run by default**, and the flag is called ``dry_run`` rather than
    ``force`` deliberately: the caller has to say the word that means "actually
    delete ten years of somebody's timesheet", and a default that deleted would
    make an accidental import of this module the worst bug in the app.

    It reports the same rows in both modes — the counts come from ``survey``
    either way — because a dry run that took a different path from the real one
    is a dry run that reassures about something else.
    """
    from apps.audit.models import AuditAction, AuditEntry
    from apps.audit.recording import record
    from apps.audit.signals import suppressed
    from apps.organisation.models import OrgSettings

    settings = settings or OrgSettings.current()
    today = today or dt.date.today()
    removed = []

    for entry in CLASSES:
        years = years_for(settings, entry)
        cutoff = cutoff_for(years, today)
        counts = {}
        for model, queryset in entry.matcher(cutoff):
            counts[model._meta.object_name] = queryset.count()
        total = sum(counts.values())
        removed.append({
            "key": entry.key, "label": entry.label,
            "years": years, "cutoff": cutoff, "counts": counts, "total": total,
        })
        if dry_run or not total:
            continue

        # **Suppressed, and one entry instead.** Left alone, deleting a decade of
        # days would write a `post_delete` entry for every one of them — a sweep
        # that grows the table it is shrinking, and fills it with rows describing
        # records that no longer exist. See the module docstring.
        with suppressed():
            for model, queryset in entry.matcher(cutoff):
                if model is AuditEntry:
                    # The one door out of an append-only table. `purge` exists so
                    # that this line has to be written on purpose; every other
                    # delete on that model raises.
                    queryset.purge()
                else:
                    queryset.delete()

    if not dry_run:
        for row in removed:
            if not row["total"]:
                continue
            detail = ", ".join(
                f"{name} {count}" for name, count in sorted(row["counts"].items()) if count
            )
            record(
                AuditAction.PURGED,
                subject="retention." + row["key"],
                subject_date=row["cutoff"],
                note=f"< {row['cutoff']:%d.%m.%Y} ({row['years']}a): {detail}"[:200],
                actor=actor,
            )

    people = list(erasable_people())
    if people and not dry_run:
        names = ", ".join(person.full_name for person in people)
        with suppressed():
            for person in people:
                person.delete()
        record(
            AuditAction.PURGED, subject="retention.people",
            note=names[:200], actor=actor,
        )
    removed.append({
        "key": "people", "label": _("People who have left"),
        "years": None, "cutoff": None,
        "counts": {"Employee": len(people)}, "total": len(people),
    })
    return removed
