"""Who is doing this, made reachable from a model signal.

A signal handler is handed a model instance and nothing else. It has no request,
which is the one thing an audit entry cannot do without — a trail that records
what changed and not who is half a trail, and the missing half is the one a
labour court asks about.

The alternatives were considered and are worse. Passing the actor down through
every call — ``save(by=request.user)`` — means every write path has to remember,
and a path that forgets records the change as nobody's; that is precisely the
failure mode the model-level backstop on the lock exists to prevent, imported
here on purpose. Auditing from the views instead means the admin, a management
command and a data migration all write silently.

So: a thread-local, set by middleware for the life of one request and cleared
afterwards. Gunicorn serves this app with threads, and each request is on one
thread for its whole life, so a thread-local *is* a request-local here. It is
the standard shape for this problem and it is honest about its one limitation:
a write from a background thread would see whatever that thread last set, which
is nothing, and records as the system.

**A write with no actor is recorded as the system rather than left blank.** They
are different statements — "we do not know who" and "nobody was signed in" — and
a seeder, a migration or a management command is genuinely the second. Blank
would let a real gap hide among them.
"""

import contextlib
import threading

_state = threading.local()


def current_actor():
    """The signed-in ``User`` for this thread, or ``None``."""
    return getattr(_state, "actor", None)


def current_actor_label():
    """The name to freeze onto an entry. Never blank — see the module docstring."""
    from apps.audit.models import SYSTEM_ACTOR

    user = current_actor()
    if user is None:
        return SYSTEM_ACTOR
    return user.get_full_name() or user.get_username() or SYSTEM_ACTOR


@contextlib.contextmanager
def acting_as(user):
    """Run a block as somebody, for a management command or a test.

    Restores rather than clears on the way out, so nesting one inside a request
    does not leave the request without its actor for whatever runs afterwards.
    """
    previous = getattr(_state, "actor", None)
    _state.actor = user
    try:
        yield
    finally:
        _state.actor = previous


class AuditActorMiddleware:
    """Puts ``request.user`` where a model signal can reach it.

    **Must sit below ``AuthenticationMiddleware``**, which is where
    ``request.user`` comes from — above it and every entry in the app would say
    ``system``, which is a trail that looks complete and names nobody.

    Cleared in a ``finally`` rather than after the response: a view that raises
    would otherwise leave this thread carrying the last actor into whichever
    request the worker picks up next, and the entry it wrote would name the
    wrong person. That is worse than naming nobody.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        _state.actor = user if (user is not None and user.is_authenticated) else None
        try:
            return self.get_response(request)
        finally:
            _state.actor = None
