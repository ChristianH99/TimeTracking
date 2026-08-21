"""The timesheet: what you were rostered, what you say you worked, and the week.

Three pages and one shared rendering. ``mine`` and ``employee`` are the *same*
week view asked about two different people — deliberately one function, because
a manager and an employee looking at the same week and seeing different figures
is the single most damaging bug this app could have, and two implementations is
how it happens.
"""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.absences.models import Absence, BankHoliday, Balance, RequestStatus
from apps.employees.models import Employee
from apps.employees.permissions import manager_required, own_or_manager
from apps.organisation.models import OrgSettings
from apps.roster.models import Shift
from apps.timesheets import clocking
from apps.timesheets.balance import hours_balance
from apps.timesheets.forms import DayForm, SegmentFormSet
from apps.timesheets.hours import contracted_minutes
from apps.timesheets.models import DayRecord, EntrySource, week_monday
from apps.timesheets.zones import local_today, zone_for


def _monday_from(request):
    raw = request.GET.get("week") or request.POST.get("week")
    try:
        day = dt.date.fromisoformat(raw)
    except (TypeError, ValueError):
        day = dt.date.today()
    return week_monday(day)


# --------------------------------------------------------------------------
# The week
# --------------------------------------------------------------------------

def build_week(employee, monday, settings=None):
    """Everything one person's week is: seven rows, and the totals under them.

    One function, called by the employee's own page and by the manager's view of
    somebody else, so the two cannot drift. Each row carries the four facts a
    day has:

    * what was **rostered** (the plan, from ``apps.roster``),
    * what was **entered** (the record, or ``None`` for a day nobody has
      answered for — which is not the same as a day of zero hours),
    * whether the two **agree**, which is the line a manager reads first,
    * and what else was true of the date: a public holiday, an absence, or a
      day the contract gives no hours.

    Four queries for the week regardless of how many days have rows.
    """
    settings = settings or OrgSettings.current()
    rules = list(settings.break_rules.all()) if settings.is_stored else None
    days = [monday + dt.timedelta(days=offset) for offset in range(7)]

    shifts = {}
    for shift in Shift.objects.filter(employee=employee, date__gte=days[0], date__lte=days[-1]):
        shifts.setdefault(shift.date, []).append(shift)

    records = {
        record.date: record
        for record in DayRecord.objects
        .filter(employee=employee, date__gte=days[0], date__lte=days[-1])
        .prefetch_related("segments")
    }

    holidays = {
        row.date: row.name
        for row in BankHoliday.objects.filter(date__gte=days[0], date__lte=days[-1])
    }

    absences = list(
        employee.absences
        .filter(start_date__lte=days[-1], end_date__gte=days[0])
        .exclude(status__in=(RequestStatus.REJECTED, RequestStatus.WITHDRAWN))
        .select_related("special_type", "closure")
    )

    rows = []
    for day in days:
        record = records.get(day)
        planned = shifts.get(day, [])
        absence = next(
            (a for a in absences if a.start_date <= day <= a.end_date), None,
        )
        # `on=day`, not today. Somebody who dropped their Wednesdays in April
        # still worked them in February, and a week reprinted afterwards has to
        # say so — that is the whole reason the contract is a history.
        contracted = contracted_minutes(employee.hours_on_weekday(day.weekday(), on=day))
        is_working_day = employee.works_on(day)
        due = contracted if is_working_day else 0
        worked = record.worked_minutes if record else None

        # What an absence hands back. A sick day is paid as though it had been
        # worked (§3 EFZG) and so is a day of leave (§11 BUrlG), so both credit
        # the contracted hours and the week comes out level instead of showing a
        # shortfall the employee does not owe. Time off in lieu credits nothing,
        # deliberately — the shortfall *is* the overtime being spent. A public
        # holiday credits too, for the same reason as leave.
        credited = 0
        if absence is not None and day not in holidays:
            credited = absence.credited_minutes(day, due)
        elif day in holidays and is_working_day:
            credited = due

        rows.append({
            "date": day,
            "record": record,
            "shifts": planned,
            "planned_minutes": sum(shift.minutes for shift in planned),
            "worked_minutes": worked,
            "contracted_minutes": due,
            # Hours the day is worth without anybody having worked them, and
            # what the row names as the reason. Kept beside the worked figure
            # rather than folded into it, because "you were ill" and "you worked
            # eight hours" are different sentences and a timesheet that could not
            # tell them apart would be no use in the argument it exists for.
            "credited_minutes": credited,
            "counted_minutes": (worked or 0) + credited,
            # Only meaningful when both exist *and the day is finished*. A day
            # with a record and no roster is not "different from what was asked"
            # — nothing was asked. And a day still running is not different
            # either; it is not yet anything, and flagging it would put an
            # attention pill on every shift the moment somebody pressed Start.
            "differs_from_roster": bool(
                record and planned and not record.is_running
                and not record.matches_roster(planned)
            ),
            "break_is_override": bool(record and record.break_is_override),
            # A stretch started and not stopped. The row draws it as running
            # rather than as a day of nought hours, which is what the totals
            # would otherwise make it look like.
            "is_running": bool(record and record.is_running),
            "running_since": record.running_segment.start if record and record.is_running else None,
            "required_break": (
                settings.required_break(record.gross_minutes, rules=rules)
                if record else None
            ),
            "holiday": holidays.get(day),
            "absence": absence,
            "is_half_day": bool(absence and absence.is_half_day),
            "is_working_day": is_working_day,
            "is_today": day == dt.date.today(),
            # A day worth asking somebody to answer: they were rostered, it is
            # not in the future, and there is no record and no absence.
            "awaiting": bool(
                planned and not record and absence is None and day <= dt.date.today()
            ),
        })

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
        # last night is still running this morning and is not on this week at
        # all once the week rolls over.
        "clock": clocking.state_for(employee),
        # Everything owed, up to the end of the week being looked at. This is
        # where an opening balance carried in from a previous contract becomes
        # visible — without it the figure would be stored and never shown, which
        # is a figure nobody can check.
        "running": hours_balance(employee, until=days[-1], settings=settings),
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


