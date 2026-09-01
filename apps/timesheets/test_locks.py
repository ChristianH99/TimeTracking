"""Closing a month, and what a closed day refuses.

The value here is concentrated in **the sweep**. A lock is only worth as much as
its least-guarded door, and the doors are many: two pop-ups, a comment box, the
old day form, two confirm buttons, Start and Stop, and every way an absence can
be written. A test that checked three of them would pass for as long as it took
somebody to add a fourth.

So ``TestNoDoorIsLeftOpen`` walks the write paths and asserts that none of them
changes a locked day, and ``DayRecord.save`` refuses one as a backstop — a view
that forgot the check would save in silence, and a lock one forgotten line can
be walked past is not a lock.
"""

import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from apps.absences.models import Absence, AbsenceKind, RequestStatus
from apps.roster.models import Shift
from apps.timesheets.models import DayLock, DayRecord, LockedDay, WorkSegment


@pytest.fixture
def september(anna):
    """The same month the rest of the timesheet tests use."""
    return dt.date(2025, 9, 1)


@pytest.fixture
def locked(anna, september, manager):
    """One locked day, closed by a manager."""
    DayLock.lock(anna, [september], by=manager.user)
    return september


def _day(employee, date, spans=(((8, 0), (17, 0)),)):
    record = DayRecord(employee=employee, date=date)
    record.save(force=True)
    for index, (start, end) in enumerate(spans):
        WorkSegment.objects.create(
            day=record, position=index, start=dt.time(*start), end=dt.time(*end),
        )
    record.refresh_from_db()
    return record


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

class TestTheLockItself:
    def test_a_month_is_locked_a_day_at_a_time(self, org, anna, manager, september):
        """A row per day and not a row per month, although a month is what is
        locked. Every question the app asks is about one date."""
        days = [september + dt.timedelta(days=n) for n in range(30)]
        assert DayLock.lock(anna, days, by=manager.user) == 30
        assert DayLock.dates_between(anna, september, days[-1]) == set(days)

    def test_locking_twice_changes_nothing_and_raises_nothing(
        self, org, anna, manager, september,
    ):
        """Two managers pressing the button in the same second is not an error,
        and the second press means the same as the first."""
        DayLock.lock(anna, [september], by=manager.user)
        assert DayLock.lock(anna, [september], by=manager.user) == 0
        assert DayLock.objects.filter(employee=anna, date=september).count() == 1

    def test_unlocking_is_deleting_the_row(self, org, anna, manager, locked):
        """There is no flag to go stale. A row exists or it does not."""
        DayLock.objects.filter(employee=anna, date=locked).delete()
        assert not DayLock.is_locked(anna, locked)

    def test_one_person_is_locked_and_not_another(self, org, anna, cem, manager, locked):
        assert DayLock.is_locked(anna, locked)
        assert not DayLock.is_locked(cem, locked)


class TestTheModelIsTheBackstop:
    """A view that forgot the check would save in silence."""

    def test_saving_a_locked_day_is_refused(self, org, anna, locked):
        with pytest.raises(LockedDay):
            DayRecord(employee=anna, date=locked).save()

    def test_deleting_a_locked_day_is_refused(self, org, anna, september, manager):
        record = _day(anna, september)
        DayLock.lock(anna, [september], by=manager.user)
        with pytest.raises(LockedDay):
            record.delete()
        assert DayRecord.objects.filter(pk=record.pk).exists()

    def test_force_is_for_callers_that_are_not_editing_a_day(self, org, anna, locked):
        """A fixture, a migration or a seeder is not somebody changing the
        record — and the lock being applied cannot be blocked by itself."""
        DayRecord(employee=anna, date=locked).save(force=True)
        assert DayRecord.objects.filter(employee=anna, date=locked).exists()

    def test_an_unlocked_day_saves_as_it_always_did(self, org, anna, september):
        DayRecord(employee=anna, date=september).save()
        assert DayRecord.objects.filter(employee=anna, date=september).exists()


# --------------------------------------------------------------------------
# The doors
# --------------------------------------------------------------------------

