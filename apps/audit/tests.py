"""The trail: that it catches everything, and that nothing can edit it.

Two of these matter more than the rest.

``TestNothingCanTouchIt`` is the whole feature. The GoBD does not forbid changing
a record — it forbids changing one *so that the original content is no longer
ascertainable*. An audit table that a view could quietly correct would be a table
that says whatever the last person to touch it wanted it to say, which is worth
less than nothing because it looks authoritative.

``TestEveryModelHasBeenDecidedAbout`` is the sweep, and it is the reason this
still works next year. It walks every model in the project against
``apps/audit/registry.py`` and fails on one that is in none of the three sets —
the same shape as the open-URL list and the URLconf walks, because the exposure
is never a decision somebody reversed, it is a table somebody added on a Tuesday.
"""

import datetime as dt

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.urls import reverse

from apps.absences.models import Absence, AbsenceKind, RequestStatus
from apps.audit import registry
from apps.audit.actor import acting_as
from apps.audit.models import (
    REDACTED, AuditAction, AuditEntry, AuditImmutable, SYSTEM_ACTOR,
)
from apps.timesheets.models import DayLock, DayRecord, WorkSegment


def entries_for(**filters):
    return list(AuditEntry.objects.filter(**filters))


# --------------------------------------------------------------------------
# The property the whole thing rests on
# --------------------------------------------------------------------------

class TestNothingCanTouchIt:

    def test_an_entry_cannot_be_changed(self, db):
        entry = AuditEntry.objects.create(action=AuditAction.CREATED, note="as written")
        entry.note = "as somebody would prefer"
        with pytest.raises(AuditImmutable):
            entry.save()
        entry.refresh_from_db()
        assert entry.note == "as written"

    def test_an_entry_cannot_be_deleted(self, db):
        entry = AuditEntry.objects.create(action=AuditAction.CREATED)
        with pytest.raises(AuditImmutable):
            entry.delete()
        assert AuditEntry.objects.filter(pk=entry.pk).exists()

    def test_setting_a_primary_key_by_hand_does_not_get_round_it(self, db):
        """``self.pk is not None`` rather than ``_state.adding``.

        A caller who assigns the pk of an existing row and saves is doing exactly
        the thing this refuses, and ``_state.adding`` would happily let them —
        which is an overwrite wearing an insert's clothes.
        """
        first = AuditEntry.objects.create(action=AuditAction.CREATED, note="first")
        second = AuditEntry(action=AuditAction.DELETED, note="second", pk=first.pk)
        with pytest.raises(AuditImmutable):
            second.save()


# --------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------

def test_every_model_has_been_decided_about():
    """No model may be outside all three sets in ``apps/audit/registry.py``.

    A model added next month is either evidence or it is not, and either answer
    is fine — what is not fine is nobody having asked. This is the same shape as
    ``apps/accounts/pages.py``: the list fails towards being noticed.
    """
    declared = registry.all_declared()
    undeclared = sorted(
        registry.label_of(model)
        for model in django_apps.get_models()
        if registry.label_of(model) not in declared
    )
    assert not undeclared, (
        f"these models are in neither BY_SIGNAL, BY_HAND nor EXEMPT: {undeclared}. "
        "Decide which, and say why in the registry — a table nobody classified is "
        "a table silently outside the audit trail."
    )


def test_the_three_sets_do_not_overlap():
    """A model in two sets would be audited twice or not at all, depending on
    which check ran first — and which that is is not written down anywhere."""
    assert not (registry.BY_SIGNAL & registry.BY_HAND)
    assert not (registry.BY_SIGNAL & registry.EXEMPT)
    assert not (registry.BY_HAND & registry.EXEMPT)


def test_every_declared_model_actually_exists():
    """A renamed model must fail here rather than quietly stop being audited."""
    real = {registry.label_of(model) for model in django_apps.get_models()}
    missing = sorted(registry.all_declared() - real)
    assert not missing, f"named in the registry but not in the project: {missing}"


# --------------------------------------------------------------------------
# What a change looks like
# --------------------------------------------------------------------------

