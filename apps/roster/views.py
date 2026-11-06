"""The week planner, and the areas it is drawn with.

The planner is a grid — the week's time slots down the side, Monday to Friday
across the top — and the people placed in its cells. ``apps/roster/forms.py``
says how the page is put together and ``apps/roster/models.py`` why a placement
*is* a shift.

Below the grid is everybody who could still be placed that day, and it is a
*reading* of the placements rather than a list of its own: the browser works it
out from the rows in the grid every time something moves, so it cannot say
somebody is free who has just been dragged in.

Who is away is part of that list, in red, rather than a band of its own. The
one mistake this page invites is rostering somebody who has an approved
holiday, which nobody notices until the morning they do not arrive.
"""

import datetime as dt

from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.absences.models import Absence, AbsenceKind, BankHoliday, RequestStatus
from apps.employees.models import Employee
from apps.employees.permissions import manager_required
from apps.roster.forms import AreaFormSet, WeekGrid, draft_from, employed_on
from apps.roster.models import (
    GRID_DAYS, Area, AreaIcon, PlannedWeek, Shift, TimeSlot,
)
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
    return f"{reverse('roster:plan')}?week={monday.isoformat()}"


def _absences(days):
    """``{(employee_id, date): absence}`` for the days shown.

    Everything not declined or withdrawn — a pending request is exactly the
    thing a manager wants to see *while* rostering, because deciding it and
    planning around it are the same act. Drawn differently on the page, so the
    two are never confused.
    """
    found = {}
    rows = (
        Absence.objects
        .filter(start_date__lte=days[-1], end_date__gte=days[0])
        .exclude(status__in=(RequestStatus.REJECTED, RequestStatus.WITHDRAWN))
        .select_related("special_type")
    )
    for absence in rows:
        for day in days:
            if absence.start_date <= day <= absence.end_date:
                found.setdefault((absence.employee_id, day), absence)
    return found


def _is_pending(absence):
    """A request nobody has decided. Sickness is never that: it is stated, not
    asked for (``Absence.credits_hours`` says why), so a reported sick day is
    away from the moment it is reported."""
    return absence.status == RequestStatus.REQUESTED and absence.kind != AbsenceKind.SICK


def _absence_label(absence):
    if absence.kind == AbsenceKind.SPECIAL and absence.special_type:
        label = absence.special_type.name
    else:
        label = absence.get_kind_display()
    if absence.is_half_day:
        label = _("%(kind)s, half day") % {"kind": label}
    if _is_pending(absence):
        label = _("%(kind)s, asked for") % {"kind": label}
    return label


def _display_names(people):
    """What a name chip says: the first name, unless two people share it.

    A cell is narrow and is read across a room, so "Anna" rather than "Anna
    Berger" — but two Annas on one grid is a grid nobody can read, so those
    two get an initial each.
    """
    counts = {}
    for person in people:
        counts[person.first_name] = counts.get(person.first_name, 0) + 1
    names = {}
    for person in people:
        if counts[person.first_name] > 1 and person.last_name:
            names[person.pk] = f"{person.first_name} {person.last_name[0]}."
        else:
            names[person.pk] = person.first_name or person.full_name
    return names


def _people_data(days, grid):
    """Everybody the grid may show, and what each day is for them.

    Anybody employed on at least one of the days, plus anybody already placed
    in the week (who may have left since) so that every chip on the page has a
    name to show. Per day: ``on`` (the contract gives hours), ``off`` (it does
    not — shown lighter, still placeable), ``away`` (an absence, in red) or
    absent from the entry altogether when they are not employed that day.
    """
    placed = {
        form.instance.employee_id for form in grid.places.forms if form.instance.pk
    }
    people = [
        person for person in Employee.objects.order_by("first_name", "last_name")
        if person.pk in placed
        or (person.is_active and any(employed_on(person, day) for day in days))
    ]
    names = _display_names(people)
    away = _absences(days)
    data = []
    for person in people:
        states = {}
        for day in days:
            if not (person.is_active and employed_on(person, day)):
                continue
            absence = away.get((person.pk, day))
            if absence is not None:
                states[day.isoformat()] = {
                    "state": "away", "label": _absence_label(absence),
                    "pending": _is_pending(absence),
                }
            elif person.works_on(day):
                states[day.isoformat()] = {"state": "on"}
            else:
                states[day.isoformat()] = {"state": "off"}
        data.append({
            "id": person.pk, "name": names[person.pk], "full": person.full_name,
            "days": states,
        })
    return data


