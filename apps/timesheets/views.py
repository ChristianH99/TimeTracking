"""The timesheet: what you were rostered, what you say you worked, and the month.

**One row builder, three pages.** ``_day_row`` is the whole of what a date is
worth to this person, and ``build_month`` (the timesheet), ``build_week`` (the
start page and the team overview) are two windows onto the same function. A
manager and an employee looking at one day and seeing different figures is the
single most damaging bug this app could have, and two implementations is how it
happens — so there is one, and the windows differ only in which dates they ask
about and what they add up afterwards.

The month is what somebody opens. ``apps/timesheets/bookings.py`` says why the
hours are entered as a column of comings and goings while the database goes on
storing pairs.
"""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from apps.absences.models import Absence, BankHoliday, Balance, RequestStatus
from apps.employees.models import Employee
from apps.employees.permissions import manager_required, own_or_manager
from apps.organisation.models import OrgSettings
from apps.roster.models import Shift
from apps.timesheets import bookings, clocking
from apps.timesheets.balance import hours_balance
from apps.timesheets.fields import SignedMinutesField
from apps.timesheets.forms import DayForm, SegmentFormSet
from apps.timesheets.hours import contracted_minutes
from apps.timesheets.templatetags.hours import hhmm, hhmm_signed
from apps.timesheets.models import (
    DayLock, DayRecord, EntrySource, assert_unlocked, week_monday,
)
from apps.timesheets.zones import local_today, zone_for


# What every refusal says, in one place. The same sentence whichever door it
# came through, because it is the same fact — and because a lock explained four
# different ways is one nobody trusts.
LOCKED_MESSAGE = _(
    "%(date)s is locked and cannot be changed. Ask a manager to unlock that day — "
    "locking a month is how the hours in it are signed off."
)


def _monday_from(request):
    raw = request.GET.get("week") or request.POST.get("week")
    try:
        day = dt.date.fromisoformat(raw)
    except (TypeError, ValueError):
        day = dt.date.today()
    return week_monday(day)


# --------------------------------------------------------------------------
# One day, and the two windows onto a run of them
# --------------------------------------------------------------------------

# How many bookings a row shows before the rest go behind a count. Named here
# rather than written into the template, because the template's `forloop.counter`
# test and this arithmetic have to agree — two fours in two files is one four
# somebody changes.
BOOKINGS_SHOWN = 4


def _facts_for(employee, first, last):
    """The four queries a run of dates needs, whatever its length.

    Fetched once for the whole range rather than per day, which is what keeps a
    month at the same query count as a week: the rosters, the records with their
    segments, the public holidays and the absences that touch the range.
    """
    shifts = {}
    for shift in Shift.objects.filter(employee=employee, date__gte=first, date__lte=last):
        shifts.setdefault(shift.date, []).append(shift)

    records = {
        record.date: record
        for record in DayRecord.objects
        .filter(employee=employee, date__gte=first, date__lte=last)
        .prefetch_related("segments")
    }

    holidays = {
        row.date: row.name
        for row in BankHoliday.objects.filter(date__gte=first, date__lte=last)
    }

    absences = list(
        employee.absences
        .filter(start_date__lte=last, end_date__gte=first)
        .exclude(status__in=(RequestStatus.REJECTED, RequestStatus.WITHDRAWN))
        .select_related("special_type", "closure")
    )
    # One query for the month rather than one per row — the fifth, and the only
    # one this added.
    locks = DayLock.dates_between(employee, first, last)
    return shifts, records, holidays, absences, locks