class TestWhatChanged:

    def test_a_created_record_is_recorded(self, anna, org, db):
        DayRecord.objects.create(employee=anna, date=dt.date(2025, 9, 1))
        entry = AuditEntry.objects.filter(subject="timesheets.DayRecord").first()
        assert entry.action == AuditAction.CREATED
        assert entry.employee == anna
        assert entry.subject_date == dt.date(2025, 9, 1)

    def test_a_change_records_both_values(self, anna, org, db):
        record = DayRecord.objects.create(employee=anna, date=dt.date(2025, 9, 1))
        record.note = "worked from the other site"
        record.save()

        entry = AuditEntry.objects.filter(action=AuditAction.CHANGED).first()
        assert entry.changes["note"] == ["", "worked from the other site"]

    def test_a_save_that_changes_nothing_writes_nothing(self, anna, org, db):
        """The half that keeps the table readable.

        The roster posts the whole week on every drag and the month posts a whole
        day on every box that is left. Without this, moving one card would write
        fifty rows each saying that nothing about those fifty shifts is
        different — and a log of nothing is a log nobody opens.
        """
        record = DayRecord.objects.create(employee=anna, date=dt.date(2025, 9, 1))
        before = AuditEntry.objects.count()
        record.save()
        record.save()
        assert AuditEntry.objects.count() == before

    def test_a_delete_records_what_it_held(self, anna, org, db):
        """"It is gone" is half a sentence. The half somebody needs a year later
        is what it said before it went."""
        record = DayRecord.objects.create(
            employee=anna, date=dt.date(2025, 9, 1),
            correction_minutes=30, correction_reason="drove to the second site",
        )
        record.delete()
        entry = AuditEntry.objects.filter(action=AuditAction.DELETED).first()
        assert entry.changes["correction_reason"] == ["drove to the second site", ""]

    def test_bookings_are_caught_although_the_day_writes_them_wholesale(self, anna, org, db):
        """The ``bulk_create`` blind spot, pinned.

        ``set_bookings`` deletes the segments and writes new ones. A queryset
        delete fires every ``post_delete`` and ``bulk_create`` fires no
        ``post_save`` at all — so with the original implementation the trail
        would have shown each edit as the day being emptied and never as it being
        filled in again. That is worse than recording nothing, because it reads
        as somebody having cleared the day.
        """
        record = DayRecord.objects.create(employee=anna, date=dt.date(2025, 9, 1))
        record.set_bookings([(dt.time(8), dt.time(16))])

        created = entries_for(subject="timesheets.WorkSegment", action=AuditAction.CREATED)
        assert len(created) == 1
        assert created[0].employee == anna
        assert created[0].subject_date == dt.date(2025, 9, 1)

    def test_a_secret_is_recorded_as_changed_and_never_by_value(self, db):
        """The one table nothing can delete must not accumulate secrets."""
        from apps.accounts.models import SSOConfiguration

        configuration = SSOConfiguration.objects.create(
            op_base="https://sso.example.invalid", client_id="tt",
        )
        configuration.set_client_secret("hunter2-and-not-in-the-log")
        configuration.save()

        for entry in AuditEntry.objects.filter(subject="accounts.SSOConfiguration"):
            for _field, pair in entry.changes.items():
                assert "hunter2" not in str(pair)
        secret_entries = [
            entry for entry in AuditEntry.objects.filter(subject="accounts.SSOConfiguration")
            if any("secret" in field for field in entry.changes)
        ]
        assert secret_entries, "the change itself still has to be recorded"
        assert secret_entries[0].changes["client_secret_encrypted"] == [REDACTED, REDACTED]


# --------------------------------------------------------------------------
# Who
# --------------------------------------------------------------------------