def _unavailable(days):
    """The test ``draft_from`` uses to leave a copied placement out.

    Not employed, away (decided or reported — not merely asked for, since a
    request may yet be declined), or a public holiday.
    """
    away = _absences(days)
    holidays = BankHoliday.dates_between(days[0], days[-1])

    def unavailable(employee, day):
        if day in holidays:
            return True
        if not (employee.is_active and employed_on(employee, day)):
            return True
        absence = away.get((employee.pk, day))
        return absence is not None and not _is_pending(absence)

    return unavailable


@manager_required
def plan(request):
    monday = _monday_from(request)
    days = [monday + dt.timedelta(days=offset) for offset in range(GRID_DAYS)]
    draft_source = None
    left_out = 0

    if request.method == "POST":
        grid = WeekGrid(monday, data=request.POST)
        if grid.is_valid():
            grid.save()
            messages.success(request, _("The roster was saved."))
            return redirect(_plan_url(monday))
        messages.error(request, _("The roster was not saved — see the entries marked below."))
    else:
        draft = None
        is_planned = (
            PlannedWeek.objects.filter(week=monday).exists()
            or TimeSlot.objects.filter(week=monday).exists()
        )
        if not is_planned and not request.GET.get("empty"):
            draft_source = TimeSlot.last_planned_before(monday)
            if draft_source:
                draft, left_out = draft_from(draft_source, monday, _unavailable(days))
        grid = WeekGrid(monday, draft=draft)

    holidays = {
        row.date: row.name
        for row in BankHoliday.objects.filter(date__gte=days[0], date__lte=days[-1])
    }
    # Shifts the grid cannot draw: on a weekend, or written before the grid
    # existed and never given a slot. They are still shifts and the timesheet
    # still reads them, so the page says they are there.
    outside = Shift.objects.filter(
        date__gte=monday, date__lte=monday + dt.timedelta(days=6),
    ).exclude(slot__week=monday, date__in=days).select_related("employee")

    areas = list(Area.objects.all())
    page_data = {
        "days": [day.isoformat() for day in days],
        "holidays": [day.isoformat() for day in holidays],
        "people": _people_data(days, grid),
        "areas": {
            str(area.pk): {"name": area.name, "icon": area.icon, "active": area.is_active}
            for area in areas
        },
        "sprite": static("icons/areas.svg"),
        "placementErrors": grid.placement_errors,
    }

    return render(request, "roster/plan.html", {
        "grid": grid,
        "monday": monday,
        "days": [
            {"date": day, "holiday": holidays.get(day), "is_today": day == dt.date.today()}
            for day in days
        ],
        "last_day": days[-1],
        "areas": areas,
        "outside": list(outside),
        "draft_source": draft_source,
        "left_out": left_out,
        "page_data": page_data,
        "previous_week": monday - dt.timedelta(days=7),
        "next_week": monday + dt.timedelta(days=7),
        "this_week": week_monday(dt.date.today()),
    })


@manager_required
def areas(request):
    """Name the areas the grid can be split into, and give each an icon.

    Deleting one that any week has used is refused and the message names the
    reversible operation instead — the same rule as for employees and leave
    types: the destructive version exists for the row created by a typo ten
    seconds ago and nothing else.
    """
    queryset = Area.objects.all()
    if request.method == "POST":
        formset = AreaFormSet(request.POST, queryset=queryset, prefix="area")
        if formset.is_valid():
            refused = []
            instances = formset.save(commit=False)
            for area in formset.deleted_objects:
                try:
                    if area.is_used:
                        raise ProtectedError("used", [area])
                    area.delete()
                except ProtectedError:
                    refused.append(area.name)
            for index, area in enumerate(instances):
                if area.position == 0 and not area.pk:
                    area.position = Area.objects.count() + index + 1
                area.save()
            if refused:
                messages.warning(request, _(
                    "%(names)s has been used in the roster and was kept. Untick “in use” "
                    "instead: that stops it being offered and keeps every week it was used in."
                ) % {"names": ", ".join(refused)})
            else:
                messages.success(request, _("The areas were saved."))
            return redirect(reverse("roster:areas") + (
                f"?week={request.POST['week']}" if request.POST.get("week") else ""
            ))
    else:
        formset = AreaFormSet(queryset=queryset, prefix="area")

    return render(request, "roster/areas.html", {
        "formset": formset,
        "icons": AreaIcon.choices,
        "sprite": static("icons/areas.svg"),
        "week": request.GET.get("week", ""),
    })
