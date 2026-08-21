"""The people a manager looks after: their contract, and what it entitles them to."""

import datetime as dt

from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.absences.models import Balance
from apps.employees.forms import (
    ContractChangeForm, EmployeeForm, SpecialLeaveGrantFormSet, leave_preview,
)
from apps.employees.models import ContractPeriod, Employee, SpecialLeaveGrant
from apps.employees.permissions import manager_required
from apps.organisation.models import OrgSettings
from apps.timesheets.balance import hours_balance


@manager_required
def employee_list(request):
    """Everybody, with what their contract comes to.

    The three columns beside the name are the three questions a manager opens
    this page with: how much are they here, how many days a week is that, and
    how much leave does that buy. Computing them here rather than per row in the
    template keeps the settings lookup to one for the page instead of one per
    person — ``annual_leave_days`` takes it as an argument for exactly that.
    """
    settings = OrgSettings.current()
    this_year = dt.date.today().year
    people = list(
        Employee.objects.select_related("user")
        .prefetch_related(
            Prefetch("special_leave",
                     queryset=SpecialLeaveGrant.objects.select_related("leave_type")),
            # Prefetched, so `contract_on` walks a list instead of querying —
            # this page asks every employee for their current contract three
            # times over, which without it is three queries per person.
            "contract_periods",
        )
    )
    rows = [
        {
            "employee": person,
            "weekly_hours": person.weekly_hours,
            "working_days": person.working_days_per_week,
            "leave_days": person.annual_leave_days(settings),
            "leave_this_year": person.leave_days_in_year(this_year, settings),
            "is_override": person.leave_days_override is not None,
            "special": person.special_leave_days(settings),
            # More than one period means the hours have moved at least once. The
            # page marks it, because "why is her entitlement 22 when the
            # contract says 24" has exactly one answer and it is this.
            "contract_changes": len(person.contract_periods.all()) - 1,
            "running": hours_balance(person, settings=settings),
        }
        for person in people
    ]
    return render(request, "employees/employee_list.html", {
        "rows": rows,
        "settings": settings,
        "active_count": sum(1 for p in people if p.is_active),
        "unlinked_count": sum(1 for p in people if p.is_active and p.user_id is None),
    })


@manager_required
def employee_form(request, pk=None):
    """Add or edit one contract, with the special leave grants underneath.

    The account link is offered as a select of the accounts that have no
    employee yet. It is a *manual* route beside the automatic one in
    ``Employee.link_by_username`` — and it is the page somebody lands on when the
    directory calls them something other than what is on the contract.
    """
    instance = get_object_or_404(Employee, pk=pk) if pk else Employee()
    settings = OrgSettings.current()

    if request.method == "POST":
        form = EmployeeForm(request.POST, instance=instance)
        formset = SpecialLeaveGrantFormSet(
            request.POST, instance=instance if instance.pk else Employee(),
        )
        if form.is_valid():
            # The account is chosen by a select that is not on the form, so it
            # is applied to the instance *before* the save rather than to the
            # saved row afterwards. That ordering matters now that the form's
            # own save writes the contract period as well: a `commit=False`
            # save returns before it gets that far, and the version that took
            # that route created employees with no contract at all — which
            # renders as a page of zeros rather than as an error.
            _apply_account_choice(request, form.instance)
            saved = form.save()
            formset.instance = saved
            if formset.is_valid():
                formset.save()
                messages.success(request, _("%(name)s was saved.") % {"name": saved.full_name})
                return redirect("employees:list")
    else:
        form = EmployeeForm(instance=instance)
        formset = SpecialLeaveGrantFormSet(instance=instance if instance.pk else Employee())

    return render(request, "employees/employee_form.html", {
        "form": form,
        "formset": formset,
        "employee": instance if instance.pk else None,
        "preview": leave_preview(instance, settings) if instance.pk else None,
        "contract_periods": (
            list(instance.contract_periods.all()) if instance.pk else []
        ),
        "settings": settings,
        "linkable": _linkable_accounts(instance),
        # The two numbers the browser needs to preview an entitlement while the
        # seven hour boxes are being typed. The *rule* crosses over, not an
        # answer — an answer would be stale the moment somebody edits a box,
        # which is the only time this panel is worth having.
        "leave_rules": {
            "full_time_days": settings.full_time_days_per_week,
            "full_time_leave": float(settings.full_time_leave_days),
            "rounding": settings.leave_rounding,
        },
    })


def _linkable_accounts(employee):
    """Accounts not already attached to somebody else.

    Includes this employee's own account so the select can show it as chosen.
    Excludes every other linked one, because attaching a second employee to one
    account is not a state any page in this app can render — whichever of the
    two ``user.employee`` returns would be the one that person sees, and the
    other's timesheet would be unreachable from their own login.
    """
    taken = set(
        Employee.objects.exclude(pk=employee.pk or 0)
        .exclude(user__isnull=True).values_list("user_id", flat=True)
    )
    return User.objects.filter(is_active=True).exclude(pk__in=taken).order_by(
        "first_name", "username",
    )


def _apply_account_choice(request, employee):
    """Read the account select. Absent or blank means "no account", which is
    an ordinary state and not a reason to refuse the save — most employees are
    created before they have ever signed in."""
    raw = request.POST.get("user")
    if raw is None:
        return
    if not raw:
        employee.user = None
        return
    candidate = _linkable_accounts(employee).filter(pk=raw).first()
    if candidate is None:
        # Silently ignoring would leave the page claiming a link that is not
        # there. It cannot be a form error, because the select is not on the
        # form — so it is a message, which is visible and does not lose the rest
        # of the edit.
        messages.error(request, _(
            "That account is already attached to somebody else, so it was not linked."
        ))
        return
    employee.user = candidate