class TestNoDoorIsLeftOpen:
    """Every way a day can be changed, against a locked one.

    Written as a list of doors rather than as one test each, because what is
    being asserted is the same sentence about all of them — and because a door
    added next month is one line here rather than a test somebody forgets to
    write.
    """

    def test_the_bookings_pop_up_is_refused(self, org, anna, client, locked):
        key = locked.isoformat()
        response = client.post(f"/timesheet/save/{key}/", {
            f"time-{key}": ["08:00", "17:00"], f"kind-{key}": ["in", "out"],
        })
        assert response.status_code == 400
        assert not DayRecord.objects.filter(employee=anna).exists()

    def test_a_correction_is_refused(self, org, anna, client, locked):
        key = locked.isoformat()
        response = client.post(f"/timesheet/save/{key}/", {
            f"correction-{key}": "30", f"why-{key}": "forgot to book out",
        })
        assert response.status_code == 400
        assert not DayRecord.objects.filter(employee=anna).exists()

    def test_a_comment_is_refused(self, org, anna, client, locked):
        """Once the month is signed off the whole row is the record."""
        key = locked.isoformat()
        response = client.post(f"/timesheet/save/{key}/", {f"note-{key}": "spät"})
        assert response.status_code == 400
        assert not DayRecord.objects.filter(employee=anna).exists()

    def test_a_status_is_refused(self, org, anna, client, locked):
        response = client.post(f"/timesheet/status/{locked.isoformat()}/", {
            "kind": AbsenceKind.SICK,
        })
        assert response.status_code == 302
        assert not Absence.objects.filter(employee=anna).exists()

    def test_the_day_form_is_refused(self, org, anna, client, locked):
        response = client.post(f"/timesheet/{anna.pk}/{locked.isoformat()}/", {
            "segments-TOTAL_FORMS": "1", "segments-INITIAL_FORMS": "0",
            "segments-MIN_NUM_FORMS": "0", "segments-MAX_NUM_FORMS": "1000",
            "segments-0-start": "08:00", "segments-0-end": "17:00",
            "automatic_break": "on",
        })
        assert response.status_code == 302
        assert not DayRecord.objects.filter(employee=anna).exists()

    def test_confirming_as_rostered_is_refused(self, org, anna, client, locked):
        Shift.objects.create(
            employee=anna, date=locked, start=dt.time(8), end=dt.time(16),
        )
        response = client.post(f"/timesheet/{anna.pk}/{locked.isoformat()}/confirm/")
        assert response.status_code == 302
        assert not DayRecord.objects.filter(employee=anna).exists()

    def test_confirming_a_week_skips_the_locked_days(self, org, anna, client, manager):
        """Skipped rather than refused. This is a bulk gesture over a week that
        may be half closed, and refusing the whole thing because one day of it
        is locked would leave nothing to press."""
        monday = dt.date(2025, 9, 1)
        for offset in range(2):
            Shift.objects.create(
                employee=anna, date=monday + dt.timedelta(days=offset),
                start=dt.time(8), end=dt.time(16),
            )
        DayLock.lock(anna, [monday], by=manager.user)

        client.post("/timesheet/confirm-week/", {"week": monday.isoformat()})
        assert not DayRecord.objects.filter(employee=anna, date=monday).exists()
        assert DayRecord.objects.filter(
            employee=anna, date=monday + dt.timedelta(days=1),
        ).exists()

    def test_clocking_in_is_refused(self, org, anna, client, manager):
        """Rare — it means somebody closed the month that is still running — but
        Start writes a record like anything else."""
        DayLock.lock(anna, [dt.date.today()], by=manager.user)
        response = client.post(f"/timesheet/{anna.pk}/clock/")
        assert response.status_code == 302
        assert not WorkSegment.objects.filter(day__employee=anna).exists()

    def test_asking_for_time_off_across_it_is_refused(self, org, anna, client, locked):
        """The absences page has its own form, and a lock only the timesheet
        honoured would be one anybody could walk round by using the other."""
        response = client.post("/absences/request/", {
            "kind": AbsenceKind.HOLIDAY,
            "start_date": locked.isoformat(),
            "end_date": locked.isoformat(),
        })
        assert response.status_code == 200
        assert not Absence.objects.filter(employee=anna).exists()

    def test_reporting_sickness_across_it_is_refused(self, org, anna, client, locked):
        response = client.post("/absences/sick/", {
            "start_date": locked.isoformat(), "end_date": locked.isoformat(),
        })
        assert response.status_code == 302
        assert not Absence.objects.filter(employee=anna).exists()

    def test_a_range_that_only_touches_a_locked_day_is_refused(
        self, org, anna, client, locked,
    ):
        """Named in the message, because "part of that is locked" sends somebody
        hunting through a fortnight for the day that is."""
        response = client.post("/absences/request/", {
            "kind": AbsenceKind.HOLIDAY,
            "start_date": locked.isoformat(),
            "end_date": (locked + dt.timedelta(days=4)).isoformat(),
        })
        assert response.status_code == 200
        assert not Absence.objects.filter(employee=anna).exists()

    def test_a_manager_is_refused_as_well(self, org, anna, manager_client, locked):
        """A manager unlocks the day and then changes it. Letting them write
        straight through the lock would make the lock a suggestion, and there
        would be no record that the month had been reopened."""
        key = locked.isoformat()
        response = manager_client.post(f"/team/{anna.pk}/save/{key}/", {
            f"time-{key}": ["08:00", "17:00"], f"kind-{key}": ["in", "out"],
        })
        assert response.status_code == 400
        assert not DayRecord.objects.filter(employee=anna).exists()