@login_required
def mine(request):
    employee = Employee.for_user(request.user)
    if employee is None:
        return render(request, "absences/no_contract.html")
    context = build_week(employee, _monday_from(request))
    context["is_own"] = True
    return render(request, "timesheets/week.html", context)


@manager_required
def employee_week(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    context = build_week(employee, _monday_from(request))
    context["is_own"] = employee.user_id == request.user.id
    return render(request, "timesheets/week.html", context)


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

    try:
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
        return redirect(_week_url(request, employee, local_today(zone_for(employee))))

    return redirect(_week_url(request, employee, segment.day.date))

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

    if request.method == "POST":
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
            return redirect(_week_url(request, employee, the_date))
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


def _week_url(request, employee, date):
    """Back to whichever week page the day was reached from.

    Decided by whose day it is rather than by a ``?next=``, so a manager editing
    somebody's Tuesday lands back on that person's week and an employee lands on
    their own. Sending everybody to ``mine`` would drop a manager onto a page
    that does not contain the change they just made.
    """
    week = week_monday(date).isoformat()
    if employee.user_id is not None and employee.user_id == request.user.id:
        return f"{reverse('timesheets:mine')}?week={week}"
    return f"{reverse('timesheets:employee', args=[employee.pk])}?week={week}"


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

    settings = OrgSettings.current()
    rules = list(settings.break_rules.all()) if settings.is_stored else None
    shifts = list(Shift.objects.filter(employee=employee, date=the_date))

    if not shifts:
        messages.error(request, _(
            "There is nothing rostered on that day, so there is nothing to confirm. "
            "Enter the hours instead."
        ))
        return redirect(_week_url(request, employee, the_date))

    record = DayRecord.from_shifts(
        employee, the_date, shifts, by=request.user, settings=settings, rules=rules,
    )
    messages.success(request, _("%(date)s was confirmed: %(hours)s worked.") % {
        "date": the_date.strftime("%d.%m.%Y"),
        "hours": _hours_label(record.worked_minutes, request.user),
    })
    return redirect(_week_url(request, employee, the_date))


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

    confirmed = skipped = 0
    for day_date in days:
        if day_date > today or day_date not in shifts:
            continue
        if day_date in existing:
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
    return redirect(f"{reverse('timesheets:mine')}?week={monday.isoformat()}")


def _hours_label(minutes, user):
    from apps.timesheets.hours import format_minutes, style_for

    return format_minutes(minutes, style_for(user))
