"""Time off: what an employee asks for, and what a manager decides.

The employee's side is **a year on one page**. Twelve month blocks, a week to a
line, every day a cell — and the cell is the control: clicking a Tuesday is how
time off is asked for, which is the same argument the timesheet's status cell
makes. A form with two date boxes cannot answer the question somebody actually
has when they open this page, which is never "what is 14 March" but always
"what does this fortnight look like, and what have I already got booked". A
calendar answers it by being one.

Three things are asked for and only two of them come off the calendar:

* **off days** — holiday, or hours being taken back — and **sick days** are
  both a run of dates, so both are drawn on the grid and both are booked from
  it;
* **extra off days** (Sonderurlaub — a funeral, a move, a wedding) are a button
  instead. They are not chosen by looking at a year: the date is whatever the
  reason forces, and the question that has to be answered first is *which
  entitlement it comes out of*, which is a list and not a day.
"""

import calendar as calendars
import datetime as dt
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import prefetch_related_objects
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dates import MONTHS, WEEKDAYS_ABBR
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.absences.forms import AbsenceRequestForm, DecisionForm, SickForm
from apps.absences.carryover import LeaveCarryOver, expire_due
from apps.absences.models import (
    Absence, AbsenceKind, Balance, BankHoliday, IN_FORCE, RequestStatus,
    UNDECIDED, year_bounds,
)
from apps.employees.models import Employee
from apps.employees.permissions import manager_required
from apps.organisation.models import OrgSettings


@login_required
def mine(request):
    """My leave year: the three figures, the calendar, and the record behind it.

    An employee with no contract gets a page that says so rather than a crash.
    That is a real state — an administrator with an account and no shifts — and
    the day somebody in that position clicks Time off out of curiosity is not a
    day the app should fall over.
    """
    employee = Employee.for_user(request.user)
    if employee is None:
        return render(request, "absences/no_contract.html")

    year = _year_from(request)
    first, last = year_bounds(year)

    # **The contract history, once.** The calendar asks `works_on` for every
    # date of the year and `Balance` asks it again for every date of every
    # absence; without the prefetch that is a query per day, and the page runs
    # something like four hundred of them to answer one number.
    prefetch_related_objects([employee], "contract_periods")

    balance = Balance(employee, year)
    absences = list(
        employee.absences
        .filter(start_date__lte=last, end_date__gte=first)
        .select_related("special_type", "closure")
    )
    special = balance.special()

    return render(request, "absences/mine.html", {
        "employee": employee,
        "year": year,
        "previous_year": year - 1,
        "next_year": year + 1,
        "this_year": dt.date.today().year,
        "today": dt.date.today(),
        "balance": balance,
        "absences": absences,
        "special": special,
        # The middle figure of the three at the top. A total across the granted
        # types rather than one stat per type: a house with three of them would
        # otherwise push the figure people came for off the end of the row.
        "special_entitled": sum((row[1] for row in special), Decimal("0")),
        "special_left": sum((row[3] for row in special), Decimal("0")),
        # Django's own, so the day names are translated by Django and never
        # reach this app's catalogue.
        "weekday_labels": [WEEKDAYS_ABBR[index] for index in range(7)],
        "months": _year_calendar(employee, year, absences),
        # No grant, no button. Offering "ask for extra off days" to somebody who
        # has been granted none is offering a form whose only possible outcome
        # is a refusal — the type list would be empty and the form requires one.
        "can_ask_special": bool(special),
    })


# --------------------------------------------------------------------------
# The year as a grid
# --------------------------------------------------------------------------

def _year_calendar(employee, year, absences):
    """Twelve months of cells, each carrying everything its day has to say.

    Built here and not in the template, for the same reason `_day_row` is: a
    cell has to know six things at once — whether it is a working day, whether
    it is a public holiday, whether it is locked, what is booked on it, whether
    that is settled, and whether it is half — and template logic that asks
    those in six nested `{% if %}`s is logic no test can reach.

    ``monthdatescalendar`` hands back whole weeks, so every month starts on a
    Monday and the days belonging to the neighbouring month come with it. Those
    are dropped rather than drawn: a date that appears in two blocks is a date
    somebody can click twice and see two different things about.
    """
    from apps.timesheets.models import DayLock

    first, last = year_bounds(year)
    holidays = dict(
        BankHoliday.objects
        .filter(date__gte=first, date__lte=last)
        .values_list("date", "name")
    )
    locked = DayLock.dates_between(employee, first, last)
    booked = _by_date(absences)
    today = dt.date.today()
    weeks_of = calendars.Calendar(firstweekday=0).monthdatescalendar

    return [
        {
            "number": month,
            "name": MONTHS[month],
            "weeks": [
                _join_runs([
                    _day_cell(employee, day, holidays, locked, booked, today)
                    if day.month == month else None
                    for day in week
                ])
                for week in weeks_of(year, month)
            ],
        }
        for month in range(1, 13)
    ]


