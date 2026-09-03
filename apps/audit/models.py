"""What changed, who changed it, and what it was before.

**The one thing this app was missing that every auditor asks for.** The GoBD
calls it *Unveränderbarkeit* and does not mean "records cannot be changed" — it
means a record may not be changed *so that the original content is no longer
ascertainable*. Changes are expected; silently overwriting is what is forbidden.
IDW PS 880 tests the same property as the journal function. ISO 27001 A.8.15
asks for it as event logging. And in front of a labour court it is the whole
difference between a document and a claim: a confirmed timesheet that can be
rewritten afterwards with no trace says only what it says today.

``docs/AUDIT.md`` sets out the four bodies that arrive at this from four
directions. This module is the answer to all of them.

----

**One table, not four.** "Who changed this record", "who signed in", "who looked
at whose hours" and "who exported what" read as different features and are the
same question asked about different objects — and four tables would be four
retention stories, four pages and four chances for one of them to be forgotten
when the retention policy finally lands. ``action`` is what tells them apart.

**Append-only, enforced on the model.** ``save`` refuses an update and ``delete``
raises. Not a convention and not a permission: a log a forgotten line can edit is
not a log, and this is the one table in the app whose whole value is that nothing
can touch it afterwards. The same argument ``assert_unlocked`` makes about the
lock, one level stronger — a lock can be lifted by a manager, and this cannot be
lifted by anybody.

**Names are frozen beside the keys.** ``actor`` and ``employee`` are nullable
foreign keys with ``SET_NULL``, because deleting an account must not take the
timesheet with it — and that means the day somebody's account is removed, every
audit row pointing at them would say *nobody did this*. So the readable name is
copied onto the row when it is written. The key is for filtering; the text is the
record. They are allowed to disagree, and when they do the text is right: it is
what was true at the time.

**Values are stored as text, old and new.** A diff holding a foreign key id is a
diff nobody can read in three years, and a diff holding a raw ``TimeField`` is
one that depends on this codebase still existing to interpret it. What goes in is
what a person would have seen on the page.

**Secrets are never diffed.** A field whose name looks like a secret records
*that* it changed and never the values — otherwise the one table that can never
be deleted would accumulate every OIDC client secret the installation has ever
had.
"""

import datetime as dt

from django.conf import settings as django_settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.employees.models import Employee


class AuditAction(models.TextChoices):
    """What kind of thing happened.

    Deliberately coarse. The value of a log is that somebody can scan it, and a
    vocabulary with fifteen verbs in it is one where two people writing the same
    kind of entry pick different words.
    """

    CREATED = "created", _("created")
    CHANGED = "changed", _("changed")
    DELETED = "deleted", _("deleted")
    # A month closed or reopened. Its own action rather than a ``changed`` on a
    # `DayLock`, because the unit somebody locks is a *month* and thirty-one
    # rows saying "created" would bury the one sentence that matters.
    LOCKED = "locked", _("locked")
    UNLOCKED = "unlocked", _("unlocked")
    # Somebody looked at somebody else's hours. The entry the works council
    # asks for, and the only processing this app does that the people recorded
    # in it could not otherwise see.
    VIEWED = "viewed", _("looked at")
    EXPORTED = "exported", _("exported")
    # The security half. A rotating log file with three backups is a log that is
    # deleted after about eight megabytes, which is not one an auditor accepts.
    SIGNED_IN = "signed-in", _("signed in")
    SIGN_IN_REFUSED = "sign-in-refused", _("sign-in refused")
    SIGNED_OUT = "signed-out", _("signed out")


# Written on a row whose actor was not a person: a management command, a data
# migration, a fixture. **Not left blank**, because blank reads as "we do not
# know" and this is a different statement — nobody was signed in, and that is
# itself the fact. `docs/AUDIT.md` counts an unattributed change as a finding.
SYSTEM_ACTOR = "system"

# A field whose name contains one of these is recorded as having changed and
# never by value. See the module docstring.
REDACTED_HINTS = ("secret", "password", "token", "key")
REDACTED = "••••••"


class AuditImmutable(Exception):
    """Raised by any attempt to change or remove an entry.

    Not a ``ValidationError``: this is not a form somebody can correct, it is a
    thing the app does not do. A caller who catches this and carries on has
    misunderstood what the table is for.
    """