class TestAnUnlockedDayIsOrdinaryAgain:
    def test_the_day_beside_it_was_never_locked(self, org, anna, client, locked):
        key = (locked + dt.timedelta(days=1)).isoformat()
        response = client.post(f"/timesheet/save/{key}/", {
            f"time-{key}": ["08:00", "17:00"], f"kind-{key}": ["in", "out"],
        })
        assert response.status_code == 200

    def test_unlocking_one_day_lets_it_be_changed(
        self, org, anna, client, manager_client, locked,
    ):
        key = locked.isoformat()
        assert manager_client.post(
            f"/team/{anna.pk}/lock/{key}/", {"unlock": "1"},
        ).status_code == 302

        response = client.post(f"/timesheet/save/{key}/", {
            f"time-{key}": ["08:00", "17:00"], f"kind-{key}": ["in", "out"],
        })
        assert response.status_code == 200
        assert DayRecord.objects.filter(employee=anna, date=locked).exists()

    def test_and_can_be_locked_again_afterwards(
        self, org, anna, client, manager_client, locked,
    ):
        """The whole shape of it: a month is closed in one gesture and opened one
        day at a time, because the reason to open one is always a single day
        that was wrong."""
        key = locked.isoformat()
        manager_client.post(f"/team/{anna.pk}/lock/{key}/", {"unlock": "1"})
        manager_client.post(f"/team/{anna.pk}/lock/{key}/", {})
        assert DayLock.is_locked(anna, locked)


# --------------------------------------------------------------------------
# The manager's page
# --------------------------------------------------------------------------