def _join_runs(week):
    """Mark which squares of a week are the middle of one booking.

    **Days booked together are drawn together.** A week off is one row in the
    database, one thing to withdraw and one thing somebody decided — and seven
    separate tiles say the opposite: that they are seven bookings which happen
    to be adjacent. So the days of one absence are joined into a bar, and the
    only rounded corners are the two at its ends.

    The comparison is on identity, not on dates: the run is "the same
    ``Absence`` row", which is exactly the thing that can be taken back as a
    unit. Two consecutive absences of the same kind stay two bars, because they
    are two decisions.

    A run breaks at the end of a week row and at any day that costs nothing —
    a weekend inside a fortnight is drawn pale, so the bar stops on the Friday
    and starts again on the Monday. That is not a gap in the booking, it is the
    booking not having been charged for those days, which is the same thing the
    balance says.
    """
    for index, cell in enumerate(week):
        if cell is None or cell["absence"] is None:
            continue
        before = week[index - 1] if index else None
        after = week[index + 1] if index + 1 < len(week) else None
        cell["joins_left"] = bool(before and before["absence"] is cell["absence"])
        cell["joins_right"] = bool(after and after["absence"] is cell["absence"])
    return week


def _by_date(absences):
    """``date -> the absence standing on it``, for everything still standing.

    Declined and withdrawn rows are history rather than a claim on the
    calendar, so they are not drawn at all — the table below the grid is where
    the record of them lives.

    An in-force row beats one still waiting where both cover a date. That can
    only happen through a closure, which is declared across everybody without
    asking whether they had already requested something; the request form
    refuses an overlap in every other direction.
    """
    standing = {}
    for absence in absences:
        if absence.status in (RequestStatus.REJECTED, RequestStatus.WITHDRAWN):
            continue
        for day in absence.dates():
            current = standing.get(day)
            if current is None or (
                absence.status in IN_FORCE and current.status not in IN_FORCE
            ):
                standing[day] = absence
    return standing


