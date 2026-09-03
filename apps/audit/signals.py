"""Catching every write, including the ones nobody remembered to tell us about.

**Signals rather than calls in the views**, and the reason is the one this
codebase keeps arriving at: the exposure is never a check somebody removed, it is
a check somebody forgot on a path added last Tuesday. ``assert_unlocked`` is
called by every view *and again* by ``DayRecord.save``, because a view that
forgot would otherwise save in silence. This is the same argument one level out:
a management command, a data migration, the Django admin and a fixture all write
through the model, and none of them would ever have called an audit function.

Connected in ``AuditConfig.ready`` with a ``dispatch_uid``, the same shape
``apps/timesheets/apps.py`` uses for the SQLite pragmas, so an autoreload that
re-imports the module does not stack a second copy of every handler.

----

**The old values come from ``pre_save``, and only for an update.** A create has
nothing to compare against, and skipping the fetch for one keeps the common case
— the roster fill, the seeder, a month of confirmations — at exactly the query
count it had before. An update pays one extra ``SELECT``, which is the price of
being able to say what a figure used to be.

**The snapshot is stashed on the instance rather than in a dictionary keyed by
pk.** A module-level cache would be shared between threads and would leak on any
save that raised; an attribute lives exactly as long as the object does.

**What ``bulk_create`` does not do.** It fires no ``post_save`` at all, so a
model written that way is silently outside this. Two answers, both in
``apps/audit/registry.py``: ``WorkSegment``'s bulk creates were changed into
ordinary saves — they are one to four rows and the batching bought nothing —
and ``DayLock`` and ``BankHoliday`` write one deliberate entry each, because
thirty-one rows saying "locked" about consecutive dates is not what anybody
needs to read. ``QuerySet.update()`` is the same blind spot and is used in
exactly one place on an audited model, ``DayRecord.stamp_entry``, deliberately:
a timestamp the system stamps on first entry is not somebody changing a record.
"""

from django.db.models.signals import post_delete, post_save, pre_save

from apps.audit import recording
from apps.audit.models import AuditAction
from apps.audit.registry import BY_SIGNAL, label_of

_SNAPSHOT = "_audit_snapshot"


def _is_audited(instance):
    return label_of(instance) in BY_SIGNAL


def before_save(sender, instance, **kwargs):
    """Stash what the row looks like now, so ``after_save`` can say what changed.

    Silent on anything that goes wrong reading it — a row that vanished between
    this and the write, a model whose manager is filtered. The save must not fail
    because the trail could not be taken; see ``recording``.
    """
    if not _is_audited(instance) or instance.pk is None:
        return
    try:
        previous = sender._default_manager.filter(pk=instance.pk).first()
    except Exception:  # noqa: BLE001
        previous = None
    setattr(instance, _SNAPSHOT, recording.snapshot(previous) if previous else None)


def after_save(sender, instance, created, **kwargs):
    """One entry, or none at all when nothing actually changed.

    The "or none" half is load-bearing rather than tidy. The roster posts the
    whole week on every drag and the month posts a whole day on every keystroke
    that lands; without this, one card moved would write fifty rows all saying
    that nothing about those fifty shifts is different.
    """
    if not _is_audited(instance):
        return
    before = getattr(instance, _SNAPSHOT, None)
    # Clear it whatever happens next: an instance saved twice in one request
    # would otherwise diff the second save against the state before the first.
    if hasattr(instance, _SNAPSHOT):
        delattr(instance, _SNAPSHOT)

    after = recording.snapshot(instance)
    if created or before is None:
        # A create records the row it made rather than a diff against nothing.
        # Blank fields are dropped: a new record listing twenty empty columns
        # buries the three that were filled in.
        changes = {
            name: ["", recording.resolve(instance, name, value)]
            for name, value in after.items()
            if value not in (None, "", 0, False)
        }
        recording.record(AuditAction.CREATED, instance, changes=changes)
        return

    changes = recording.diff(before, after, instance)
    if not changes:
        return
    recording.record(AuditAction.CHANGED, instance, changes=changes)


def after_delete(sender, instance, **kwargs):
    """What was removed, and what it held.

    A delete records the row's *values* and not a diff, because "it is gone" is
    only half the sentence — the half somebody needs a year later is what it said
    before it went.
    """
    if not _is_audited(instance):
        return
    values = {
        name: [recording.resolve(instance, name, value), ""]
        for name, value in recording.snapshot(instance).items()
        if value not in (None, "", 0, False)
    }
    recording.record(AuditAction.DELETED, instance, changes=values)


def connect():
    pre_save.connect(before_save, dispatch_uid="audit.before_save")
    post_save.connect(after_save, dispatch_uid="audit.after_save")
    post_delete.connect(after_delete, dispatch_uid="audit.after_delete")
