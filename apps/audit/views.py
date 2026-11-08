"""Reading the trail back.

Three pages and one query builder, because "show me everything" and "show me
what happened to my timesheet" are the same list with a filter on it — and two
implementations is how a manager and an employee end up being shown different
histories of one Tuesday.

**Who may see what is three answers, not one.**

* ``log`` is **staff**: the whole table, sign-ins included. This is the software
  administrator's page and the one an IDW PS 880 auditor is shown.
* ``employee_log`` is **own-or-manager**: everything that ever touched one
  person's records. A manager opening it is itself a read, recorded by the same
  door that allowed it.
* ``mine`` is the same page pointed at yourself, under its own route so the
  sidebar marks "My time" rather than "Team" — the duplication
  ``apps/timesheets/urls.py`` explains, for the same reason.

**An employee can see their own.** That is a decision and not an oversight. It
is their data (Art. 15 DSGVO), and more to the point it is the half of this
feature that is worth anything to the person being recorded: an audit trail only
the employer can read is a trail that protects only the employer. Somebody who
opens their month and finds a figure they did not type can now see who typed it.

**No filter can widen what the door allowed.** The employee pages filter on the
employee *before* the request's own parameters are read, so a ``?employee=``
smuggled onto the URL changes nothing. The alternative — one view that reads the
employee from the query string and then checks — is the shape where somebody
adds a second parameter next year and forgets it is inside the perimeter.
"""

import datetime as dt

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from apps.accounts.permissions import staff_required
from apps.audit.models import AuditAction, AuditEntry
from apps.employees.models import Employee
from apps.employees.permissions import own_or_manager

# One page of the log. Large enough that a day's work is usually one page and
# small enough that the page renders — the trail is the one table in the app
# with no upper bound on its size.
PER_PAGE = 100


def _date(raw):
    try:
        return dt.date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _filtered(request, entries):
    """The query parameters every version of the page understands.

    Applied to whatever queryset it is handed, so the employee pages can narrow
    first and let these narrow further — and no parameter here can undo that.
    """
    action = request.GET.get("action") or ""
    if action in AuditAction.values:
        entries = entries.filter(action=action)

    since = _date(request.GET.get("from"))
    until = _date(request.GET.get("to"))
    if since:
        entries = entries.filter(at__date__gte=since)
    if until:
        entries = entries.filter(at__date__lte=until)

    return entries, {"action": action, "date_from": since, "date_to": until}


def _page(request, entries):
    paginator = Paginator(entries, PER_PAGE)
    return paginator.get_page(request.GET.get("page"))


def _querystring(request):
    """The current filters, ready to have ``page=`` appended.

    Carried onto the paging links because a pager that drops the filters shows
    page two of something else — and on this page, "something else" is somebody
    else's records, which is the one mistake it must not make.
    """
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return f"{encoded}&" if encoded else ""


@login_required
@staff_required
def log(request):
    """Everything, for whoever administers the software.

    ``select_related`` on both keys: the table draws the actor and the employee
    on every row, and without it a hundred rows is two hundred queries — which
    is the one page in this app where that is not a theoretical concern, because
    it is the page that grows forever.
    """
    entries = AuditEntry.objects.select_related("actor", "employee")

    who = request.GET.get("employee") or ""
    if who.isdigit():
        entries = entries.filter(employee_id=int(who))

    entries, applied = _filtered(request, entries)
    return render(request, "audit/log.html", {
        "page": _page(request, entries),
        "people": Employee.objects.order_by("last_name", "first_name"),
        "employee_filter": who,
        "actions": AuditAction.choices,
        "is_whole_log": True,
        "querystring": _querystring(request),
        **applied,
    })


def _employee_log(request, employee, own):
    entries = (
        AuditEntry.objects
        .select_related("actor", "employee")
        .filter(employee=employee)
    )
    entries, applied = _filtered(request, entries)
    return render(request, "audit/log.html", {
        "page": _page(request, entries),
        "subject": employee,
        "is_own": own,
        "actions": AuditAction.choices,
        "is_whole_log": False,
        "querystring": _querystring(request),
        **applied,
    })


@login_required
def mine(request):
    """Your own history. Its own route so the sidebar marks "My time"."""
    employee = Employee.for_user(request.user)
    if employee is None:
        raise Http404
    return _employee_log(request, employee, own=True)


@login_required
def employee_log(request, pk):
    employee = get_object_or_404(Employee, pk=pk)
    if not own_or_manager(request, employee):
        raise Http404
    own = employee.user_id is not None and employee.user_id == request.user.id
    return _employee_log(request, employee, own=own)
