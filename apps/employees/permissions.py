"""Who may look at somebody else's time.

This is the app's third door and it is not either of the two in
``apps/accounts/permissions.py``. Those ask who may administer the *software*;
this asks who may administer the *people*, and in a kindergarten or a school
those are reliably different sets. The deputy head plans the roster and decides
holiday requests and has no business creating logins. Whoever looks after the
NAS has every login right there is and may never have met the staff.

So: ``manager_required`` reads ``Employee.is_manager``, plus superusers — an app
whose only manager has left has to be recoverable without a shell on the NAS.
``user.is_staff`` is deliberately *not* enough.

Like the other two, these answer **404 rather than 403**. A bare 403 is a dead
end with no way back into the app; a 404 renders the app's own not-found page.
There is nothing to conceal either way, since the links are only in the sidebar
for the people who may follow them.

The exposure a forgotten decorator would create is covered from the other side:
``apps/employees/tests.py`` walks the URLconf for every route in the manager
apps and refuses to let any of them answer an ordinary employee.
"""

from functools import wraps

from django.http import Http404

from apps.employees.models import Employee


def is_manager(user):
    """Whether this account may see the team's time.

    Written as a function as well as a decorator because the templates and
    ``apps/employees/context.py`` ask the same question, and two implementations
    of "who may" is how a page ends up showing a link that 404s.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    employee = Employee.for_user(user)
    return bool(employee and employee.is_manager and employee.is_active)


def manager_required(view):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not is_manager(request.user):
            raise Http404
        return view(request, *args, **kwargs)

    return guarded


def own_or_manager(request, employee):
    """Whether this request may see *this* employee's time.

    The rule every timesheet and absence view shares: your own, always; anybody
    else's, only as a manager. Written once because the two halves are easy to
    get subtly wrong apart — an employee whose account has been unlinked has no
    ``user``, and ``employee.user_id == request.user.id`` with both sides None
    would hand every unlinked employee's timesheet to anybody signed in.
    """
    if employee is None:
        return False
    if employee.user_id is not None and employee.user_id == request.user.id:
        return True
    return is_manager(request.user)