class TestClosingAMonth:
    def test_it_locks_every_day_of_the_month_for_everybody_ticked(
        self, org, anna, cem, manager_client, september,
    ):
        response = manager_client.post("/team/month-end/lock/", {
            "month": "2025-09", "employee": [anna.pk, cem.pk],
        })
        assert response.status_code == 302
        assert len(DayLock.dates_between(anna, september, dt.date(2025, 9, 30))) == 30
        assert len(DayLock.dates_between(cem, september, dt.date(2025, 9, 30))) == 30

    def test_somebody_not_ticked_is_not_locked(
        self, org, anna, cem, manager_client, september,
    ):
        manager_client.post("/team/month-end/lock/", {
            "month": "2025-09", "employee": [anna.pk],
        })
        assert DayLock.is_locked(anna, september)
        assert not DayLock.is_locked(cem, september)

    def test_it_refuses_while_something_is_waiting_for_a_decision(
        self, org, anna, manager_client, september,
    ):
        """Approving a request afterwards would change the credited hours of a
        month that had already been signed off without them — which is the one
        thing a lock is supposed to make impossible."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=september + dt.timedelta(days=8),
            end_date=september + dt.timedelta(days=9),
            status=RequestStatus.REQUESTED,
        )
        response = manager_client.post("/team/month-end/lock/", {
            "month": "2025-09", "employee": [anna.pk],
        })
        assert response.status_code == 302
        assert not DayLock.objects.filter(employee=anna).exists()

    def test_a_decided_request_does_not_stop_it(
        self, org, anna, manager_client, september,
    ):
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=september + dt.timedelta(days=8),
            end_date=september + dt.timedelta(days=9),
            status=RequestStatus.APPROVED,
        )
        manager_client.post("/team/month-end/lock/", {
            "month": "2025-09", "employee": [anna.pk],
        })
        assert DayLock.is_locked(anna, september)

    def test_unlocking_carries_no_conditions(
        self, org, anna, manager_client, september,
    ):
        """It is the escape hatch, and a condition on an escape hatch is how
        somebody ends up with a month they cannot correct."""
        manager_client.post("/team/month-end/lock/", {
            "month": "2025-09", "employee": [anna.pk],
        })
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.SICK,
            start_date=september, end_date=september,
            status=RequestStatus.REQUESTED,
        )
        manager_client.post("/team/month-end/lock/", {
            "month": "2025-09", "employee": [anna.pk], "unlock": "1",
        })
        assert not DayLock.objects.filter(employee=anna).exists()

    def test_it_only_touches_the_month_it_was_asked_about(
        self, org, anna, manager_client, september,
    ):
        manager_client.post("/team/month-end/lock/", {
            "month": "2025-09", "employee": [anna.pk],
        })
        assert not DayLock.is_locked(anna, dt.date(2025, 8, 31))
        assert not DayLock.is_locked(anna, dt.date(2025, 10, 1))

    def test_the_page_says_who_is_ready(self, org, anna, manager_client, september):
        response = manager_client.get("/team/month-end/?month=2025-09")
        assert response.status_code == 200
        row = next(r for r in response.context["people"] if r["employee"] == anna)
        assert row["is_locked"] is False
        assert row["total_days"] == 30

    def test_a_month_with_one_day_unlocked_reads_as_partly_locked(
        self, org, anna, manager_client, september,
    ):
        """A real third state. Saying "locked" would be a lie about the other
        twenty-nine days."""
        manager_client.post("/team/month-end/lock/", {
            "month": "2025-09", "employee": [anna.pk],
        })
        manager_client.post(f"/team/{anna.pk}/lock/{september.isoformat()}/", {"unlock": "1"})

        response = manager_client.get("/team/month-end/?month=2025-09")
        row = next(r for r in response.context["people"] if r["employee"] == anna)
        assert row["is_locked"] is False
        assert row["is_partly_locked"] is True
        assert row["locked_days"] == 29


class TestOnlyAManagerCloses:
    def test_an_employee_cannot_reach_the_page(self, org, anna, client):
        assert client.get("/team/month-end/").status_code == 404

    def test_an_employee_cannot_lock_a_month(self, org, anna, client, september):
        assert client.post("/team/month-end/lock/", {
            "month": "2025-09", "employee": [anna.pk],
        }).status_code == 404
        assert not DayLock.objects.exists()

    def test_an_employee_cannot_unlock_their_own_day(
        self, org, anna, client, locked,
    ):
        """The whole point. A lock somebody can take off their own hours is a
        lock that says nothing."""
        response = client.post(f"/team/{anna.pk}/lock/{locked.isoformat()}/", {"unlock": "1"})
        assert response.status_code == 404
        assert DayLock.is_locked(anna, locked)


# --------------------------------------------------------------------------
# What the page draws
# --------------------------------------------------------------------------

class TestThePageDrawsItShut:
    def test_a_locked_row_offers_nothing(self, org, anna, client, locked):
        page = client.get(f"/timesheet/?month=2025-09").content.decode()
        assert "is-locked" in page
        assert "disabled" in page

    def test_the_month_knows_how_much_of_it_is_closed(
        self, org, anna, client, manager_client, september,
    ):
        manager_client.post("/team/month-end/lock/", {
            "month": "2025-09", "employee": [anna.pk],
        })
        response = client.get("/timesheet/?month=2025-09")
        assert response.context["is_locked"] is True
        assert response.context["locked_days"] == 30

        manager_client.post(f"/team/{anna.pk}/lock/{september.isoformat()}/", {"unlock": "1"})
        response = client.get("/timesheet/?month=2025-09")
        assert response.context["is_locked"] is False
        assert response.context["has_locks"] is True