def _day_cell(employee, day, holidays, locked, booked, today):
    """One square of the grid.

    **A day that costs nothing is drawn as costing nothing, whatever covers
    it.** A weekend, a public holiday and a date the contract gives no hours
    are the three subtractions ``Absence.working_days`` makes, and they are the
    whole reason a week off is four days for one person and five for another —
    so a fortnight booked over Christmas comes out as blocks of colour with the
    holidays and the Sundays pale between them, which is exactly what was
    spent. Painting the whole stretch one colour would be the page claiming
    days the balance never took.

    ``can_book`` is the rest of it: on top of those three, a day somebody has
    locked, and a workplace closure, which is the employer's to declare and not
    one person's to take back. Inviting somebody to press a control that
    refuses is worse than a square that quietly says nothing, which is the same
    rule `:not(:disabled)` enforces on the timesheet's fillable cells.
    """
    holiday = holidays.get(day)
    works = employee.works_on(day)
    is_locked = day in locked
    counts = works and holiday is None
    absence = booked.get(day) if counts else None

    cell = {
        "date": day,
        "day": day.day,
        "is_weekend": day.weekday() >= 5,
        "is_today": day == today,
        "is_working": works,
        "is_locked": is_locked,
        "holiday": holiday,
        "absence": absence,
        "kind": absence.kind if absence else "",
        "is_pending": bool(absence and absence.status in UNDECIDED),
        "is_half": bool(absence and absence.is_half_day),
        # Whether this square is the middle of a booking rather than the whole
        # of one. `_join_runs` fills these in once the week around it exists.
        "joins_left": False,
        "joins_right": False,
        # More than one date, so what the pop-up offers to take back is the
        # whole of it and the heading has to say so.
        "is_group": bool(absence and absence.start_date != absence.end_date),
        "what": "",
        "when": "",
        "state": "",
        # What the button in the pop-up would do, decided here because it is
        # the same line `request_cancel` draws: nothing a manager has not
        # answered is theirs yet, so it is withdrawn outright, and something
        # approved is a day the roster was built around, so it is *asked* for.
        "action": "",
    }

    if absence is not None:
        cell["what"] = (
            absence.special_type.name
            if absence.kind == AbsenceKind.SPECIAL and absence.special_type
            else absence.get_kind_display()
        )
        cell["when"] = (
            absence.start_date.strftime("%d.%m.%Y")
            if absence.start_date == absence.end_date
            else f"{absence.start_date:%d.%m.%Y} – {absence.end_date:%d.%m.%Y}"
        )
        cell["state"] = absence.get_status_display()
        if absence.closure_id is None:
            if absence.status == RequestStatus.REQUESTED:
                cell["action"] = "withdraw"
            elif absence.status == RequestStatus.APPROVED:
                cell["action"] = "ask"

    cell["can_book"] = counts and not is_locked and (
        absence is None or absence.closure_id is None
    )

    # **What the pop-up calls the thing it is about**, and the two answers are
    # different questions. An empty square is a *date* somebody is about to
    # book, so it is named as one, weekday and all. A square that is part of a
    # booking of several days is not a date at all — it is a handle on the
    # whole booking, which is the only unit that can be taken back — so it is
    # named by its span. A heading reading "Freitag, 16. Oktober" over a dialog
    # whose only button withdraws five days is a heading that misnames what the
    # button does.
    cell["label"] = cell["when"] if cell["is_group"] else date_format(
        day, "l, j. F Y",
    )

    # The tooltip, and the only thing a square that is not a button can say for
    # itself. Punctuation is the only glue: a sentence assembled out of three
    # translated fragments is a sentence no translator can see the shape of.
    if absence is not None:
        cell["title"] = f"{cell['what']} · {cell['when']} · {cell['state']}"
    elif holiday:
        cell["title"] = holiday
    elif is_locked:
        cell["title"] = _("This day has been locked and nothing can be booked on it.")
    elif not works:
        cell["title"] = _("You are not due to work on this day.")
    else:
        cell["title"] = ""
    return cell


# --------------------------------------------------------------------------
# Asking
# --------------------------------------------------------------------------

@login_required
@require_POST
def book(request):
    """One door for everything an employee asks for — a day off, or an illness.

    **The forms are still two and the door is one.** Which of them answers is
    decided from ``kind`` here, exactly as ``timesheets.views.set_status``
    decides it: every rule about who may ask for what, which special types are
    theirs, whether those dates are working days at all and whether something
    already covers them lives in ``AbsenceRequestForm`` and ``SickForm``. A
    second implementation here would be a second answer to "may this person
    book this day", and the two would disagree the first time either changed.
    What this adds is nothing but the dispatch.

    It replaced two routes that differed only in which form they built, and
    that difference had become a liability rather than a safeguard: the
    calendar's pop-up offers holiday, time in lieu and sickness from one set of
    radio buttons, and a dialog that had to post to a different URL depending
    on which one was ticked is a dialog with two ways to be wrong.

    Always ``REQUESTED``, even for a manager asking for their own. Approving is
    a separate press that leaves a row saying who decided it, and a
    self-approving shortcut is exactly the audit trail this app keeps.

    A refusal comes back as a message and a reload rather than as a re-rendered
    form. The page behind the dialog is a whole year, and rebuilding the grid
    through a POST to say one sentence that fits in the message strip is a lot
    of machinery for a sentence.
    """
    employee = Employee.for_user(request.user)
    if employee is None:
        return render(request, "absences/no_contract.html")

    back = f"{reverse('absences:mine')}?year={_year_from(request)}"
    kind = request.POST.get("kind") or ""
    data = {
        "start_date": request.POST.get("start_date", ""),
        # **Not defaulted to the start.** A blank end is refused by both forms,
        # and it is refused on purpose: an absence with no end is what "off sick
        # from Tuesday, I will say when it stops" used to write, and it was the
        # one row nothing else in the app could count. The pop-up opens with
        # both dates filled in and both required, so a blank one arriving here
        # means something is wrong rather than something is unknown.
        "end_date": request.POST.get("end_date", ""),
        "is_half_day": request.POST.get("is_half_day", ""),
    }

    if kind == AbsenceKind.SICK:
        form = SickForm(data, employee=employee)
    else:
        data.update({
            "kind": kind,
            "special_type": request.POST.get("special_type", ""),
            # No note on a sick day, here as everywhere else: a sick absence
            # records that somebody was ill and never why, and a free-text box
            # beside it is where a diagnosis ends up.
            "reason": request.POST.get("reason", ""),
        })
        form = AbsenceRequestForm(data, employee=employee)

    if not form.is_valid():
        messages.error(request, _("That could not be saved: %(why)s") % {
            "why": " ".join(
                message for errors in form.errors.values() for message in errors
            ),
        })
        return redirect(back)

    absence = form.save(commit=False)
    absence.employee = employee
    absence.status = RequestStatus.REQUESTED
    absence.save()

    if absence.kind == AbsenceKind.SICK:
        messages.success(request, _(
            "Recorded, and your manager has been shown it. It shows as waiting until "
            "they decide — it does not come out of your leave either way, and the days "
            "you were not due to work are not counted."
        ))
    else:
        messages.success(request, _(
            "Your request was sent for approval. It shows as waiting until your manager "
            "decides, and the days are not taken off your balance before then."
        ))
    return redirect(back)