def _day_row(employee, day, facts, settings, rules, today=None):
    """Everything one date is worth to one person.

    **The single place any of this is decided.** The week window and the month
    window both come through here, so a figure cannot read one way on the start
    page and another on the timesheet — which is the bug this app can least
    afford, and two implementations is the only way to get it.

    The row carries the facts a day has:

    * what was **rostered** (the plan, from ``apps.roster``),
    * what was **entered** (the record, or ``None`` for a day nobody has
      answered for — which is not the same as a day of zero hours),
    * whether the two **agree**, which is the line a manager reads first,
    * what else was true of the date: a public holiday, an absence, or a day the
      contract gives no hours,
    * and the figures the month's columns are: what the bookings came to, what
      the break took off, what was corrected by hand, and the saldo.
    """
    shifts, records, holidays, absences, locks = facts
    today = today or dt.date.today()

    record = records.get(day)
    planned = shifts.get(day, [])
    absence = next((a for a in absences if a.start_date <= day <= a.end_date), None)

    # `on=day`, not today. Somebody who dropped their Wednesdays in April still
    # worked them in February, and a month reprinted afterwards has to say so —
    # that is the whole reason the contract is a history.
    contracted = contracted_minutes(employee.hours_on_weekday(day.weekday(), on=day))
    is_working_day = employee.works_on(day)
    due = contracted if is_working_day else 0

    # **A record carrying only a comment is not an answer about hours.**
    #
    # The month lets somebody write a note against any date, so a row can exist
    # with no bookings and no correction on it. Reading that as nought hours
    # worked would print "0:00" where the page has always printed "—", and the
    # two are different statements: one says they worked none of it, the other
    # says nobody has answered yet. The saldo is unaffected either way — the
    # contracted hours are owed regardless — so this changes only what the
    # column claims to know.
    has_hours = bool(record) and bool(
        list(record.segments.all()) or record.correction_minutes
    )
    worked = record.worked_minutes if has_hours else None

    # What an absence hands back. A sick day is paid as though it had been
    # worked (§3 EFZG) and so is a day of leave (§11 BUrlG), so both credit the
    # contracted hours and the week comes out level instead of showing a
    # shortfall the employee does not owe. Time off in lieu credits nothing,
    # deliberately — the shortfall *is* the overtime being spent. A public
    # holiday credits too, for the same reason as leave.
    credited = 0
    if absence is not None and day not in holidays:
        credited = absence.credited_minutes(day, due)
    elif day in holidays and is_working_day:
        credited = due

    counted = (worked or 0) + credited

    return {
        "date": day,
        "record": record,
        "shifts": planned,
        "planned_minutes": sum(shift.minutes for shift in planned),
        "worked_minutes": worked,
        "contracted_minutes": due,
        # Hours the day is worth without anybody having worked them, and what
        # the row names as the reason. Kept beside the worked figure rather than
        # folded into it, because "you were ill" and "you worked eight hours"
        # are different sentences and a timesheet that could not tell them apart
        # would be no use in the argument it exists for.
        "credited_minutes": credited,
        "counted_minutes": counted,
        # The three the month prints separately, because a day that adds up is a
        # day somebody can check: the bookings, what came off them, and what was
        # put on by hand.
        "gross_minutes": record.gross_minutes if record else None,
        "break_minutes": record.break_minutes if record else None,
        "correction_minutes": record.correction_minutes if record else 0,
        "correction_reason": record.correction_reason if record else "",
        "note": record.note if record else "",
        "bookings": record.bookings if record else [],
        # How many punches the cell has no room for. Four is what fits without
        # the row growing, and the row must not grow: this is a grid read down a
        # column, and a day that gets taller pushes every figure below it out of
        # the place the eye last found it. The rest are one click away in the
        # pop-up, which is where they can be corrected as well as read.
        "hidden_bookings": max(0, (len(record.bookings) if record else 0) - BOOKINGS_SHOWN),
        # **Actual minus supposed**, so a longer day is a surplus and reads
        # green. The other way round would disagree in sign with `difference`
        # here, with `hours_balance` and with every figure on the start page —
        # one page saying +0:30 while another says -0:30 about the same Tuesday
        # is not a presentation choice, it is a wrong number.
        #
        # Nothing at all in two cases, and they are different questions.
        #
        # A day with no record, no credit and no contracted hours has no saldo
        # because there is nothing to compare: a Sunday nobody worked is not a
        # saldo of nought, and a column of 0:00 down every weekend buries the
        # days that are actually level.
        #
        # **A day in the future has none either.** A contract that says eight
        # hours next Tuesday is not a debt somebody has already failed to pay,
        # and drawing it in red down the rest of the month says exactly that —
        # on the first of the month it made an ordinary employee look 176 hours
        # short. The same clamp `hours_balance` makes, for the same reason.
        "saldo": (
            (counted - due) if (has_hours or credited or due) and day <= today else None
        ),
        # Only meaningful when both exist *and the day is finished*. A day with a
        # record and no roster is not "different from what was asked" — nothing
        # was asked. And a day still running is not different either; it is not
        # yet anything, and flagging it would put an attention pill on every
        # shift the moment somebody pressed Start.
        "differs_from_roster": bool(
            has_hours and planned and not record.is_running
            and not record.matches_roster(planned)
        ),
        "break_is_override": bool(record and record.break_is_override),
        # A stretch started and not stopped. The row draws it as running rather
        # than as a day of nought hours, which is what the totals would
        # otherwise make it look like.
        "is_running": bool(record and record.is_running),
        "running_since": record.running_segment.start if record and record.is_running else None,
        "required_break": (
            settings.required_break(*record.shape, rules=rules) if record else None
        ),
        "holiday": holidays.get(day),
        "absence": absence,
        "is_half_day": bool(absence and absence.is_half_day),
        # What the status pop-up opens on, and whether it may open at all.
        #
        # **A closure is the employer's and a range is not one date.** Withdrawing
        # either from a single cell would be answering a question the cell did
        # not ask: a closure belongs to everybody at once, and taking one date
        # out of a fortnight's holiday is a split, which is four more states and
        # no clearer than editing it where it was booked. Both send somebody to
        # the absences page instead, which is where those live.
        "status_kind": absence.kind if absence else "",
        "status_special": absence.special_type_id if absence else "",
        "status_note": absence.reason if absence else "",
        "status_editable": absence is None or bool(
            absence.closure_id is None and absence.start_date == absence.end_date
        ),
        "is_working_day": is_working_day,
        # **Locked: finished, and not to be changed.** Every write path checks
        # it again — this is only what the page draws, and a row that merely
        # *looked* locked would be a lock made of CSS.
        "is_locked": day in locks,
        "is_today": day == today,
        "is_future": day > today,
        "is_weekend": day.weekday() >= 5,
        # A day worth asking somebody to answer: they were rostered, it is not
        # in the future, and there is no record and no absence.
        "awaiting": bool(
            planned and not record and absence is None and day <= today
        ),
    }


def _rows_for(employee, days, settings=None, rules=None):
    """``_day_row`` over a run of dates, with the queries done once."""
    settings = settings or OrgSettings.current()
    if rules is None and settings.is_stored:
        rules = list(settings.break_rules.all())
    facts = _facts_for(employee, days[0], days[-1])
    today = dt.date.today()
    return settings, rules, [
        _day_row(employee, day, facts, settings, rules, today) for day in days
    ]


# --------------------------------------------------------------------------
# The week — the start page and the team overview
# --------------------------------------------------------------------------

def build_week(employee, monday, settings=None):
    """Everything one person's week is: seven rows, and the totals under them.

    Kept after the timesheet went monthly, because two pages still ask the week
    question and it is a different question: the start page asks "what does this
    week still want from me", and the team overview asks it of everybody at
    once. Both are built from ``_day_row``, so neither can drift from the month.
    """
    days = [monday + dt.timedelta(days=offset) for offset in range(7)]
    settings, rules, rows = _rows_for(employee, days, settings)

    worked_total = sum(row["worked_minutes"] or 0 for row in rows)
    credited_total = sum(row["credited_minutes"] for row in rows)
    contracted_total = sum(row["contracted_minutes"] for row in rows)
    return {
        "employee": employee,
        "monday": monday,
        "sunday": days[-1],
        "rows": rows,
        "worked_total": worked_total,
        "planned_total": sum(row["planned_minutes"] for row in rows),
        "contracted_total": contracted_total,
        "credited_total": credited_total,
        "counted_total": worked_total + credited_total,
        # Worked *plus what an absence credits*, minus contracted.
        #
        # This reverses an earlier decision and the reversal is the point: the
        # first version added nothing back, so a fortnight's sickness showed as
        # eighty hours of shortfall — a debt the employee does not owe and that
        # German law says outright they do not (§3 EFZG for illness, §11 BUrlG
        # for leave). Reporting it was not a conservative simplification; it was
        # a wrong figure in the direction that costs the employee.
        #
        # What is *not* credited is time off in lieu, and that is what keeps the
        # overtime mechanism working: the shortfall on such a day is the whole
        # of how overtime is drawn down.
        "difference": worked_total + credited_total - contracted_total,
        "unconfirmed": sum(
            1 for row in rows if row["record"] and not row["record"].is_confirmed
        ),
        "awaiting": sum(1 for row in rows if row["awaiting"]),
        "previous_week": monday - dt.timedelta(days=7),
        "next_week": monday + dt.timedelta(days=7),
        "this_week": week_monday(dt.date.today()),
        "today": dt.date.today(),
        "settings": settings,
        # Which of the two buttons to draw, and since when. Read from the
        # database rather than from the rows above, because a stretch started
        # last night is still running this morning and is not on this week at all
        # once the week rolls over.
        "clock": clocking.state_for(employee),
        # Everything owed, up to the end of the week being looked at. This is
        # where an opening balance carried in from a previous contract becomes
        # visible — without it the figure would be stored and never shown, which
        # is a figure nobody can check.
        "running": hours_balance(employee, until=days[-1], settings=settings),
    }


# --------------------------------------------------------------------------
# The month — the timesheet itself
# --------------------------------------------------------------------------

def month_start(day):
    """The first of the month ``day`` falls in."""
    return day.replace(day=1)