@manager_required
def contract_change(request, pk):
    """Put somebody on different hours from a date.

    A page of its own rather than a control on the contract form, and that is
    the point: changing somebody's working week is a decision with a date on it,
    and the one question it turns on — *from when* — has no sensible default. A
    version that reused the contract form would answer it silently with "always,
    retrospectively", which rewrites every week already worked.

    Backdating is allowed, because paperwork is slow and the agreement was made
    in April even when it is typed in June. What it is not is quiet: the page
    says how many confirmed days the change reaches back over, both before it is
    saved and in the message afterwards.
    """
    employee = get_object_or_404(Employee, pk=pk)
    settings = OrgSettings.current()

    if request.method == "POST":
        form = ContractChangeForm(request.POST, employee=employee)
        if form.is_valid():
            reaches_back = form.rewrites_confirmed_days
            period = form.save()
            if reaches_back:
                messages.warning(request, _(
                    "%(name)s is on the new hours from %(date)s. %(days)s day(s) they "
                    "had already confirmed fall inside that, so the hours those days "
                    "are measured against have changed — the hours worked have not."
                ) % {
                    "name": employee.full_name,
                    "date": period.valid_from.strftime("%d.%m.%Y"),
                    "days": reaches_back,
                })
            else:
                messages.success(request, _(
                    "%(name)s is on the new hours from %(date)s. Everything before "
                    "that keeps the old ones."
                ) % {
                    "name": employee.full_name,
                    "date": period.valid_from.strftime("%d.%m.%Y"),
                })
            return redirect("employees:edit", pk=employee.pk)
    else:
        form = ContractChangeForm(
            employee=employee, initial={"valid_from": dt.date.today()},
        )

    return render(request, "employees/contract_change.html", {
        "employee": employee,
        "form": form,
        "settings": settings,
        "periods": list(employee.contract_periods.all()),
        "current": employee.current_contract,
        "year": dt.date.today().year,
        # The same two numbers the contract form sends, so the panel that
        # previews an entitlement while the boxes are being typed behaves
        # identically on both pages rather than being a second implementation.
        "leave_rules": {
            "full_time_days": settings.full_time_days_per_week,
            "full_time_leave": float(settings.full_time_leave_days),
            "rounding": settings.leave_rounding,
        },
    })


@manager_required
@require_POST
def contract_delete(request, pk, period_pk):
    """Remove a contract change that should not have been made.

    Refused for the *only* period somebody has, which is not a change at all but
    their contract — deleting it would leave an employee with no hours on any
    date, and every page would answer with zeros rather than with an error.
    """
    employee = get_object_or_404(Employee, pk=pk)
    period = get_object_or_404(ContractPeriod, pk=period_pk, employee=employee)
    if employee.contract_periods.count() <= 1:
        messages.error(request, _(
            "That is the only contract %(name)s has, not a change to one. Edit the "
            "hours instead — an employee with no contract has no working days at all."
        ) % {"name": employee.full_name})
        return redirect("employees:edit", pk=employee.pk)
    period.delete()
    messages.success(request, _(
        "The change from %(date)s was removed. The contract before it applies again."
    ) % {"date": period.valid_from.strftime("%d.%m.%Y")})
    return redirect("employees:edit", pk=employee.pk)


@manager_required
@require_POST
def employee_delete(request, pk):
    """Delete a contract, or refuse when there is a timesheet behind it.

    Refusing is the whole point. Somebody who has left still worked the hours,
    and payroll may need them for years — so the destructive version is not
    offered once there is anything to destroy. "Switched off" is the operation
    people actually want and it is reversible; this exists for the row created
    by a mistyped name ten seconds ago.
    """
    employee = get_object_or_404(Employee, pk=pk)
    if employee.days.exists() or employee.absences.exists() or employee.shifts.exists():
        messages.error(request, _(
            "%(name)s has hours, shifts or absences recorded and cannot be deleted — "
            "those are the record of work that was actually done. Switch them off "
            "instead: that takes them off the roster and keeps everything."
        ) % {"name": employee.full_name})
        return redirect("employees:edit", pk=pk)
    name = employee.full_name
    employee.delete()
    messages.success(request, _("%(name)s was deleted.") % {"name": name})
    return redirect("employees:list")


@manager_required
def employee_leave(request, pk):
    """One person's leave year: entitlement, what is spent, what is waiting.

    The manager's view of the same figures the employee sees on their own Time
    off page, rendered from the same ``Balance`` — deliberately one class, so
    the two cannot disagree. A balance that reads differently depending on who
    is looking at it is the single thing most likely to be reported as a bug and
    hardest to explain as anything else.
    """
    employee = get_object_or_404(Employee, pk=pk)
    year = _year_from(request)
    balance = Balance(employee, year)
    return render(request, "employees/employee_leave.html", {
        "employee": employee,
        "year": year,
        "years": range(year - 2, year + 2),
        "balance": balance,
        "running": hours_balance(employee),
        "periods": list(employee.contract_periods.all()),
        "absences": employee.absences.filter(
            start_date__lte=dt.date(year, 12, 31), end_date__gte=dt.date(year, 1, 1),
        ).select_related("special_type", "closure"),
    })


def _year_from(request):
    raw = request.GET.get("year")
    try:
        year = int(raw)
    except (TypeError, ValueError):
        return dt.date.today().year
    return year if 1970 <= year <= 2200 else dt.date.today().year