@login_required
@require_POST
def request_cancel(request, pk):
    """Take back what has not been decided; *ask* for what has.

    **The line is approval, and it is the same line for every kind.** Nothing a
    manager has not yet answered is theirs yet, so withdrawing it is the
    employee's to do and leaves nothing to explain. Something they have approved
    is a day the roster has been built around and the leave already spent
    against — taking that back unilaterally is a change to somebody else's plan,
    so it becomes a request in its own right and waits on the same list.

    Withdrawn rather than deleted, either way, so the record still says the
    conversation happened. Deleting would leave a manager who remembers
    approving something with no trace of it at all.
    """
    employee = Employee.for_user(request.user)
    absence = get_object_or_404(Absence, pk=pk, employee=employee)
    back = f"{reverse('absences:mine')}?year={_year_from(request)}"

    # Not the employee's, whatever its status: the employer declared it.
    if absence.kind == AbsenceKind.CLOSURE:
        messages.error(request, _("That is not something you can withdraw."))
        return redirect(back)

    if absence.status == RequestStatus.REQUESTED:
        absence.status = RequestStatus.WITHDRAWN
        absence.save(update_fields=["status"])
        messages.success(request, _("The request was withdrawn."))
        return redirect(back)

    if absence.status == RequestStatus.APPROVED:
        absence.status = RequestStatus.CANCELLING
        absence.save(update_fields=["status"])
        messages.success(request, _(
            "Your manager has been asked to cancel it. It stays booked until they "
            "answer — the days are still spent and the hours still credited."
        ))
        return redirect(back)

    if absence.status == RequestStatus.CANCELLING:
        messages.error(request, _("You have already asked for that to be cancelled."))
        return redirect(back)

    messages.error(request, _("That has already been decided."))
    return redirect(back)


# --------------------------------------------------------------------------
# The manager's side
# --------------------------------------------------------------------------

@manager_required
def requests(request):
    """Everything waiting to be decided, and what it would cost each person.

    The balance is shown *beside* each request rather than left to be looked up,
    because "can they afford this" is the question being answered and a decision
    made without it is a decision made blind. ``remaining_if_all_approved`` is
    the figure that matters: approving two of somebody's three pending requests
    is a thing that happens, and the days are only committed as each is decided.
    """
    # Everybody's pending time off is everybody's data, so opening the page is a
    # read of it. No single employee to name — see `apps/audit/access.py`.
    from apps.audit.access import record_view

    record_view(request, note="requests")
    waiting = (
        Absence.objects.filter(status__in=UNDECIDED)
        .select_related("employee", "special_type")
        .order_by("start_date")
    )
    year = dt.date.today().year
    balances = {}
    rows = []
    for absence in waiting:
        key = absence.employee_id
        if key not in balances:
            balances[key] = Balance(absence.employee, year)
        rows.append({
            "absence": absence,
            "days": absence.working_days(),
            "balance": balances[key],
            "form": DecisionForm(),
        })

    decided = (
        Absence.objects.exclude(status__in=UNDECIDED)
        .exclude(kind=AbsenceKind.CLOSURE)
        .select_related("employee", "special_type", "decided_by")
        .order_by("-decided_at", "-start_date")[:25]
    )
    return render(request, "absences/requests.html", {
        "rows": rows, "recent": decided, "year": year,
    })