def month_shift(first, months):
    """``months`` whole months either side of a first-of-the-month.

    Written out rather than reached for in a library, because the arithmetic is
    two lines and a month is the one calendar unit that cannot be added as a
    ``timedelta`` — ``+ 30 days`` lands in February twice a year and in the same
    month once.
    """
    index = (first.year * 12 + first.month - 1) + months
    return dt.date(index // 12, index % 12 + 1, 1)


def month_end(first):
    """The last date of the month beginning at ``first``."""
    return month_shift(first, 1) - dt.timedelta(days=1)


def _month_from(request):
    """``?month=YYYY-MM`` off the query string, or this month.

    ``YYYY-MM-DD`` is accepted too and read as the month it falls in, so a link
    carrying a date — from the roster, or from a message naming a day — lands on
    the right page instead of on today's.
    """
    raw = (request.GET.get("month") or request.POST.get("month") or "").strip()
    for text in (raw, raw + "-01"):
        try:
            return month_start(dt.date.fromisoformat(text))
        except (TypeError, ValueError):
            continue
    return month_start(dt.date.today())


def _month_choices(employee, current):
    """The months the dropdown offers, newest first.

    From the month this person's records begin — their opening date, or their
    earliest contract — through to a year ahead, and always including whichever
    month is being looked at. Bounded rather than open-ended because a select
    with every month since 1970 in it is a select nobody scrolls; a year ahead
    because a roster is planned forward and checking next spring's rostered
    hours is an ordinary thing to do.
    """
    last = max(month_shift(month_start(dt.date.today()), 12), current)
    first = month_start(employee.opening_date or dt.date.today())
    # Four years of history at most in the list itself. Anything older is still
    # reachable by editing the query string, and is not what a dropdown is for.
    first = max(first, month_shift(last, -48))
    # **Last, and after the clamp.** The month being looked at is always in the
    # list, whatever it is: a select whose selected option is not among its
    # options renders as the first entry instead, so an old link would show a
    # picker that disagrees with the page it is on.
    first = min(first, current)

    months = []
    step = last
    while step >= first:
        months.append(step)
        step = month_shift(step, -1)
    return months


def build_month(employee, first, settings=None):
    """One person's month: a row per date, and the running saldo down the side.

    The running column is the reason ``carried`` exists. It starts from what
    this person carried into the month — their opening balance plus everything
    up to the last day of the previous month — so the figure on the last row of
    the month *is* their balance to date, and the same number ``hours_balance``
    gives for that date. A column that reset to nought every month would be a
    different number from the one on the start page, about the same person, on
    the same day.
    """
    last = month_end(first)
    days = [first + dt.timedelta(days=offset) for offset in range((last - first).days + 1)]
    settings, rules, rows = _rows_for(employee, days, settings)

    # Everything up to the day before this month began. `hours_balance` clamps
    # `until` at today of its own accord, so a month in the future carries in
    # today's balance and adds nothing to it — which is right: next March is not
    # a shortfall anybody has already failed to pay.
    carried = hours_balance(employee, until=first - dt.timedelta(days=1), settings=settings)
    today = dt.date.today()

    running = carried["total"]
    for row in rows:
        if row["saldo"] is not None:
            running += row["saldo"]
            row["running_saldo"] = running
        else:
            row["running_saldo"] = None

    # **Every total is to date, and the whole month's contracted hours are
    # reported separately.**
    #
    # Summing the future's contracted hours into the month's figures is what
    # made an ordinary employee read as 176 hours short on the first of the
    # month. It is also what stops the table adding up: the saldo column would
    # total one number while the last row of the running column reached
    # another, about the same person on the same day, in two cells a centimetre
    # apart.
    #
    # So the footer is the sum of the cells it is under, and the month's own
    # plan — what is still to come — is `contracted_month`, said in its own row
    # rather than folded into a figure that is about what has happened.
    done = [row for row in rows if row["date"] <= today]
    worked_total = sum(row["worked_minutes"] or 0 for row in done)
    credited_total = sum(row["credited_minutes"] for row in done)
    contracted_total = sum(row["contracted_minutes"] for row in done)
    return {
        "employee": employee,
        "month": first,
        "month_end": last,
        "rows": rows,
        "months": _month_choices(employee, first),
        "previous_month": month_shift(first, -1),
        "next_month": month_shift(first, 1),
        "this_month": month_start(today),
        "today": today,
        "carried": carried["total"],
        "carried_on": first - dt.timedelta(days=1),
        "opening": carried["opening"],
        "opening_on": carried["opening_on"],
        "worked_total": worked_total,
        "credited_total": credited_total,
        "counted_total": worked_total + credited_total,
        "contracted_total": contracted_total,
        "correction_total": sum(row["correction_minutes"] for row in done),
        "break_total": sum(row["break_minutes"] or 0 for row in done),
        # What the whole month is contracted for, future days included. The one
        # figure on the page that is about the plan rather than about what has
        # happened, which is why it is named apart from `contracted_total`.
        "contracted_month": sum(row["contracted_minutes"] for row in rows),
        "is_finished": last <= today,
        # How much of the month is closed. Three states rather than two, because
        # "partly" is a real one: a manager unlocks a single day to correct it
        # and the month is neither open nor shut until they lock it again.
        "locked_days": sum(1 for row in rows if row["is_locked"]),
        "is_locked": all(row["is_locked"] for row in rows),
        "has_locks": any(row["is_locked"] for row in rows),
        # So the template's "show the first four" and `hidden_bookings` cannot
        # disagree about how many four is.
        "bookings_shown": BOOKINGS_SHOWN,
        "difference": worked_total + credited_total - contracted_total,
        "balance_to_date": running,
        "awaiting": sum(1 for row in rows if row["awaiting"]),
        "settings": settings,
        "rules": rules,
        # **No `clock` key.** Start and Stop are the topbar's now, supplied by
        # `apps.timesheets.context.clock` on every page — and a `clock` here
        # would *shadow* it, because a view's context wins over a processor's.
        # It did, silently: the bar kept working and the half of it the
        # processor adds simply rendered blank.
    }


@login_required
def home(request):
    """The start page: this week, and whatever is asking to be dealt with.

    Deliberately not a dashboard of statistics. The two questions somebody opens
    this app with are "have I confirmed my hours" and — for a manager — "is
    anybody waiting on me", and a page of totals answers neither.
    """
    employee = Employee.for_user(request.user)
    context = {"employee": employee}

    if employee is not None:
        monday = week_monday(dt.date.today())
        week = build_week(employee, monday)
        context["week"] = week
        context["balance"] = Balance(employee, dt.date.today().year)
        context["running"] = week["running"]

    if request.user.is_authenticated and context.get("employee") is None:
        context["no_contract"] = True

    from apps.employees.permissions import is_manager as _is_manager

    if _is_manager(request.user):
        context["waiting_requests"] = (
            Absence.objects.filter(status=RequestStatus.REQUESTED)
            .select_related("employee").order_by("start_date")[:5]
        )
        context["unconfirmed_people"] = _people_with_unconfirmed_days()

    return render(request, "timesheets/home.html", context)


def _people_with_unconfirmed_days():
    """Who has entered hours nobody has agreed to, in the last fortnight.

    A fortnight rather than everything, because the useful question is "who
    needs chasing now" — a list that grows without bound is one nobody reads
    twice.
    """
    since = dt.date.today() - dt.timedelta(days=14)
    rows = (
        DayRecord.objects.filter(confirmed_at__isnull=True, date__gte=since)
        .select_related("employee").order_by("employee__first_name", "date")
    )
    grouped = {}
    for record in rows:
        grouped.setdefault(record.employee, []).append(record)
    return sorted(grouped.items(), key=lambda pair: pair[0].full_name)


def _month_context(request, employee):
    """The month page's context. One function, two doors, for the usual reason."""
    from apps.absences.models import AbsenceKind
    from apps.organisation.models import SpecialLeaveType

    settings = OrgSettings.current()
    rules = list(settings.break_rules.all()) if settings.is_stored else None
    context = build_month(employee, _month_from(request), settings)
    # The four a status cell may set. A closure is the employer's to declare and
    # is deliberately absent — offering it here would let somebody record "the
    # workplace was shut" for one person on one day, which is not a thing that
    # can be true.
    context["status_kinds"] = [
        (AbsenceKind.HOLIDAY, AbsenceKind.HOLIDAY.label),
        (AbsenceKind.SICK, AbsenceKind.SICK.label),
        (AbsenceKind.OVERTIME, AbsenceKind.OVERTIME.label),
        (AbsenceKind.SPECIAL, AbsenceKind.SPECIAL.label),
    ]
    # Only the types this person has been granted — the same restriction
    # `AbsenceRequestForm` makes, for the same reason: a type nobody granted is
    # not theirs, and offering it produces a request a manager has to decline
    # and then explain.
    context["special_types"] = SpecialLeaveType.objects.filter(
        grants__employee=employee, is_active=True,
    )
    context["is_own"] = (
        employee.user_id is not None and employee.user_id == request.user.id
    )
    # The break table as plain data, so the pop-up can say what the break will
    # be while somebody is still typing the bookings rather than only after the
    # save. The browser gets the *rules* and applies the same formula — the only
    # version that stays right as the times change. `hours.js` carries the four
    # lines and a test holds the two implementations to the same answers.
    context["break_rules_json"] = _break_rules_json(settings, rules)
    return context


@login_required
def mine(request):
    employee = Employee.for_user(request.user)
    if employee is None:
        return render(request, "absences/no_contract.html")
    return render(request, "timesheets/month.html", _month_context(request, employee))


@manager_required
def employee_month(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    return render(request, "timesheets/month.html", _month_context(request, employee))


@manager_required
def team(request):
    """Everybody's week on one page, one row per person.

    The overview a manager opens on a Monday morning. Each row is that person's
    week collapsed to four numbers and a count of what is unanswered; the name
    is a link into the same week view they see themselves.
    """
    monday = _monday_from(request)
    settings = OrgSettings.current()
    weeks = [
        build_week(employee, monday, settings)
        for employee in Employee.objects.filter(is_active=True)
    ]
    return render(request, "timesheets/team.html", {
        "monday": monday,
        "weeks": weeks,
        "previous_week": monday - dt.timedelta(days=7),
        "next_week": monday + dt.timedelta(days=7),
        "this_week": week_monday(dt.date.today()),
        "days": [monday + dt.timedelta(days=offset) for offset in range(7)],
        "worked_total": sum(week["worked_total"] for week in weeks),
        "credited_total": sum(week["credited_total"] for week in weeks),
        "counted_total": sum(week["counted_total"] for week in weeks),
        "contracted_total": sum(week["contracted_total"] for week in weeks),
        "awaiting_total": sum(week["awaiting"] for week in weeks),
        "running_now": [week for week in weeks if week["clock"]["running"]],
    })


# --------------------------------------------------------------------------
# Start and Stop
# --------------------------------------------------------------------------

@login_required
@require_POST
def clock(request, pk):
    """One button, doing whichever of the two things makes sense.

    A single route rather than a start route and a stop route, because the page
    only ever offers one of them and a second URL would be a second thing that
    could get out of step with the state. Which one it is is decided *here*,
    from the database, and not from what the form said — a page left open in
    another tab must not be able to start a second shift by being the older of
    the two.

    ``apps/timesheets/clocking.py`` holds the rules; this is the door.
    """
    employee = get_object_or_404(Employee, pk=pk)
    if not own_or_manager(request, employee):
        raise Http404

    # Back to the page the button was pressed on. It is in the topbar now, so
    # that is any page in the app — landing everybody on the timesheet would
    # throw away whatever they were doing when they remembered to clock in.
    back = _safe_next(request) or _month_url(request, employee, local_today(zone_for(employee)))

    try:
        # A locked day cannot be clocked into either. Rare — it means somebody
        # closed the month that is still running — but Start writes a record
        # like anything else, and a lock with an exception nobody documented is
        # not a lock.
        assert_unlocked(employee, local_today(zone_for(employee)))
        if clocking.open_stretch(employee) is None:
            segment = clocking.start(employee, by=request.user)
            messages.success(request, _("Started at %(time)s.") % {
                "time": segment.start.strftime("%H:%M"),
            })
        else:
            segment = clocking.stop(employee, by=request.user)
            messages.success(request, _(
                "Stopped at %(time)s. %(hours)s recorded for %(date)s so far."
            ) % {
                "time": segment.end.strftime("%H:%M"),
                "hours": _hours_label(segment.day.worked_minutes, request.user),
                "date": segment.day.date.strftime("%d.%m.%Y"),
            })
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect(back)

    return redirect(back)


def _safe_next(request):
    """``?next``/``next=`` if it is a URL on this site, else ``None``.

    A redirect target taken on trust is an open redirect, and this one arrives
    on a POST from a form that anybody can put on their own page — a "clock in"
    button on somebody else's site would otherwise be able to bounce a signed-in
    employee anywhere at all, from a URL that starts with the name of the app
    they trust.
    """
    from django.utils.http import url_has_allowed_host_and_scheme

    target = request.POST.get("next") or request.GET.get("next")
    if not target:
        return None
    if url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return target
    return None

# --------------------------------------------------------------------------
# One day
# --------------------------------------------------------------------------

@login_required
def day(request, pk, date):
    """Enter or correct one day's hours.

    ``pk`` is the employee and the route is the same one a manager uses, gated
    by ``own_or_manager``: your own day always, somebody else's only as a
    manager. One view rather than two, for the same reason the week is one
    function.
    """
    employee = get_object_or_404(Employee, pk=pk)
    if not own_or_manager(request, employee):
        raise Http404

    try:
        the_date = dt.date.fromisoformat(date)
    except ValueError as error:
        raise Http404 from error

    settings = OrgSettings.current()
    rules = list(settings.break_rules.all()) if settings.is_stored else None
    record = DayRecord.objects.filter(employee=employee, date=the_date).first()
    shifts = list(Shift.objects.filter(employee=employee, date=the_date))
    locked = DayLock.is_locked(employee, the_date)

    if request.method == "POST":
        if locked:
            messages.error(request, LOCKED_MESSAGE % {
                "date": the_date.strftime("%d.%m.%Y"),
            })
            return redirect(_month_url(request, employee, the_date))
        instance = record or DayRecord(employee=employee, date=the_date)
        form = DayForm(request.POST, instance=instance)
        # Bound to the instance whether or not it has been saved: an inline
        # formset on a pk-less parent simply has an empty queryset, which is
        # exactly right for a day being entered for the first time.
        formset = SegmentFormSet(request.POST, instance=instance)

        # **Both validated before anything is written.** The version that saved
        # the record first and then validated the segments left an empty
        # DayRecord behind every time a day was rejected — and an empty record
        # is not nothing: the week view renders it as a day somebody entered and
        # worked nought hours, which is a confident wrong answer rather than an
        # error.
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                # The order inside here is what the whole view turns on: save
                # the record, save the segments, *then* let the form work the
                # break out — it is computed from the segments, and computing it
                # first gives every new day a break of nought.
                draft = form.save(commit=False)
                draft.employee = employee
                draft.date = the_date
                draft.source = EntrySource.MANUAL
                draft.save()

                formset.instance = draft
                formset.save()

                draft.refresh_from_db()
                form.instance = draft
                form.save(settings=settings, rules=rules)

                # The hours have just changed, so an earlier agreement to them
                # is no longer an agreement to anything somebody has seen.
                draft.unconfirm()

            messages.success(request, _("The day was saved."))
            return redirect(_month_url(request, employee, the_date))
    else:
        form = DayForm(instance=record)
        formset = SegmentFormSet(instance=record)

    return render(request, "timesheets/day.html", {
        "employee": employee,
        "date": the_date,
        "record": record,
        "shifts": shifts,
        "planned_minutes": sum(shift.minutes for shift in shifts),
        "form": form,
        "formset": formset,
        "is_own": employee.user_id == request.user.id,
        "contracted_minutes": contracted_minutes(
            employee.hours_on_weekday(the_date.weekday(), on=the_date)
        ),
        "settings": settings,
        "locked": locked,
        "week": week_monday(the_date),
        # The break table, so the page can answer while somebody is typing
        # rather than only on save. The browser gets the *rules*, not a computed
        # answer, and applies the same formula — which is the only version that
        # stays right as the times change. `hours.js` carries the four lines and
        # a test holds the two implementations to the same answers.
        "break_rules_json": _break_rules_json(settings, rules),
    })


def _break_rules_json(settings, rules):
    """The break tiers as plain data for the page.

    Falls back to the defaults when the table is empty, exactly as
    ``OrgSettings.required_break`` does — otherwise a fresh installation would
    show "0 min" in the browser while the server saved 30, and the disagreement
    would look like the save having gone wrong.
    """
    from apps.organisation.models import DEFAULT_BREAK_RULES

    if rules:
        return [{"over": rule.over_minutes, "break": rule.break_minutes} for rule in rules]
    return [{"over": over, "break": length} for over, length in DEFAULT_BREAK_RULES]


def _month_url(request, employee, date):
    """Back to whichever timesheet the day was reached from.

    Decided by whose day it is rather than by a ``?next=``, so a manager editing
    somebody's Tuesday lands back on that person's month and an employee lands
    on their own. Sending everybody to ``mine`` would drop a manager onto a page
    that does not contain the change they just made.
    """
    month = month_start(date).strftime("%Y-%m")
    if employee.user_id is not None and employee.user_id == request.user.id:
        return f"{reverse('timesheets:mine')}?month={month}"
    return f"{reverse('timesheets:employee', args=[employee.pk])}?month={month}"


@login_required
@require_POST
def confirm_day(request, pk, date):
    """"Yes, I worked what I was rostered" — the one-tap path.

    Copies the shifts into a record and marks it agreed. This is the gesture the
    whole app is arranged around: on a normal day nothing needs typing, and the
    manual form exists for the days that are not normal.
    """
    employee = get_object_or_404(Employee, pk=pk)
    if not own_or_manager(request, employee):
        raise Http404
    try:
        the_date = dt.date.fromisoformat(date)
    except ValueError as error:
        raise Http404 from error

    if DayLock.is_locked(employee, the_date):
        messages.error(request, LOCKED_MESSAGE % {
            "date": the_date.strftime("%d.%m.%Y"),
        })
        return redirect(_month_url(request, employee, the_date))

    settings = OrgSettings.current()
    rules = list(settings.break_rules.all()) if settings.is_stored else None
    shifts = list(Shift.objects.filter(employee=employee, date=the_date))

    if not shifts:
        messages.error(request, _(
            "There is nothing rostered on that day, so there is nothing to confirm. "
            "Enter the hours instead."
        ))
        return redirect(_month_url(request, employee, the_date))

    record = DayRecord.from_shifts(
        employee, the_date, shifts, by=request.user, settings=settings, rules=rules,
    )
    messages.success(request, _("%(date)s was confirmed: %(hours)s worked.") % {
        "date": the_date.strftime("%d.%m.%Y"),
        "hours": _hours_label(record.worked_minutes, request.user),
    })
    return redirect(_month_url(request, employee, the_date))


@login_required
@require_POST
def confirm_week(request):
    """Confirm every rostered day of a week that has nothing entered yet.

    **Only the days with no record.** A day somebody has already entered by hand
    is left alone, because overwriting it with the rostered times would silently
    discard the correction they made — which is the one thing this button must
    never do. The message says how many were skipped and why.
    """
    employee = Employee.for_user(request.user)
    if employee is None:
        return render(request, "absences/no_contract.html")

    monday = _monday_from(request)
    days = [monday + dt.timedelta(days=offset) for offset in range(7)]
    today = dt.date.today()
    settings = OrgSettings.current()
    rules = list(settings.break_rules.all()) if settings.is_stored else None

    shifts = {}
    for shift in Shift.objects.filter(employee=employee, date__gte=days[0], date__lte=days[-1]):
        shifts.setdefault(shift.date, []).append(shift)
    existing = set(
        DayRecord.objects.filter(employee=employee, date__gte=days[0], date__lte=days[-1])
        .values_list("date", flat=True)
    )

    # Skipped rather than refused. This button is a bulk gesture over a week
    # that may be half closed, and refusing the whole thing because one day of
    # it is locked would leave nothing to press.
    locked = DayLock.dates_between(employee, days[0], days[-1])

    confirmed = skipped = 0
    for day_date in days:
        if day_date > today or day_date not in shifts:
            continue
        if day_date in existing or day_date in locked:
            skipped += 1
            continue
        DayRecord.from_shifts(
            employee, day_date, shifts[day_date], by=request.user,
            settings=settings, rules=rules,
        )
        confirmed += 1

    if confirmed and skipped:
        messages.success(request, _(
            "%(confirmed)s days were confirmed. %(skipped)s already had hours entered "
            "and were left exactly as they are."
        ) % {"confirmed": confirmed, "skipped": skipped})
    elif confirmed:
        messages.success(request, _("%(confirmed)s days were confirmed.") % {"confirmed": confirmed})
    elif skipped:
        messages.info(request, _(
            "Every rostered day this week already has hours entered, so nothing was changed."
        ))
    else:
        messages.info(request, _("There is nothing rostered this week to confirm."))
    return redirect(f"{reverse('timesheets:mine')}?month={monday.strftime('%Y-%m')}")


# --------------------------------------------------------------------------
# Saving the month
# --------------------------------------------------------------------------

class _DayRejected(Exception):
    """One date the month cannot be saved with. Carries the date and the reason.

    An exception rather than a collected list, because the save is atomic and
    has to stop: half a month written and half refused is a page whose figures
    are neither what was there before nor what somebody asked for, and no
    message can make that legible afterwards.
    """

    def __init__(self, date, message):
        super().__init__(message)
        self.date = date
        self.message = message


def _wanted_correction(request, raw):
    """``(minutes, reason)`` for one date, off the POST. Raises ``_DayRejected``.

    A correction with nothing saying why is refused here as well as in
    ``DayRecord.clean``, because this is where the message can name the date —
    "on 14.09." rather than "on one of the days below".
    """
    field = SignedMinutesField()
    raw_value = (request.POST.get(f"correction-{raw}") or "").strip()
    reason = (request.POST.get(f"why-{raw}") or "").strip()[:200]
    if not raw_value:
        return 0, ""
    try:
        minutes = field.clean(raw_value) or 0
    except ValidationError as error:
        raise _DayRejected(raw, error.messages[0]) from error
    if minutes and not reason:
        raise _DayRejected(raw, _(
            "There is a correction with nothing saying why. A correction nobody can "
            "account for is the one entry on a timesheet that cannot be defended."
        ))
    return minutes, (reason if minutes else "")


def _apply_day(request, employee, date, raw, record, settings, rules, tz):
    """Write one date, or leave it exactly as it was. Returns what happened.

    ``"kept"`` when nothing about the row differs from what is stored — which is
    most of a month, most of the time, and is why a Save on a page of thirty-one
    rows is a handful of writes rather than thirty-one.

    ``"removed"`` when the row has been emptied: no bookings, no correction and
    no comment. That is the only way to take a day off a timesheet, and it has
    to exist — a record of nought hours and no record at all are different
    statements, and the app has always drawn them differently.
    """
    times = request.POST.getlist(f"time-{raw}")
    kinds = request.POST.getlist(f"kind-{raw}")
    note = (request.POST.get(f"note-{raw}") or "").strip()[:200]
    correction, why = _wanted_correction(request, raw)

    try:
        pairs = bookings.clean(date, list(zip(kinds, times)), tz)
    except ValidationError as error:
        raise _DayRejected(raw, error.messages[0]) from error

    stored = (
        [(s.start, s.end) for s in record.segments.all()] if record else []
    )
    hours_changed = pairs != stored or (record.correction_minutes if record else 0) != correction
    note_changed = (record.note if record else "") != note
    why_changed = (record.correction_reason if record else "") != why

    if not (hours_changed or note_changed or why_changed):
        return "kept"

    if not pairs and not correction and not note:
        if record is None:
            return "kept"
        record.delete()
        return "removed"

    if record is None:
        record = DayRecord(employee=employee, date=date)
        record.save()

    if pairs != stored:
        record.set_bookings(pairs)
        # By hand, whatever it was before. A day whose times were copied from
        # the roster and then edited is no longer "confirmed as rostered", and
        # leaving the source saying so would make the timesheet claim an
        # agreement that is not what is on the row.
        record.source = EntrySource.MANUAL
        record.apply_break_rules(settings=settings, rules=rules)

    record.correction_minutes = correction
    record.correction_reason = why
    record.note = note
    record.save()

    if hours_changed:
        # The figures have changed underneath any earlier agreement to them, so
        # the agreement is no longer an agreement to anything somebody has seen.
        # A comment is not hours and deliberately does not do this.
        record.unconfirm()
    return "saved"


def _month_payload(employee, first, settings=None):
    """The month as plain data, for a page that has just changed one day of it.

    Everything the browser needs to repaint and **nothing it has to work out**.
    An edit to the third of the month moves the running total on every row below
    it and all six figures in the footer; a reply carrying only the edited row
    would leave the rest of the column stale, and the alternative — repeating the
    prefix sum, the break rules and the credited-hours branches in JavaScript —
    is exactly the duplication ``build_month`` exists to avoid.

    Every duration arrives **already written**, in the page's own ``hh:mm``.
    Handing over minutes and letting the browser format them is one more place
    for the two to disagree about a rounding, and the figures on this page are
    ones somebody is paid against.

    It costs what rendering the month cost: the same four queries.
    """
    month = build_month(employee, first, settings)
    return {
        "rows": [
            {
                "date": row["date"].isoformat(),
                "bookings": [
                    {"kind": booking["kind"], "time": booking["time"].strftime("%H:%M")}
                    for booking in row["bookings"]
                ],
                # None where the cell should read "—": a date with no record at
                # all has no break, which is a different statement from a break
                # of nought.
                "break_display": hhmm(row["break_minutes"]) if row["record"] else None,
                "break_is_override": row["break_is_override"],
                "correction_minutes": row["correction_minutes"],
                "correction": hhmm_signed(row["correction_minutes"]),
                "correction_reason": row["correction_reason"],
                "note": row["note"],
                "counted": hhmm(row["counted_minutes"]) if (
                    row["worked_minutes"] is not None or row["credited_minutes"]
                ) else None,
                "credited": bool(row["credited_minutes"]),
                "saldo": hhmm_signed(row["saldo"]) if row["saldo"] is not None else None,
                "saldo_minutes": row["saldo"],
                "running": (
                    hhmm_signed(row["running_saldo"])
                    if row["running_saldo"] is not None else None
                ),
                "running_minutes": row["running_saldo"],
                "is_running": row["is_running"],
                "differs_from_roster": row["differs_from_roster"],
            }
            for row in month["rows"]
        ],
        "totals": {
            "break_display": hhmm(month["break_total"]),
            "correction": (
                hhmm_signed(month["correction_total"]) if month["correction_total"] else ""
            ),
            "counted": hhmm(month["counted_total"]),
            "contracted": hhmm(month["contracted_total"]),
            "difference": hhmm_signed(month["difference"]),
            "difference_minutes": month["difference"],
            "balance": hhmm_signed(month["balance_to_date"]),
            "balance_minutes": month["balance_to_date"],
        },
    }


@login_required
@require_POST
def set_status(request, pk, date):
    """Record — or clear — one day's absence, from the timesheet's status cell.

    **The forms are the absences app's own**, not a second implementation. Every
    rule about who may ask for what, which special types are theirs, whether the
    dates are working days at all and whether something already covers them
    lives in ``AbsenceRequestForm`` and ``SickForm``; this only ever fills in the
    one date the cell is on and hands them the rest. A parallel path here would
    be a second answer to "may this person book this day", and the two would
    disagree the first time either was changed.

    A form POST and a redirect rather than the JSON the rest of this page uses,
    and deliberately: a status changes what the *whole* month is worth — the
    credited hours, the saldo, the balance, the pills on the row — and a reload
    is both simpler and certainly right. It is also a thing somebody does a few
    times a month, not a few times an hour.
    """
    from apps.absences.forms import AbsenceRequestForm, SickForm
    from apps.absences.models import AbsenceKind, RequestStatus

    employee = get_object_or_404(Employee, pk=pk)
    if not own_or_manager(request, employee):
        raise Http404
    try:
        the_date = dt.date.fromisoformat(date)
    except ValueError as error:
        raise Http404 from error

    back = _month_url(request, employee, the_date)

    if DayLock.is_locked(employee, the_date):
        messages.error(request, LOCKED_MESSAGE % {
            "date": the_date.strftime("%d.%m.%Y"),
        })
        return redirect(back)

    existing = (
        employee.absences
        .exclude(status__in=(RequestStatus.REJECTED, RequestStatus.WITHDRAWN))
        .filter(start_date__lte=the_date, end_date__gte=the_date)
        .first()
    )

    if existing is not None:
        if existing.closure_id is not None:
            messages.error(request, _(
                "That day is a workplace closure, which is the employer's to declare "
                "and not something one timesheet can take back."
            ))
            return redirect(back)
        if existing.start_date != existing.end_date:
            messages.error(request, _(
                "That absence runs from %(from)s to %(to)s. Change it where it was "
                "booked — taking one day out of a range from here would have to split "
                "it, and a split nobody asked for is worse than an extra click."
            ) % {
                "from": existing.start_date.strftime("%d.%m.%Y"),
                "to": existing.end_date.strftime("%d.%m.%Y"),
            })
            return redirect(back)

    kind = request.POST.get("kind") or ""

    with transaction.atomic():
        if existing is not None:
            # Withdrawn rather than deleted, the same as `absences.request_cancel`:
            # the record still says the conversation happened, and a manager who
            # remembers approving something is not left with no trace of it.
            existing.status = RequestStatus.WITHDRAWN
            existing.save(update_fields=["status"])

        if not kind:
            messages.success(request, _("%(date)s has no status any more.") % {
                "date": the_date.strftime("%d.%m.%Y"),
            })
            return redirect(back)

        data = {
            "start_date": the_date.isoformat(),
            "end_date": the_date.isoformat(),
            "is_half_day": request.POST.get("is_half_day", ""),
        }
        if kind == AbsenceKind.SICK:
            form = SickForm(data, employee=employee)
        else:
            data.update({
                "kind": kind,
                "special_type": request.POST.get("special_type", ""),
                # No note on a sick day, here as everywhere else: a sick absence
                # records that somebody was ill and never why, and a free-text
                # box beside it is where a diagnosis ends up.
                "reason": request.POST.get("reason", ""),
            })
            form = AbsenceRequestForm(data, employee=employee)

        if not form.is_valid():
            # The rollback matters: without it a status that could not be saved
            # would still have withdrawn the one that was there, so a mistyped
            # correction would silently clear the day.
            transaction.set_rollback(True)
            messages.error(request, _("%(date)s could not be saved: %(why)s") % {
                "date": the_date.strftime("%d.%m.%Y"),
                "why": " ".join(
                    message for errors in form.errors.values() for message in errors
                ),
            })
            return redirect(back)

        absence = form.save(commit=False)
        absence.employee = employee
        if kind != AbsenceKind.SICK:
            # Always REQUESTED, even when a manager enters it — approving is a
            # separate press that leaves a row saying who decided it, and a
            # self-approving shortcut is exactly the audit trail this app keeps.
            absence.status = RequestStatus.REQUESTED
        absence.save()

    messages.success(request, _("%(date)s was recorded as %(status)s.") % {
        "date": the_date.strftime("%d.%m.%Y"),
        "status": absence.special_type.name if (
            absence.kind == AbsenceKind.SPECIAL and absence.special_type
        ) else absence.get_kind_display(),
    })
    return redirect(back)


@login_required
@require_POST
def set_status_mine(request, date):
    """The same, for the page whose path names no employee."""
    employee = Employee.for_user(request.user)
    if employee is None:
        raise Http404
    return set_status(request, employee.pk, date)


@login_required
@require_POST
def save_day(request, pk, date):
    """Write one day and answer with the month.

    **There is no Save button any more**, and this is what replaced it: a box
    that is left, or a pop-up that is accepted, writes that one day. The
    all-or-nothing question the month form had to answer does not arise — one
    day is the unit, so a day that cannot be read is refused on its own and
    every other day is untouched by construction.

    The refusal comes back as text for the pop-up to print rather than as a
    message on the next page load, because there is no next page load: the
    person is still looking at the box they typed into.
    """
    employee = get_object_or_404(Employee, pk=pk)
    if not own_or_manager(request, employee):
        raise Http404
    try:
        the_date = dt.date.fromisoformat(date)
    except ValueError as error:
        raise Http404 from error

    if DayLock.is_locked(employee, the_date):
        return JsonResponse({"ok": False, "error": LOCKED_MESSAGE % {
            "date": the_date.strftime("%d.%m.%Y"),
        }}, status=400)

    settings = OrgSettings.current()
    rules = list(settings.break_rules.all()) if settings.is_stored else None
    record = (
        DayRecord.objects.filter(employee=employee, date=the_date)
        .prefetch_related("segments").first()
    )

    try:
        with transaction.atomic():
            _apply_day(
                request, employee, the_date, date, record,
                settings, rules, zone_for(employee),
            )
            # One open stretch per person, checked over everything rather than
            # over this month: somebody clocked in yesterday and given a second
            # open booking today is a state Stop cannot read, and this is the
            # one door besides `clocking.start` that could create it.
            open_days = list(
                DayRecord.objects
                .filter(employee=employee, segments__end__isnull=True)
                .distinct().values_list("date", flat=True)
            )
            if len(open_days) > 1:
                raise _DayRejected(date, _(
                    "There is more than one day with a coming and no going — %(dates)s. "
                    "Only one stretch can be left open at a time, or Stop has no way "
                    "of knowing which one it ended."
                ) % {"dates": ", ".join(d.strftime("%d.%m.") for d in sorted(open_days))})
    except _DayRejected as rejected:
        return JsonResponse({"ok": False, "error": rejected.message}, status=400)

    return JsonResponse({
        "ok": True,
        "month": _month_payload(employee, month_start(the_date), settings),
    })


@login_required
@require_POST
def save_day_mine(request, date):
    """The same, for the page whose path names no employee."""
    employee = Employee.for_user(request.user)
    if employee is None:
        raise Http404
    return save_day(request, employee.pk, date)


# --------------------------------------------------------------------------
# Closing a month
# --------------------------------------------------------------------------

def _month_summary(employee, first, settings=None):
    """One person's month as four figures and two counts, for the lock page.

    Deliberately **not** ``build_month``. That walks the balance back to the
    person's opening date to work out what they carried in, which is the one
    expensive thing on the page and is not a question this page asks — and it
    would ask it once per employee. What is wanted here is the month itself.
    """
    from apps.absences.models import RequestStatus

    last = month_end(first)
    days = [first + dt.timedelta(days=offset) for offset in range((last - first).days + 1)]
    settings, _rules, rows = _rows_for(employee, days, settings)
    today = dt.date.today()
    done = [row for row in rows if row["date"] <= today]

    worked = sum(row["worked_minutes"] or 0 for row in done)
    credited = sum(row["credited_minutes"] for row in done)
    contracted = sum(row["contracted_minutes"] for row in done)
    locked = sum(1 for row in rows if row["is_locked"])

    return {
        "employee": employee,
        "counted": worked + credited,
        "contracted": contracted,
        "difference": worked + credited - contracted,
        # Days somebody was rostered for and has not answered. A month with any
        # of these is one nobody should be signing off yet.
        "awaiting": sum(1 for row in done if row["awaiting"]),
        # **What stops the lock.** An undecided request inside the month would
        # change the credited hours the moment it was approved — after the month
        # had been signed off on the figures without it.
        "waiting": employee.absences.filter(
            status=RequestStatus.REQUESTED,
            start_date__lte=last, end_date__gte=first,
        ).count(),
        "locked_days": locked,
        "total_days": len(rows),
        "is_locked": locked == len(rows),
        "is_partly_locked": 0 < locked < len(rows),
    }


@manager_required
def month_end_page(request):
    """Closing a month: who is ready, and the button that shuts it.

    The parallel of ``absences.year_end`` and deliberately shaped like it — a
    periodic act a manager performs over everybody at once, with the figures
    they need in order to decide in front of them rather than one navigation
    away.
    """
    first = _month_from(request)
    settings = OrgSettings.current()
    people = [
        _month_summary(employee, first, settings)
        for employee in Employee.objects.filter(is_active=True)
    ]
    return render(request, "timesheets/month_end.html", {
        "month": first,
        "month_end": month_end(first),
        "people": people,
        "months": _month_choices_for_everybody(first),
        "previous_month": month_shift(first, -1),
        "next_month": month_shift(first, 1),
        "this_month": month_start(dt.date.today()),
        "locked_people": sum(1 for row in people if row["is_locked"]),
        "waiting_total": sum(row["waiting"] for row in people),
    })


def _month_choices_for_everybody(current):
    """The dropdown for a page that is about the whole team.

    ``_month_choices`` starts at one employee's opening date, which is not a
    question with an answer here. Two years back and a year forward, which is
    the range a month is ever closed in.
    """
    last = max(month_shift(month_start(dt.date.today()), 12), current)
    first = min(month_shift(last, -36), current)
    months = []
    step = last
    while step >= first:
        months.append(step)
        step = month_shift(step, -1)
    return months


@manager_required
@require_POST
def lock_month(request):
    """Lock — or unlock — a month for everybody who was ticked.

    **Refused while anything in the month is still waiting for a decision.**
    Approving a request afterwards would change the credited hours of a month
    that had already been signed off without them, which is the one thing a
    lock is supposed to make impossible. The message names who, so the fix is
    one click away on the requests page rather than a hunt.

    Unlocking has no such condition: it is the escape hatch, and a condition on
    an escape hatch is how somebody ends up with a month they cannot correct.
    """
    from apps.absences.models import RequestStatus

    first = _month_from(request)
    last = month_end(first)
    days = [first + dt.timedelta(days=offset) for offset in range((last - first).days + 1)]
    unlocking = bool(request.POST.get("unlock"))

    chosen = Employee.objects.filter(
        pk__in=request.POST.getlist("employee"), is_active=True,
    )
    if not chosen:
        messages.info(request, _("Nobody was ticked, so nothing was changed."))
        return redirect(f"{reverse('timesheets:month-end')}?month={first:%Y-%m}")

    if unlocking:
        removed = DayLock.objects.filter(
            employee__in=chosen, date__gte=first, date__lte=last,
        ).delete()[0]
        messages.success(request, ngettext(
            "%(count)s day was unlocked.", "%(count)s days were unlocked.", removed,
        ) % {"count": removed})
        return redirect(f"{reverse('timesheets:month-end')}?month={first:%Y-%m}")

    blocked = [
        employee for employee in chosen
        if employee.absences.filter(
            status=RequestStatus.REQUESTED,
            start_date__lte=last, end_date__gte=first,
        ).exists()
    ]
    if blocked:
        messages.error(request, _(
            "%(names)s still have time off waiting for a decision in that month. "
            "Decide it first — approving it afterwards would change hours the month "
            "had already been signed off on."
        ) % {"names": ", ".join(person.full_name for person in blocked)})
        return redirect(f"{reverse('timesheets:month-end')}?month={first:%Y-%m}")

    locked = sum(
        DayLock.lock(employee, days, by=request.user) for employee in chosen
    )
    messages.success(request, ngettext(
        "%(count)s day was locked.", "%(count)s days were locked.", locked,
    ) % {"count": locked})
    return redirect(f"{reverse('timesheets:month-end')}?month={first:%Y-%m}")


@manager_required
@require_POST
def lock_day(request, pk, date):
    """One day, unlocked so it can be corrected — or locked again afterwards.

    The other half of "the default is to lock a whole month": a month is closed
    in one gesture and opened one day at a time, because the reason to open one
    is always a single day that was wrong.
    """
    employee = get_object_or_404(Employee, pk=pk)
    try:
        the_date = dt.date.fromisoformat(date)
    except ValueError as error:
        raise Http404 from error

    if request.POST.get("unlock"):
        DayLock.objects.filter(employee=employee, date=the_date).delete()
        messages.success(request, _("%(date)s was unlocked and can be changed again.") % {
            "date": the_date.strftime("%d.%m.%Y"),
        })
    else:
        DayLock.lock(employee, [the_date], by=request.user)
        messages.success(request, _("%(date)s was locked.") % {
            "date": the_date.strftime("%d.%m.%Y"),
        })
    return redirect(_month_url(request, employee, the_date))


def _hours_label(minutes, user):
    from apps.timesheets.hours import format_minutes, style_for

    return format_minutes(minutes, style_for(user))
