"""The week planner.

Seven columns, one per day, with a card for each shift stacked inside the day it
falls on. Dragging a card to another column moves the shift; the card is the
form row and the drag rewrites its hidden ``date``, so there is never a second
copy of the week to keep in step (``apps/roster/forms.py`` says why that matters).

Absences are drawn in the columns too, and they are **not** shifts — they are
read-only bands showing who is already away. Without them the one mistake this
page invites is rostering somebody who has an approved holiday, which nobody
notices until the morning they do not arrive.
"""

import datetime as dt

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.absences.models import Absence, BankHoliday, RequestStatus
from apps.employees.models import Employee
from apps.employees.permissions import manager_required
from apps.organisation.models import OrgSettings
from apps.roster.forms import CopyWeekForm, ShiftFormSet, rosterable
from apps.roster.models import Shift
from apps.timesheets.hours import contracted_minutes
from apps.timesheets.models import week_monday


def _monday_from(request):
    """The week a page is showing, defaulting to this one.

    Anything unparseable falls back to the current week rather than raising:
    this arrives in a query string, and a 500 on ``?week=banana`` is a page
    somebody can break from the address bar. Normalised to a Monday, so a link
    that names any day of a week lands on that week.
    """
    raw = request.GET.get("week") or request.POST.get("week")
    try:
        day = dt.date.fromisoformat(raw)
    except (TypeError, ValueError):
        day = dt.date.today()
    return week_monday(day)


def _plan_url(monday):
    """The planner, showing that week.

    Built with ``reverse`` rather than by slicing ``request.path``. The slicing
    version worked and was one route rename away from redirecting to a 404 —
    and the routes it sliced are at three different depths, so each of the three
    had its own magic number.
    """
    return f"{reverse('roster:plan')}?week={monday.isoformat()}"


@manager_required
def plan(request):
    monday = _monday_from(request)
    days = [monday + dt.timedelta(days=offset) for offset in range(7)]
    people = rosterable()

    if request.method == "POST":
        formset = ShiftFormSet(
            request.POST,
            queryset=Shift.objects.filter(date__gte=days[0], date__lte=days[-1]),
            week_dates=set(days), employees=people,
        )
        if formset.is_valid():
            formset.save()
            messages.success(request, _("The roster was saved."))
            return redirect(_plan_url(monday))
        messages.error(request, _("The roster was not saved — see the cards marked below."))
    else:
        formset = ShiftFormSet(
            queryset=Shift.objects.filter(date__gte=days[0], date__lte=days[-1])
            .select_related("employee"),
            week_dates=set(days), employees=people,
        )

    # The forms, arranged into the seven columns the page draws. A form belongs
    # to the day its *bound* date says, not the day its instance was saved on —
    # otherwise a card that failed validation after being dragged springs back
    # to where it came from while the error message talks about the new day.
    columns = {day: [] for day in days}
    for form in formset.forms:
        day = _day_of(form, days)
        columns[day].append(form)

    holidays = {
        row.date: row.name
        for row in BankHoliday.objects.filter(date__gte=days[0], date__lte=days[-1])
    }
    away = _absences_by_day(days)

    return render(request, "roster/plan.html", {
        "formset": formset,
        "monday": monday,
        "days": days,
        "columns": [
            {
                "date": day,
                "forms": columns[day],
                "holiday": holidays.get(day),
                "away": away.get(day, []),
                "is_today": day == dt.date.today(),
            }
            for day in days
        ],
        "employees": people,
        "previous_week": monday - dt.timedelta(days=7),
        "next_week": monday + dt.timedelta(days=7),
        "this_week": week_monday(dt.date.today()),
        "copy_form": CopyWeekForm(initial={"source_monday": monday - dt.timedelta(days=7)}),
        "settings": OrgSettings.current(),
    })


def _day_of(form, days):
    """Which column a form belongs in.

    Bound data first (what the browser last said), then the saved instance, then
    the first day of the week as a last resort. The fallback is not decoration:
    a row whose date failed to parse has to render *somewhere*, or the card
    carrying the error message disappears from the page that is supposed to be
    showing it.
    """
    if form.is_bound:
        raw = form.data.get(form.add_prefix("date"))
        try:
            day = dt.date.fromisoformat(raw)
        except (TypeError, ValueError):
            day = None
        if day in days:
            return day
    if form.instance and form.instance.date in days:
        return form.instance.date
    return days[0]