@manager_required
@require_POST
def decide(request, pk):
    absence = get_object_or_404(Absence, pk=pk)
    if not absence.is_decidable:
        messages.error(request, _("That request has already been decided."))
        return redirect("absences:requests")

    form = DecisionForm(request.POST)
    if not form.is_valid():
        messages.error(request, form.errors.get("note", [_("That could not be saved.")])[0])
        return redirect("absences:requests")

    approved = form.cleaned_data["approve"]
    who = absence.employee.full_name

    # **Two questions reach this button and they are not the same one.** On a
    # request, yes means the absence happens; on a cancellation, yes means it
    # stops happening — and answering the second with `decide` would approve the
    # very absence somebody asked to have removed.
    if absence.is_cancelling:
        absence.decide_cancellation(
            approved, by=request.user, note=form.cleaned_data["note"],
        )
        if approved:
            messages.success(request, _("%(who)s’s absence was cancelled.") % {"who": who})
        else:
            messages.success(request, _(
                "%(who)s’s absence stays booked, and they were told why."
            ) % {"who": who})
        return redirect("absences:requests")

    absence.decide(approved, by=request.user, note=form.cleaned_data["note"])
    if approved:
        messages.success(request, _("%(who)s’s time off was approved.") % {"who": who})
    else:
        messages.success(request, _(
            "%(who)s’s request was declined and they were told why."
        ) % {"who": who})
    return redirect("absences:requests")


def _year_from(request):
    """The year a page or a form is about.

    **Reads the body as well as the query string**, which is not a nicety: the
    year-end page posts its year in a hidden field, and a version that only
    looked at ``request.GET`` fell back to *today's* year on every POST — so the
    button labelled "close 2025" closed 2026 and carried everybody's days into
    2027. Nothing raised; the page came back with a cheerful message naming the
    wrong year, which is the only reason it was noticed at all.

    ``apps/timesheets/views.py:_monday_from`` reads both for the same reason and
    has always done; this is that fix arriving here.
    """
    raw = request.POST.get("year") or request.GET.get("year")
    try:
        year = int(raw)
    except (TypeError, ValueError):
        return timezone.localdate().year
    return year if 1970 <= year <= 2200 else timezone.localdate().year


# --------------------------------------------------------------------------
# The end of a leave year
# --------------------------------------------------------------------------

@manager_required
def year_end(request):
    """What each person is carrying, when it lapses, and who was told.

    The page that makes the whole carry-over model usable, and it is a manager's
    page because every act on it is a decision: closing a year, extending one
    person's deadline, recording that the reminder went out. None of them can be
    inferred, which is exactly why ``apps/absences/carryover.py`` stores rather
    than derives.

    The column somebody will read first is the one saying the notice is missing.
    Under German case law statutory days do not lapse unless the employee was
    told what was left and that it was about to — so a deadline with no notice
    against it is a deadline that will not bite, and the days go on being owed.
    """
    year = _year_from(request)
    settings = OrgSettings.current()
    people = list(
        Employee.objects.filter(is_active=True).prefetch_related("contract_periods")
    )

    rows = []
    for employee in people:
        balance = Balance(employee, year, settings)
        carried = LeaveCarryOver.for_employee(employee, year)
        rows.append({
            "employee": employee,
            "balance": balance,
            "carried": carried,
            # What closing *this* year would leave behind, computed but not
            # written. Shown so a manager can see the consequence before
            # pressing the button rather than after.
            "would_carry": balance.remaining,
            "notice_missing": balance.notice_is_missing,
        })

    return render(request, "absences/year_end.html", {
        "year": year,
        "years": range(year - 3, year + 2),
        "rows": rows,
        "settings": settings,
        "statutory_deadline": settings.statutory_deadline(year),
        "employer_deadline": settings.employer_deadline(year),
        "today": dt.date.today(),
        "carried_total": sum(row["balance"].carried_days for row in rows),
        "lost_total": sum(row["balance"].carried_lost for row in rows),
    })


