"""Sign-ins, and who looked at whose hours.

The other half of the table. ``signals.py`` records what changed; this records
what *happened* — which for an ISO 27001 questionnaire and for a works council
is the half they ask about first.

----

**Sign-ins were already logged and were still not kept.** ``config/settings.py``
sends them to a rotating file with three backups of two megabytes, which is to
say they are deleted after about eight megabytes of ordinary traffic. That is
fine for finding out why somebody could not get in this morning and is not a log
an auditor accepts, because the question an auditor asks is about March. The file
handler stays — it is what you read while the server is in front of you — and the
record is the table.

**Only the username, never the credentials and never an address.** Django's
``user_login_failed`` hands over the credentials that were tried, password
included; putting those in a table nothing can delete would turn a security
measure into the app's worst secret leak. The IP is left out too, and that is a
decision rather than an oversight: this app deliberately holds no location data
about its staff, an address is personal data under the DSGVO, and "who was
refused" is answerable without one on a system whose users are eleven people in
one building.

----

**The read log is recorded inside ``own_or_manager``**, which is the app's one
door for "may this account see this person's time" — so the place that decides is
also the place that records, and a view added next month is covered by having
gone through the door at all. Two narrowings, both deliberate:

*Safe methods only.* A POST is already an entry with an actor on it; recording
the read as well would double every write and say nothing new.

*Somebody else's only.* An employee reading their own timesheet is not
processing anybody else's data, and logging it would bury the entries that
matter under the ones nobody asked for.

**No collapsing.** The tempting optimisation is one row per manager per employee
per day. It halves the table and it destroys the answer to the question the log
exists for, which is not "did my manager look at my hours" but "how often".
"""

from django.contrib.auth.signals import (
    user_logged_in, user_logged_out, user_login_failed,
)

from apps.audit.models import AuditAction
from apps.audit.recording import record


def _name(user):
    return (user.get_full_name() or user.get_username()) if user else ""


def on_signed_in(sender, request, user, **kwargs):
    record(AuditAction.SIGNED_IN, actor=user, note=_name(user))


def on_signed_out(sender, request, user, **kwargs):
    # ``user`` is None when the session had already expired, which is a sign-out
    # that happened and is worth a row saying so rather than being dropped.
    record(AuditAction.SIGNED_OUT, actor=user, note=_name(user))


def on_sign_in_refused(sender, credentials, **kwargs):
    """A refusal, named by the username that was tried and nothing else.

    ``credentials`` carries the password. Django masks it in the object it
    sends, but the safe thing is not to reach for anything but the username at
    all — a field added to the form next year would otherwise arrive in here on
    its own.
    """
    attempted = (credentials or {}).get("username") or ""
    record(AuditAction.SIGN_IN_REFUSED, note=str(attempted)[:200])


def record_view(request, employee=None, note=""):
    """Somebody looked at somebody else's record.

    Called from ``own_or_manager`` for the pages that show one person, and by
    hand from the manager pages that show everybody at once — where there is no
    single employee to name and the note says which page it was.
    """
    if request is None or request.method not in ("GET", "HEAD"):
        return None
    return record(AuditAction.VIEWED, employee=employee, note=note)


def record_export(request, employee=None, note=""):
    """A copy of the records left the app.

    Recorded for every export without exception, including an employee taking
    their own — the draft ArbZG gives them the right to a copy, and an employer
    who has to show they honoured it needs the same row.
    """
    return record(AuditAction.EXPORTED, employee=employee, note=note)


def connect():
    user_logged_in.connect(on_signed_in, dispatch_uid="audit.signed_in")
    user_logged_out.connect(on_signed_out, dispatch_uid="audit.signed_out")
    user_login_failed.connect(on_sign_in_refused, dispatch_uid="audit.sign_in_refused")