class AuditEntry(models.Model):
    """One thing that happened, and what it looked like before.

    Rows are written by ``apps.audit.signals`` for every model in the registry
    and explicitly by the handful of acts whose natural unit is bigger than a
    row — locking a month, regenerating a year of public holidays.
    """

    at = models.DateTimeField(_("when"), auto_now_add=True, db_index=True)
    action = models.CharField(
        _("what happened"), max_length=20, choices=AuditAction.choices,
    )

    # -- who ---------------------------------------------------------------
    actor = models.ForeignKey(
        django_settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+", editable=False,
    )
    # The name as it was. See the module docstring: the key can become null and
    # this cannot.
    actor_label = models.CharField(_("who"), max_length=150, default=SYSTEM_ACTOR)

    # -- whose ------------------------------------------------------------
    #
    # Nullable, because plenty of entries are about nobody in particular: a
    # sign-in, a change to the break table, a public holiday. It is filled in
    # wherever the record belongs to a person, which is what makes "show me
    # everything that ever touched this timesheet" one query.
    employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="audit_entries", editable=False,
    )
    employee_label = models.CharField(_("about"), max_length=150, blank=True)

    # -- what --------------------------------------------------------------
    subject = models.CharField(_("record"), max_length=64, blank=True)
    subject_id = models.CharField(max_length=40, blank=True)
    # The date the record is *about*, which is not the date it was written. A
    # timesheet row for the 3rd edited on the 20th has both, and an auditor asks
    # about the first while a security reviewer asks about the second.
    subject_date = models.DateField(null=True, blank=True, db_index=True)

    # {field: [old, new]} — both already written as a person would read them.
    changes = models.JSONField(default=dict, blank=True)
    # For an act that is not a field diff: "September 2025, 30 days".
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        # Newest first, and the id as the tie-break: `auto_now_add` is only
        # microsecond-resolution and two entries written inside one transaction
        # can share it exactly. Without the second key the order of a save's own
        # entries is whatever the database feels like, which on a page that
        # reads "before → after" is the difference between a story and a jumble.
        ordering = ["-at", "-id"]
        verbose_name = _("audit entry")
        verbose_name_plural = _("audit entries")
        indexes = [
            models.Index(fields=["employee", "-at"]),
            models.Index(fields=["actor", "-at"]),
            models.Index(fields=["subject", "subject_id"]),
            models.Index(fields=["action", "-at"]),
        ]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.actor_label} {self.action} {self.subject}"

    def save(self, *args, **kwargs):
        """Insert only. An entry that already exists cannot be written again.

        ``self.pk`` is the test rather than ``_state.adding`` because a caller
        who set the pk by hand is doing the thing this refuses, and
        ``_state.adding`` would let them.
        """
        if self.pk is not None:
            raise AuditImmutable(
                "An audit entry cannot be changed once it is written. That is "
                "the whole of what it is for."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditImmutable(
            "An audit entry cannot be deleted. A retention policy that reaches "
            "this table is a decision to make deliberately and in one place — "
            "see docs/AUDIT.md — and not something a view does by accident."
        )

    # -- reading it back ---------------------------------------------------

    @property
    def is_security_event(self):
        """Whether this belongs to the sign-in half rather than the record half.

        The two are one table and two questions, and the page filters on this
        rather than on a list of actions written out again — a tenth action
        added next year has to land on one side of the line, and here is where
        that is decided once.
        """
        return self.action in {
            AuditAction.SIGNED_IN,
            AuditAction.SIGN_IN_REFUSED,
            AuditAction.SIGNED_OUT,
        }

    @property
    def change_list(self):
        """``changes`` as ``[(label, old, new), …]``, in a stable order.

        Sorted by field name rather than left in whatever order the diff
        happened to build, because two entries about the same record read
        against each other and a column that moves between them cannot be
        compared by eye.

        **The field is stored by its machine name and shown by its label**, and
        that split is deliberate. Storing the label would freeze whichever
        language was active when the entry was written — a table that ends up
        half German and half English, permanently, because nothing can rewrite
        it. Storing the name keeps the JSON queryable and stable, and the label
        is resolved here at read time in the reader's own language. A model or a
        field that has since been renamed falls back to the stored name, which is
        the honest answer: that is what the record actually says.
        """
        return [
            (self.label_for(field), pair[0], pair[1])
            for field, pair in sorted(self.changes.items())
        ]

    def label_for(self, field_name):
        """A field's ``verbose_name``, or the raw name when it cannot be found."""
        from django.apps import apps as django_apps

        try:
            model = django_apps.get_model(self.subject)
            return str(model._meta.get_field(field_name).verbose_name)
        except Exception:  # noqa: BLE001 — a renamed model or field
            return field_name


def value_as_text(value):
    """One field value, written the way somebody would have seen it.

    The point of doing this at write time rather than at read time is that the
    entry then does not depend on this codebase still existing to be understood
    — which is the difference between an audit trail and a debugging aid. A
    ``TimeField`` stored as a ``datetime.time`` repr is readable today and is a
    Python detail in five years.

    ``None`` becomes the empty string, deliberately: on a page a missing value
    and an empty one look the same, and the pair ``["", "08:00"]`` reads as "it
    was not set and now it is" without needing a null in the JSON.
    """
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, dt.date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, dt.time):
        return value.strftime("%H:%M")
    if isinstance(value, bool):
        # "True"/"False" is a programmer's answer. yes/no is what the column
        # means, and it survives being read by somebody who does not write code.
        return "yes" if value else "no"
    if isinstance(value, models.Model):
        return str(value)
    return str(value)


def is_redacted(field_name):
    lowered = field_name.lower()
    return any(hint in lowered for hint in REDACTED_HINTS)