def _absences_by_day(days):
    """``{date: [(employee, absence), …]}`` for the week.

    Approved and pending both, drawn differently on the page: a pending request
    is exactly the thing a manager wants to see *while* rostering, because
    deciding it and planning around it are the same act. One query for the week
    rather than one per day.
    """
    rows = (
        Absence.objects
        .filter(start_date__lte=days[-1], end_date__gte=days[0])
        # Booked and merely asked for alike — deciding it and planning round it
        # are the same act. A cancellation somebody has asked for is *booked*,
        # so it is in `IN_FORCE` and shows here as the absence it still is.
        .exclude(status__in=(
            RequestStatus.REJECTED, RequestStatus.WITHDRAWN,
        ))
        .select_related("employee", "special_type")
    )
    by_day = {}
    for absence in rows:
        for day in days:
            if absence.start_date <= day <= absence.end_date and absence.employee.works_on(day):
                by_day.setdefault(day, []).append(absence)
    return by_day


@manager_required
@require_POST
def copy_week(request):
    """Copy another week's shifts onto this one.

    Adds rather than replaces, and the button says so. See
    ``Shift.copy_week`` for why: replacing is the tidier implementation and
    would silently discard a week somebody had already adjusted.
    """
    monday = _monday_from(request)
    form = CopyWeekForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("That is not a date this app can read."))
        return redirect(_plan_url(monday))

    source = form.cleaned_data["source_monday"]
    if source == monday:
        messages.error(request, _("That is this week — copying it onto itself would double every shift."))
        return redirect(_plan_url(monday))

    copied = Shift.copy_week(source, monday)
    if copied:
        messages.success(request, _(
            "%(count)s shifts were copied from the week of %(from)s. They were added "
            "to what was already here, so anything that is now doubled can be dragged off."
        ) % {"count": copied, "from": source.strftime("%d.%m.%Y")})
    else:
        messages.info(request, _("That week has no shifts to copy."))
    return redirect(_plan_url(monday))


@manager_required
@require_POST
def fill_from_pattern(request):
    """Draft a week from everybody's contracted hours.

    The first thing a manager does on an empty roster, and the largest single
    cost this app can take off them. It is explicitly a **draft**: a contract
    says how long somebody works and never when, so the start time comes from
    the one setting that holds it and every card is then dragged into place.

    The end is start + contracted hours **+ the break that length of day
    requires**, because the contract's hours are working time and a shift is
    clock-in to clock-out. Without that, everybody rostered for a 7.5-hour
    contract would be down 45 minutes a day the moment they took the break they
    are legally required to take — which is the sort of arithmetic error that
    turns up in a payroll audit rather than on the page.

    Skips days somebody is already rostered on, so pressing it twice does not
    double the week.
    """
    monday = _monday_from(request)
    days = [monday + dt.timedelta(days=offset) for offset in range(7)]
    settings = OrgSettings.current()
    rules = list(settings.break_rules.all()) if settings.is_stored else None

    already = set(
        Shift.objects.filter(date__gte=days[0], date__lte=days[-1])
        .values_list("employee_id", "date")
    )
    holidays = BankHoliday.dates_between(days[0], days[-1])

    created = []
    for employee in Employee.objects.filter(is_active=True):
        for day in days:
            if (employee.id, day) in already or day in holidays:
                continue
            if not employee.works_on(day):
                continue
            working = contracted_minutes(
                employee.hours_on_weekday(day.weekday(), on=day)
            )
            span = working + settings.required_break(working, rules=rules)
            start = settings.day_start
            end_minutes = (start.hour * 60 + start.minute + span) % (24 * 60)
            created.append(Shift(
                employee=employee, date=day, start=start,
                end=dt.time(end_minutes // 60, end_minutes % 60),
            ))
    Shift.objects.bulk_create(created)

    if created:
        messages.success(request, _(
            "%(count)s shifts were drafted from the contracts, starting at %(start)s. "
            "Days that already had somebody on them were left alone — drag the cards "
            "to where they belong."
        ) % {"count": len(created), "start": settings.day_start.strftime("%H:%M")})
    else:
        messages.info(request, _(
            "Nothing to draft: everybody who works this week is already rostered."
        ))
    return redirect(_plan_url(monday))


@manager_required
@require_POST
def shift_delete(request, pk):
    """Remove one shift outright.

    Beside the formset's own DELETE box rather than instead of it: the box is
    how several are removed in one save, and this is the single-card gesture
    from the card's own menu. Both exist because the formset's version needs a
    save afterwards and somebody deleting one card does not expect to have to.
    """
    shift = get_object_or_404(Shift, pk=pk)
    week = week_monday(shift.date)
    shift.delete()
    messages.success(request, _("The shift was removed."))
    return redirect(_plan_url(week))
