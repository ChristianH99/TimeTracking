"""Who the signed-in person is *in the organisation*.

Every page needs two of these facts and the sidebar needs all three, so they are
resolved once per request rather than in each view: the ``Employee`` row behind
the account, whether that person may see anybody else's time, and how many
requests are waiting for them to decide.

The manager question is deliberately **not** ``user.is_staff``. Those are two
different rights and conflating them is the mistake this file exists to avoid:
staff manages *accounts* (who may sign in at all), a manager manages *people*
(who works when). A kindergarten's deputy head plans the roster and has no
business creating logins; whoever administers the NAS has a login and may never
have set foot in the building. ``employees.is_manager`` is the roster right; a
superuser is included because an app whose only manager has left has to be
recoverable without a shell on the NAS.
"""

from apps.employees.models import Employee


def who(request):
    """``current_employee``, ``is_manager``, ``pending_request_count``.

    All three are cheap and two of them are needed by ``base.html`` on every
    page, so there is no laziness here to be clever about — except the count,
    which is skipped entirely for the people who cannot act on it.

    There was a fourth, ``hours_style``, carrying the reader's decimal-or-clock
    preference to the ``hours`` filter. Every duration in the app is ``hh:mm``
    now and the preference is gone with it.
    """
    user = getattr(request, "user", None)
    employee = Employee.for_user(user)
    is_manager = bool(
        (employee and employee.is_manager and employee.is_active)
        or (user is not None and user.is_authenticated and user.is_superuser)
    )

    pending = 0
    if is_manager:
        # Imported here rather than at module scope: this module is loaded from
        # the settings' context-processor list, and absences imports employees.
        from apps.absences.models import Absence, RequestStatus

        pending = Absence.objects.filter(status=RequestStatus.REQUESTED).count()

    return {
        "current_employee": employee,
        "is_manager": is_manager,
        "pending_request_count": pending,
    }