class TestWho:

    def test_a_write_with_nobody_signed_in_is_the_system(self, anna, org, db):
        """Not blank. "We do not know who" and "nobody was signed in" are
        different statements, and a seeder or a migration is genuinely the
        second — leaving it blank would let a real gap hide among them."""
        DayRecord.objects.create(employee=anna, date=dt.date(2025, 9, 1))
        assert AuditEntry.objects.first().actor_label == SYSTEM_ACTOR

    def test_a_write_inside_a_request_names_the_person(self, anna, org, db):
        who = User.objects.create_user("ben", first_name="Ben", last_name="Roth")
        with acting_as(who):
            DayRecord.objects.create(employee=anna, date=dt.date(2025, 9, 1))
        entry = AuditEntry.objects.first()
        assert entry.actor == who
        assert entry.actor_label == "Ben Roth"

    def test_the_name_survives_the_account_being_deleted(self, anna, org, db):
        """``SET_NULL`` from the account, and the readable name frozen beside it.

        Deleting an account must not take a timesheet with it — which means the
        day it happens, every audit row pointing at that account would say
        *nobody did this* unless the name had been copied onto the row.
        """
        who = User.objects.create_user("ben", first_name="Ben", last_name="Roth")
        with acting_as(who):
            DayRecord.objects.create(employee=anna, date=dt.date(2025, 9, 1))
        who.delete()

        entry = AuditEntry.objects.filter(subject="timesheets.DayRecord").first()
        assert entry.actor is None
        assert entry.actor_label == "Ben Roth"

    def test_the_middleware_clears_the_actor_even_when_a_view_raises(self, db):
        """Otherwise the worker carries the last actor into the next request and
        attributes somebody else's change to them — which is worse than naming
        nobody at all."""
        from apps.audit.actor import AuditActorMiddleware, current_actor

        who = User.objects.create_user("ben")

        class _Request:
            method = "GET"
            user = who

        def explode(request):
            raise RuntimeError("the view failed")

        middleware = AuditActorMiddleware(explode)
        with pytest.raises(RuntimeError):
            middleware(_Request())
        assert current_actor() is None


# --------------------------------------------------------------------------
# The acts with a unit bigger than a row
# --------------------------------------------------------------------------

class TestLockingIsOneEntry:

    def test_a_month_locked_is_one_entry_and_not_thirty_one(self, anna, org, db):
        days = [dt.date(2025, 9, 1) + dt.timedelta(days=n) for n in range(30)]
        DayLock.lock(anna, days, by=None)

        locked = entries_for(action=AuditAction.LOCKED)
        assert len(locked) == 1
        assert "01.09.2025" in locked[0].note and "30.09.2025" in locked[0].note
        assert "(30)" in locked[0].note
        assert locked[0].employee == anna

    def test_unlocking_is_one_entry_too(self, anna, org, db):
        days = [dt.date(2025, 9, 1) + dt.timedelta(days=n) for n in range(30)]
        DayLock.lock(anna, days, by=None)
        DayLock.unlock(anna, days)

        assert len(entries_for(action=AuditAction.UNLOCKED)) == 1

    def test_locking_nothing_new_records_nothing(self, anna, org, db):
        DayLock.lock(anna, [dt.date(2025, 9, 1)], by=None)
        before = AuditEntry.objects.count()
        DayLock.lock(anna, [dt.date(2025, 9, 1)], by=None)
        assert AuditEntry.objects.count() == before


# --------------------------------------------------------------------------
# Sign-ins, and who looked at whose hours
# --------------------------------------------------------------------------

class TestTheSecurityHalf:

    def test_signing_in_is_recorded(self, db, org):
        from django.test import Client

        User.objects.create_user("ben", password="pw", first_name="Ben")
        Client().login(username="ben", password="pw")
        assert entries_for(action=AuditAction.SIGNED_IN)

    def test_a_refusal_is_recorded_by_username_and_nothing_else(self, db, org):
        """The password must not reach a table nothing can delete."""
        from django.test import Client

        User.objects.create_user("ben", password="pw")
        Client().login(username="ben", password="definitely-the-wrong-password")

        refusals = entries_for(action=AuditAction.SIGN_IN_REFUSED)
        assert len(refusals) == 1
        assert refusals[0].note == "ben"
        for entry in AuditEntry.objects.all():
            assert "definitely-the-wrong-password" not in str(entry.note)
            assert "definitely-the-wrong-password" not in str(entry.changes)

    def test_a_manager_reading_somebody_elses_month_is_recorded(
        self, db, org, manager, manager_client, anna,
    ):
        manager_client.get(reverse("timesheets:employee", args=[anna.pk]))
        views = entries_for(action=AuditAction.VIEWED, employee=anna)
        assert views, "a manager opening somebody else's month is the entry a works council asks for"
        assert views[0].actor == manager.user

    def test_reading_your_own_month_is_not_recorded(self, db, org, anna, client):
        client.get(reverse("timesheets:mine"))
        assert not entries_for(action=AuditAction.VIEWED)

    def test_an_export_is_recorded(self, db, org, anna, client):
        response = client.get(reverse("timesheets:export", args=["csv"]))
        assert response.status_code == 200
        exports = entries_for(action=AuditAction.EXPORTED)
        assert len(exports) == 1
        assert exports[0].employee == anna


