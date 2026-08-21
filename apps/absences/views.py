"""Time off: what an employee asks for, and what a manager decides."""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.absences.forms import AbsenceRequestForm, DecisionForm, SickForm
from apps.absences.carryover import LeaveCarryOver, expire_due
from apps.absences.models import (
    Absence, AbsenceKind, Balance, RequestStatus,
)
from apps.employees.models import Employee
from apps.employees.permissions import manager_required
from apps.organisation.models import OrgSettings


@login_required
def mine(request):
    """My leave year: the balance, and everything I have booked or asked for.

    An employee with no contract gets a page that says so rather than a crash.
    That is a real state — an administrator with an account and no shifts — and
    the day somebody in that position clicks Time off out of curiosity is not a
    day the app should fall over.
    """
    employee = Employee.for_user(request.user)
    if employee is None:
        return render(request, "absences/no_contract.html")

    year = _year_from(request)
    balance = Balance(employee, year)
    first, last = dt.date(year, 1, 1), dt.date(year, 12, 31)

    return render(request, "absences/mine.html", {
        "employee": employee,
        "year": year,
        "years": range(year - 2, year + 2),
        "balance": balance,
        "today": dt.date.today(),
        "absences": employee.absences.filter(
            start_date__lte=last, end_date__gte=first,
        ).select_related("special_type", "closure"),
        "request_form": AbsenceRequestForm(employee=employee),
        "sick_form": SickForm(employee=employee, initial={"start_date": dt.date.today()}),
        "open_sickness": employee.absences.filter(
            kind=AbsenceKind.SICK, end_date__gte=dt.date.today(),
        ).exclude(status=RequestStatus.REJECTED).order_by("-start_date").first(),
    })


@login_required
@require_POST
def request_absence(request):
    """Ask for holiday or special leave.

    Always ``REQUESTED``, even when a manager submits it for themselves. A
    manager approving their own request is a separate press of a separate
    button, and it leaves a row saying who decided it — which is exactly the
    audit trail that a self-approving shortcut would erase.
    """
    employee = Employee.for_user(request.user)
    if employee is None:
        return render(request, "absences/no_contract.html")

    form = AbsenceRequestForm(request.POST, employee=employee)
    if not form.is_valid():
        year = _year_from(request)
        balance = Balance(employee, year)
        first, last = dt.date(year, 1, 1), dt.date(year, 12, 31)
        return render(request, "absences/mine.html", {
            "employee": employee, "year": year, "years": range(year - 2, year + 2),
            "balance": balance,
            "absences": employee.absences.filter(
                start_date__lte=last, end_date__gte=first,
            ).select_related("special_type", "closure"),
            "request_form": form,
            "sick_form": SickForm(employee=employee, initial={"start_date": dt.date.today()}),
            "open_sickness": None,
            # Reopens the panel the errors are in. A page that comes back with
            # the form folded away again reads as the request having vanished.
            "show_request_form": True,
        })

    absence = form.save(commit=False)
    absence.employee = employee
    absence.status = RequestStatus.REQUESTED
    absence.save()
    messages.success(request, _(
        "Your request was sent for approval. It shows as waiting until your manager "
        "decides, and the days are not taken off your balance before then."
    ))
    return redirect("absences:mine")


@login_required
@require_POST
def request_cancel(request, pk):
    """Withdraw a request, or an approved absence that has not started.

    Withdrawn rather than deleted, so the record still says the conversation
    happened. Deleting would leave a manager who remembers approving something
    with no trace of it at all.
    """
    employee = Employee.for_user(request.user)
    absence = get_object_or_404(Absence, pk=pk, employee=employee)

    if absence.kind == AbsenceKind.CLOSURE:
        messages.error(request, _("That is not something you can withdraw."))
        return redirect("absences:mine")
    if absence.kind == AbsenceKind.SICK and absence.status != RequestStatus.REQUESTED:
        # A report a manager has already acknowledged is part of the record and
        # not the employee's to take back. One entered a minute ago against the
        # wrong dates is, and refusing that would leave a wrong absence on the
        # calendar with no way to say so.
        messages.error(request, _(
            "Your manager has already seen that. Ask them to correct the dates."
        ))
        return redirect("absences:mine")
    if absence.start_date <= dt.date.today() and absence.status == RequestStatus.APPROVED:
        messages.error(request, _(
            "That time off has already started. Ask your manager to change it."
        ))
        return redirect("absences:mine")

    absence.status = RequestStatus.WITHDRAWN
    absence.save(update_fields=["status"])
    messages.success(request, _("The request was withdrawn."))
    return redirect("absences:mine")


@login_required
@require_POST
def report_sick(request):
    """Say you are ill. Approved on arrival — see ``SickForm``."""
    employee = Employee.for_user(request.user)
    if employee is None:
        return render(request, "absences/no_contract.html")

    form = SickForm(request.POST, employee=employee)
    if form.is_valid():
        form.save()
        messages.success(request, _(
            "Recorded, and your manager has been shown it. It counts from now — it does "
            "not come out of your leave, the hours are credited, and the days you were "
            "not due to work are not counted."
        ))
    else:
        messages.error(request, _("Those dates could not be read."))
    return redirect("absences:mine")


@login_required
@require_POST
def end_sickness(request, pk):
    """Say when an open sickness ended.

    Separate from reporting it, because on the morning somebody rings in nobody
    knows the answer — and a form that demanded one would get today's date,
    every time, from everybody.
    """
    employee = Employee.for_user(request.user)
    absence = get_object_or_404(
        Absence, pk=pk, employee=employee, kind=AbsenceKind.SICK,
    )
    try:
        last_day = dt.date.fromisoformat(request.POST.get("end_date", ""))
    except ValueError:
        messages.error(request, _("That date could not be read."))
        return redirect("absences:mine")

    if last_day < absence.start_date:
        messages.error(request, _("That is before the illness started."))
        return redirect("absences:mine")

    absence.end_date = last_day
    absence.save(update_fields=["end_date"])
    messages.success(request, _("Thank you — the sickness is recorded as ended."))
    return redirect("absences:mine")


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
    waiting = (
        Absence.objects.filter(status=RequestStatus.REQUESTED)
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
        Absence.objects.exclude(status=RequestStatus.REQUESTED)
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
    absence.decide(approved, by=request.user, note=form.cleaned_data["note"])

    # Sickness reads differently on both sides of the button, because it was
    # never a request. Approving it is acknowledging a report; refusing it is
    # the employer positively declining to accept the absence, which is the one
    # act that stops the hours being credited — so the message says so rather
    # than calling it a declined request.
    if absence.kind == AbsenceKind.SICK:
        if approved:
            messages.success(request, _("%(who)s’s sickness was acknowledged.") % {
                "who": absence.employee.full_name,
            })
        else:
            messages.success(request, _(
                "%(who)s’s sickness was recorded as not accepted, and they were told why. "
                "Those days no longer count as time worked."
            ) % {"who": absence.employee.full_name})
    elif approved:
        messages.success(request, _("%(who)s’s time off was approved.") % {
            "who": absence.employee.full_name,
        })
    else:
        messages.success(request, _("%(who)s’s request was declined and they were told why.") % {
            "who": absence.employee.full_name,
        })
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

