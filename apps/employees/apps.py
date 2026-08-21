from django.apps import AppConfig


class EmployeesConfig(AppConfig):
    name = "apps.employees"
    label = "employees"
    verbose_name = "Employees"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        # Connected in ready() rather than with a decorator: that is the one
        # point Django guarantees runs once, after the app registry is
        # populated. dispatch_uid so an autoreload re-importing this module does
        # not stack a second copy of the handler.
        user_logged_in.connect(_attach_employee, dispatch_uid="employees.link_on_login")


def _attach_employee(sender, request, user, **kwargs):
    """Attach the matching employee row at sign-in, when there is exactly one.

    This is the moment the whole nullable ``Employee.user`` exists for. A
    manager rosters eleven people before any of them has ever signed in — the
    provider creates their account at the first token and not a second earlier —
    so the link has to be made *here*, on the way in, or every one of them lands
    on a page saying they have no contract while their contract is sitting in
    the table.

    The key is the **directory name** — the ``preferred_username`` the provider
    read out of LDAP, which is the ``firstname.surname`` a manager typed onto
    the contract. It is taken from the identity row rather than from
    ``user.username``, because for an SSO account the local username is the
    opaque ``sub`` and would never match anything.

    ``Employee.link_by_username`` returns ``None`` rather than guessing: no
    name, no matching row, or an employee already linked elsewhere all mean
    nothing happens and a manager makes the link by hand. That is visible and
    undoable; a wrong guess signs somebody in as their colleague and shows them
    somebody else's hours.

    Never raises. This runs inside the login transaction — including the OIDC
    callback, where an exception is a sign-in that fails with no explanation
    and no way for the person to work around it. A missed link is a page that
    says "no contract"; a raised exception is an app nobody can get into.
    """
    import logging

    from apps.employees.models import Employee

    log = logging.getLogger(__name__)
    try:
        identity = getattr(user, "sso_identity", None)
        directory_name = getattr(identity, "provider_username", "") if identity else ""
        employee = Employee.link_by_username(user, directory_name)
    except Exception:  # noqa: BLE001 - a login must not fail over this
        log.exception("Could not link an employee to %s", getattr(user, "pk", "?"))
        return
    if employee is not None:
        log.info(
            "Linked %s to employee %s by the directory name %r",
            user.get_username(), employee.pk, directory_name or user.get_username(),
        )