# --------------------------------------------------------------------------
# The pages
# --------------------------------------------------------------------------

class TestThePages:

    def test_an_employee_sees_their_own_history(self, db, org, anna, client):
        DayRecord.objects.create(employee=anna, date=dt.date(2025, 9, 1))
        response = client.get(reverse("audit:mine"))
        assert response.status_code == 200
        assert list(response.context["page"])

    def test_an_employee_cannot_see_somebody_elses(self, db, org, anna, client):
        other = anna.__class__.objects.create(first_name="Other", username="other.person")
        assert client.get(reverse("audit:employee", args=[other.pk])).status_code == 404

    def test_the_whole_log_is_staff_only(self, db, org, anna, client, manager_client):
        """Staff, not manager. `apps/accounts/permissions.py`: administering the
        *software* and administering the *people* are different rights, and this
        page carries sign-ins and the SSO configuration's history."""
        assert client.get(reverse("audit:log")).status_code == 404
        assert manager_client.get(reverse("audit:log")).status_code == 404

    def test_a_staff_account_sees_everything(self, db, org, anna, staff):
        from django.test import Client

        DayRecord.objects.create(employee=anna, date=dt.date(2025, 9, 1))
        session = Client()
        session.force_login(staff)
        response = session.get(reverse("audit:log"))
        assert response.status_code == 200
        assert list(response.context["page"])

    def test_a_filter_cannot_widen_what_the_door_allowed(self, db, org, anna, client):
        """``?employee=`` smuggled onto your own history changes nothing.

        The employee page filters on the employee *before* the request's own
        parameters are read, which is what makes this true by construction rather
        than by a check somebody has to remember.
        """
        other = anna.__class__.objects.create(first_name="Other", username="other.person")
        DayRecord.objects.create(employee=other, date=dt.date(2025, 9, 1))

        response = client.get(reverse("audit:mine"), {"employee": other.pk})
        assert all(entry.employee_id == anna.pk for entry in response.context["page"])


# --------------------------------------------------------------------------
# An absence, end to end
# --------------------------------------------------------------------------

def test_an_absence_decision_is_in_the_trail(db, org, anna, manager):
    """The kind of question the trail is opened for: who approved this, and when.

    ``Absence`` is on the signal list, so a decision is a diff on ``status`` with
    both values on it — which is what turns "it says approved" into "Ben approved
    it on the 4th, and before that it was waiting".
    """
    absence = Absence.objects.create(
        employee=anna, kind=AbsenceKind.HOLIDAY,
        start_date=dt.date(2025, 9, 8), end_date=dt.date(2025, 9, 12),
        status=RequestStatus.REQUESTED,
    )
    with acting_as(manager.user):
        absence.status = RequestStatus.APPROVED
        absence.save()

    entry = AuditEntry.objects.filter(
        subject="absences.Absence", action=AuditAction.CHANGED,
    ).first()
    assert entry.changes["status"] == ["requested", "approved"]
    assert entry.actor == manager.user
    assert entry.employee == anna


def test_a_segment_belongs_to_the_employee_whose_day_it_is(db, org, anna):
    """``WorkSegment`` reaches its employee through ``day``.

    Without that, every punch in the app would be filed under nobody — and "show
    me everything that ever touched this timesheet" is the query the whole table
    is indexed for.
    """
    record = DayRecord.objects.create(employee=anna, date=dt.date(2025, 9, 1))
    WorkSegment.objects.create(day=record, position=0, start=dt.time(8), end=dt.time(16))
    entry = AuditEntry.objects.filter(subject="timesheets.WorkSegment").first()
    assert entry.employee == anna