@manager_required
@require_POST
def close_year(request):
    """Write the carry-over rows for the year that has just ended.

    Idempotent: running it again recomputes from the same absences and rewrites
    the same rows, so a manager who presses it twice — or presses it in January
    and again in February after a late correction — gets the right answer rather
    than a doubled one.

    It does **not** expire anything. Closing records what was left on 31
    December; expiring happens on 31 March to whatever of it is still there, and
    the two are months apart for a reason.
    """
    year = _year_from(request)
    settings = OrgSettings.current()
    notice = _date_or_none(request.POST.get("notice_given_on"))

    written = 0
    for employee in Employee.objects.filter(is_active=True):
        if LeaveCarryOver.close_year(employee, year, settings, notice_given_on=notice):
            written += 1

    if written:
        messages.success(request, _(
            "%(count)s people are carrying days into %(next_year)s."
        ) % {"count": written, "next_year": year + 1})
        if notice is None:
            # Said every time, because it is the difference between a deadline
            # that means something and one that does not.
            messages.warning(request, _(
                "No reminder date was recorded, so the statutory days are treated as "
                "not expiring. Tell each person what they have left and that it will "
                "lapse, then record the date here."
            ))
    else:
        messages.info(request, _("Nobody has days left over from %(year)s.") % {"year": year})
    return redirect(f"{reverse('absences:year-end')}?year={year + 1}")


@manager_required
@require_POST
def expire_year(request):
    """Forfeit the carried days whose deadline has now passed.

    Refused before the deadline. Expiring early is not a shortcut a manager
    should have — the days are the employee's until the morning after, and there
    is no undo for taking them away.
    """
    year = _year_from(request)
    settings = OrgSettings.current()
    today = dt.date.today()
    deadline = settings.statutory_deadline(year)

    if today <= deadline:
        messages.error(request, _(
            "The deadline is %(date)s and it has not passed. Those days are still "
            "theirs to take."
        ) % {"date": deadline.strftime("%d.%m.%Y")})
        return redirect(f"{reverse('absences:year-end')}?year={year}")

    lost = expire_due(year, on=today, settings=settings)
    if lost:
        messages.success(request, _(
            "%(count)s people lost carried-over days, and each row records what went "
            "and when."
        ) % {"count": len(lost)})
    else:
        messages.info(request, _("There was nothing left to lapse."))
    return redirect(f"{reverse('absences:year-end')}?year={year}")


@manager_required
@require_POST
def extend_deadline(request, pk):
    """Move one person's deadline, for a reason that has to be written down.

    The special-circumstances door. It is per person because the circumstances
    are — long-term sickness, parental leave, a project that made the autumn
    impossible — and a blanket extension would be a change to the policy rather
    than an exception to it.
    """
    carried = get_object_or_404(LeaveCarryOver, pk=pk)
    statutory = _date_or_none(request.POST.get("statutory_deadline"))
    employer = _date_or_none(request.POST.get("employer_deadline"))
    reason = (request.POST.get("extension_reason") or "").strip()
    notice = _date_or_none(request.POST.get("notice_given_on"))

    if notice is not None:
        carried.notice_given_on = notice
        carried.save(update_fields=["notice_given_on", "updated_at"])

    if statutory is None and employer is None:
        if notice is not None:
            messages.success(request, _("The reminder date was recorded."))
        else:
            messages.error(request, _("No new date was given, so nothing was changed."))
        return redirect(f"{reverse('absences:year-end')}?year={carried.year}")

    try:
        carried.extend(request.user, statutory=statutory, employer=employer, reason=reason)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect(f"{reverse('absences:year-end')}?year={carried.year}")

    messages.success(request, _("%(who)s’s deadline was moved, and the reason recorded.") % {
        "who": carried.employee.full_name,
    })
    return redirect(f"{reverse('absences:year-end')}?year={carried.year}")


def _date_or_none(raw):
    """A posted ISO date, or ``None`` for blank *and* for unreadable.

    The two are folded together deliberately: every caller treats ``None`` as
    "not given" and says so, and a form that distinguished "empty" from
    "nonsense" here would be reporting a parse error about a field somebody
    left alone.
    """
    try:
        return dt.date.fromisoformat(raw or "")
    except (TypeError, ValueError):
        return None

