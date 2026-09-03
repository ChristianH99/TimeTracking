"""Writing an entry: the one function everything else goes through.

Split from ``models.py`` so that the model stays a description of the table and
this stays the description of *how a row comes to exist*. Both halves are read by
somebody asking different questions.

**Failing to write an entry must never fail the thing being audited.** That
sounds like the wrong way round for a compliance feature and it is not: a bug in
this module would otherwise make the timesheet unusable, and an employer who
cannot record hours at all is in far deeper trouble under §16 ArbZG than one
whose trail has a gap. So the writer swallows and logs. The gap is visible — the
log file says so, and the entries either side of it have a hole between them —
which is the honest failure. `docs/AUDIT.md` names this as the residual risk.
"""

import logging

from apps.audit.models import (
    REDACTED, AuditAction, AuditEntry, is_redacted, value_as_text,
)

logger = logging.getLogger(__name__)


def _employee_of(instance):
    """The person a record belongs to, if it belongs to one.

    Three shapes, because three exist and guessing wrong would file a day of
    Anna's under nobody: the record *is* an employee, the record *has* one, or
    the record reaches one through its day (a ``WorkSegment``).

    Reads ``_id`` attributes wherever it can. Following the relation would be a
    query per audited save on the hottest write path in the app, and the entry
    only needs the key — the readable name comes from ``_label`` beside it, and
    that one query is worth paying once here rather than never being right.
    """
    from apps.employees.models import Employee

    if isinstance(instance, Employee):
        return instance
    for attribute in ("employee", "day"):
        related = getattr(instance, attribute, None)
        if related is None:
            continue
        if isinstance(related, Employee):
            return related
        nested = getattr(related, "employee", None)
        if isinstance(nested, Employee):
            return nested
    return None


def _date_of(instance):
    """The date the record is *about*, which is not when it was written.

    A timesheet row for the 3rd edited on the 20th has both, and the two
    questions asked of this table want different ones: an auditor asks about the
    first, a security reviewer about the second.
    """
    for attribute in ("date", "start_date", "valid_from"):
        value = getattr(instance, attribute, None)
        if value is not None and hasattr(value, "year"):
            return value
    day = getattr(instance, "day", None)
    if day is not None:
        return getattr(day, "date", None)
    return None


def record(action, instance=None, changes=None, note="", employee=None,
           subject="", subject_id="", subject_date=None, actor=None):
    """Write one entry. Returns it, or ``None`` if it could not be written.

    Everything is optional because the four kinds of entry fill in different
    halves: a diff has an instance and no note, a sign-in has a note and no
    instance at all.
    """
    from apps.audit.actor import current_actor, current_actor_label
    from apps.audit.registry import label_of

    try:
        if instance is not None:
            subject = subject or label_of(instance)
            subject_id = subject_id or str(instance.pk or "")
            if employee is None:
                employee = _employee_of(instance)
            if subject_date is None:
                subject_date = _date_of(instance)

        if actor is None:
            actor = current_actor()
            label = current_actor_label()
        else:
            label = actor.get_full_name() or actor.get_username()

        return AuditEntry.objects.create(
            action=action,
            actor=actor if (actor is not None and actor.pk) else None,
            actor_label=label[:150],
            employee=employee,
            employee_label=(str(employee) if employee is not None else "")[:150],
            subject=subject[:64],
            subject_id=subject_id[:40],
            subject_date=subject_date,
            changes=changes or {},
            note=note[:200],
        )
    except Exception:  # noqa: BLE001 — see the module docstring
        logger.exception("could not write an audit entry for %s", action)
        return None


# --------------------------------------------------------------------------
# The diff
# --------------------------------------------------------------------------

# Never diffed. Each is written by the machine rather than by a person, and an
# entry saying "updated_at changed" on every single save would be a trail whose
# every row is noise — which is a trail nobody reads, which is no trail.
#
# **``id`` is in here and that is the important one.** A create "changes" every
# field, so without this every new row would open with its own primary key as the
# first line of the diff — a number that means nothing to anybody and that the
# entry already carries in ``subject_id``.
IGNORED_FIELDS = {"id", "pk", "updated_at", "created_at", "at"}

# Foreign keys the entry already answers on its own. A ``WorkSegment``'s ``day``
# and a ``DayRecord``'s ``employee`` are exactly what ``employee_label`` and
# ``subject_date`` say, and repeating them as raw row ids — "day — → 6" — is the
# same fact written twice, once unreadably.
STRUCTURAL_RELATIONS = {"employees.Employee", "timesheets.DayRecord"}


def _is_structural(field):
    from apps.audit.registry import label_of

    remote = getattr(field, "related_model", None)
    return remote is not None and label_of(remote) in STRUCTURAL_RELATIONS


def snapshot(instance):
    """Every concrete field of an instance, as ``{name: value}``.

    Foreign keys are read through ``attname`` (``employee_id``) rather than by
    following them, so taking a snapshot costs no queries. The readable version
    happens in ``diff`` below, and only for the fields that actually changed —
    which on an ordinary save is one or two of them rather than twenty.
    """
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in IGNORED_FIELDS or _is_structural(field):
            continue
        values[field.name] = getattr(instance, field.attname, None)
    return values


def resolve(instance, name, value):
    """One stored value as a person would read it.

    A foreign key is followed *here* rather than in ``snapshot``, so the query is
    paid only for a field that actually changed — which on an ordinary save is
    one or two rather than twenty. "confirmed_by 4 → 7" is a diff nobody can act
    on; "confirmed_by Ben Kraus" is the sentence somebody opened the page for.

    A key pointing at a row that has since been deleted resolves to the id it
    held, which is honest: the reference is all that is left of it.
    """
    if value is None or instance is None:
        return value_as_text(value)
    try:
        field = instance._meta.get_field(name)
    except Exception:  # noqa: BLE001 — a field the model no longer has
        return value_as_text(value)
    remote = getattr(field, "related_model", None)
    if remote is None:
        return value_as_text(value)
    try:
        return str(remote._default_manager.filter(pk=value).first() or value)
    except Exception:  # noqa: BLE001
        return value_as_text(value)


def diff(before, after, instance=None):
    """``{field: [old, new]}`` for what actually changed, already as text.

    Empty when nothing did — and the caller writes no entry in that case, which
    is what keeps the roster usable: its save posts the whole week every time,
    so without this every drag would write fifty rows saying nothing happened.
    """
    changed = {}
    for name, new in after.items():
        old = before.get(name)
        if old == new:
            continue
        if is_redacted(name):
            # Recorded as having changed, never by value. The one table nothing
            # can delete must not accumulate secrets.
            changed[name] = [REDACTED, REDACTED]
        else:
            changed[name] = [resolve(instance, name, old), resolve(instance, name, new)]
    return changed


__all__ = [
    "AuditAction", "diff", "record", "resolve", "snapshot",
]
