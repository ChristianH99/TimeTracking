"""The retention policy: what goes, what may not go, and what goes last.

Four of these matter more than the rest.

``TestTheCalendarYearRule`` pins §147(4) AO. Every German retention period runs
from the *end of the calendar year* in which the record arose, and the obvious
implementation — subtract N years from today — deletes up to eleven months early.
Early is the direction that loses evidence rather than the one that loses an
argument, which is why it has a class rather than a case.

``TestTheFloorCannotBeCrossed`` is the half of a retention policy nobody builds.
An app that only deletes is an app that destroys records its employer is required
to produce, and the setting that would do it looks like tidying up.

``TestTheSweepDoesNotAuditItself`` is the bug that would have made the first real
run unusable: a per-row entry means a sweep that grows the table it is shrinking,
with rows describing records that no longer exist.

``TestAPersonIsErasedLast`` is the DSGVO answer to a problem this codebase made
for itself. A name frozen into an append-only table cannot be edited out, so the
only lawful order is: records, then trail, then person.
"""

import datetime as dt

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.absences.carryover import LeaveCarryOver
from apps.absences.models import Absence, AbsenceKind, RequestStatus
from apps.audit import retention
from apps.audit.models import AuditAction, AuditEntry, AuditImmutable
from apps.employees.models import Employee
from apps.organisation.models import OrgSettings
from apps.roster.models import Shift
from apps.timesheets.models import DayLock, DayRecord, WorkSegment


@pytest.fixture
def policy(org):
    """Settings with every period at its default."""
    org.save()
    return org


def _day(employee, date, spans=((8, 16),)):
    record = DayRecord.objects.create(employee=employee, date=date)
    for index, (start, end) in enumerate(spans):
        WorkSegment.objects.create(
            day=record, position=index, start=dt.time(start), end=dt.time(end),
        )
    return record


# --------------------------------------------------------------------------
# §147(4) AO
# --------------------------------------------------------------------------

class TestTheCalendarYearRule:
    """The period begins at the end of the calendar year, not on the record's
    own date."""

    def test_a_record_lives_to_the_end_of_its_last_year(self):
        # Two years, a record from March 2024. It is kept through all of 2025 and
        # all of 2026, and goes on 1 January 2027.
        assert retention.cutoff_for(2, dt.date(2026, 12, 31)) == dt.date(2024, 1, 1)
        assert retention.cutoff_for(2, dt.date(2027, 1, 1)) == dt.date(2025, 1, 1)

    def test_the_naive_subtraction_would_delete_it_early(self):
        """The assertion that says why this function exists.

        ``today - 2 years`` on 15 June 2026 is 15 June 2024, which would take a
        record from March 2024 — six months before its period is up.
        """
        march = dt.date(2024, 3, 15)
        today = dt.date(2026, 6, 15)
        naive = today.replace(year=today.year - 2)
        assert march < naive, "the naive cutoff would have caught it"
        assert march >= retention.cutoff_for(2, today), "the calendar-year rule keeps it"

    def test_a_day_inside_its_period_is_not_due(self, anna, policy):
        _day(anna, dt.date(2026, 3, 2))
        rows = {row["key"]: row for row in retention.survey(policy, today=dt.date(2027, 6, 1))}
        assert rows["working_time"]["due"] == 0

    def test_a_day_past_its_period_is_due(self, anna, policy):
        policy.keep_working_time_years = 2
        policy.save()
        _day(anna, dt.date(2024, 3, 2))
        rows = {row["key"]: row for row in retention.survey(policy, today=dt.date(2027, 1, 2))}
        assert rows["working_time"]["due"] == 1


# --------------------------------------------------------------------------
# The half nobody builds
# --------------------------------------------------------------------------

class TestTheFloorCannotBeCrossed:

    def test_a_period_below_the_statutory_minimum_is_raised(self, policy):
        """Not obeyed, and not silently: the page says it was raised.

        Clamped in the module as well as refused on the form, because a row
        written by a data migration or by hand must not be able to shorten a
        statutory period just by being loaded.
        """
        policy.keep_working_time_years = 1  # below §16 ArbZG's two
        entry = retention.BY_KEY["working_time"]
        assert retention.years_for(policy, entry) == retention.FLOOR_WORKING_TIME

    def test_the_form_refuses_rather_than_quietly_raising(self, db, policy):
        """A settings page that takes a figure and ignores it is the control
        that does nothing, which is the one people report as broken."""
        from apps.organisation.forms import RetentionForm

        form = RetentionForm({
            "keep_working_time_years": 1, "keep_absences_years": 10,
            "keep_roster_years": 2, "keep_audit_years": 10,
            "keep_security_log_years": 1,
        }, instance=policy)
        assert not form.is_valid()
        assert "keep_working_time_years" in form.errors

    def test_the_survey_says_when_it_raised_a_figure(self, policy):
        policy.keep_working_time_years = 1
        rows = {row["key"]: row for row in retention.survey(policy)}
        assert rows["working_time"]["raised_to_floor"]
        assert rows["working_time"]["years"] == retention.FLOOR_WORKING_TIME

    def test_the_sweep_cannot_reach_inside_a_floor(self, anna, policy):
        """Even asked for one year, two years of days survive."""
        policy.keep_working_time_years = 1
        policy.save()
        _day(anna, dt.date(2025, 6, 2))
        retention.sweep(policy, today=dt.date(2027, 1, 2), dry_run=False)
        assert DayRecord.objects.filter(date=dt.date(2025, 6, 2)).exists()


# --------------------------------------------------------------------------
# The audit trail's own period
# --------------------------------------------------------------------------

class TestTheTrailOutlivesWhatItExplains:

    def test_its_floor_is_the_longest_record_period(self, policy):
        policy.keep_working_time_years = 12
        policy.keep_absences_years = 6
        policy.keep_roster_years = 2
        assert retention.audit_floor(policy) == 12

    def test_a_shorter_setting_is_raised_to_it(self, policy):
        policy.keep_working_time_years = 12
        policy.keep_audit_years = 3
        entry = retention.BY_KEY["audit"]
        assert retention.years_for(policy, entry) == 12

    def test_the_security_log_does_not_drag_the_floor_down(self, policy):
        """`RECORD_CLASSES` names three, not "everything but the trail".

        The sign-in log is kept for a year on purpose; if it counted towards the
        floor it would be the *minimum* of nothing and the trail would be free to
        expire before the timesheets it explains.
        """
        policy.keep_security_log_years = 1
        policy.keep_working_time_years = 10
        assert retention.audit_floor(policy) == 10

    def test_the_form_refuses_a_trail_shorter_than_its_records(self, db, policy):
        from apps.organisation.forms import RetentionForm

        form = RetentionForm({
            "keep_working_time_years": 10, "keep_absences_years": 10,
            "keep_roster_years": 2, "keep_audit_years": 4,
            "keep_security_log_years": 1,
        }, instance=policy)
        assert not form.is_valid()
        assert "keep_audit_years" in form.errors


# --------------------------------------------------------------------------
# One table, two policies
# --------------------------------------------------------------------------

class TestSignInsGoSoonerThanRecords:

    def test_a_sign_in_is_swept_on_the_shorter_period(self, anna, policy, db):
        old = dt.datetime(2020, 5, 1, 9, 0, tzinfo=dt.timezone.utc)
        signin = AuditEntry.objects.create(action=AuditAction.SIGNED_IN, note="anna")
        change = AuditEntry.objects.create(
            action=AuditAction.CHANGED, employee=anna, subject="timesheets.DayRecord",
        )
        AuditEntry.objects.filter(pk__in=[signin.pk, change.pk]).update(at=old)

        retention.sweep(policy, today=dt.date(2026, 1, 2), dry_run=False)

        assert not AuditEntry.objects.filter(pk=signin.pk).exists(), (
            "a sign-in from 2020 is well past the one-year period"
        )
        assert AuditEntry.objects.filter(pk=change.pk).exists(), (
            "a record entry from 2020 is inside the ten-year period"
        )


# --------------------------------------------------------------------------
# The one door out of an append-only table
# --------------------------------------------------------------------------

class TestNothingElseCanEmptyTheTrail:

    def test_a_queryset_delete_is_refused(self, db):
        """``Model.delete`` alone was not enough, and this is the gap it left.

        A queryset delete never calls it, so ``AuditEntry.objects.all().delete()``
        would have emptied the table with the guard three lines away looking like
        it was doing something.
        """
        AuditEntry.objects.create(action=AuditAction.CREATED)
        with pytest.raises(AuditImmutable):
            AuditEntry.objects.all().delete()
        assert AuditEntry.objects.exists()

    def test_purge_is_the_way_past_it(self, db):
        AuditEntry.objects.create(action=AuditAction.CREATED)
        AuditEntry.objects.all().purge()
        assert not AuditEntry.objects.exists()

    def test_a_single_entry_still_cannot_be_deleted(self, db):
        """There is no case for removing one, and the case that looks like one —
        "this entry is wrong" — is what the table exists to refuse."""
        entry = AuditEntry.objects.create(action=AuditAction.CREATED)
        with pytest.raises(AuditImmutable):
            entry.delete()


# --------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------

class TestTheSweepDoesNotAuditItself:

    def test_it_writes_one_entry_per_class_and_not_one_per_row(self, anna, policy):
        policy.keep_working_time_years = 2
        policy.save()
        for day in range(1, 11):
            _day(anna, dt.date(2024, 3, day))
        AuditEntry.objects.all().purge()

        retention.sweep(policy, today=dt.date(2027, 1, 2), dry_run=False)

        entries = list(AuditEntry.objects.all())
        assert len(entries) == 1, (
            "ten days went; a per-row trail would be a sweep that grows the table "
            f"it is shrinking. Got: {[e.action for e in entries]}"
        )
        assert entries[0].action == AuditAction.PURGED
        assert "01.01.2025" in entries[0].note

    def test_deleting_a_day_by_hand_is_still_audited(self, anna, policy):
        """The suppression is scoped to the sweep and nothing else."""
        record = _day(anna, dt.date(2026, 3, 2))
        AuditEntry.objects.all().purge()
        record.delete()
        assert AuditEntry.objects.filter(action=AuditAction.DELETED).exists()


class TestADryRunIsTheDefault:

    def test_sweep_deletes_nothing_unless_told(self, anna, policy):
        policy.keep_working_time_years = 2
        policy.save()
        _day(anna, dt.date(2024, 3, 2))
        rows = retention.sweep(policy, today=dt.date(2027, 1, 2))
        assert DayRecord.objects.count() == 1
        assert sum(row["total"] for row in rows) == 1

    def test_the_command_reports_without_deleting(self, anna, policy):
        policy.keep_working_time_years = 2
        policy.save()
        _day(anna, dt.date(2024, 3, 2))
        call_command("apply_retention")
        assert DayRecord.objects.count() == 1

    def test_the_command_deletes_when_told_twice(self, anna, policy):
        # The command has no "pretend it is 2027" argument and should not: it is
        # the one thing in the app that destroys records, and a flag that moved
        # its idea of today would be a flag that deleted a year early. So the
        # date is derived from the policy instead — one day before the real
        # cutoff, which is out of period today and stays out.
        policy.keep_working_time_years = 2
        policy.save()
        gone = retention.cutoff_for(2) - dt.timedelta(days=1)
        _day(anna, gone)
        call_command("apply_retention", "--apply")
        assert DayRecord.objects.count() == 0


class TestWhatEachClassCovers:

    def test_a_days_punches_go_with_it_and_not_on_their_own(self, anna, policy):
        """``WorkSegment`` is deliberately not in the matcher: it cascades.

        Listing it would delete punches whose day is still inside its period the
        moment somebody got a filter wrong — a timesheet with its hours silently
        removed and its rows still there.
        """
        policy.keep_working_time_years = 2
        policy.save()
        _day(anna, dt.date(2024, 3, 2))
        kept = _day(anna, dt.date(2026, 3, 2))
        retention.sweep(policy, today=dt.date(2027, 1, 2), dry_run=False)
        assert WorkSegment.objects.filter(day=kept).count() == 1
        assert WorkSegment.objects.count() == 1

    def test_an_absence_is_anchored_on_its_end(self, anna, policy):
        """A fortnight beginning in December ends in January, and the period runs
        from the later one."""
        policy.keep_absences_years = 3
        policy.save()
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=dt.date(2023, 12, 27), end_date=dt.date(2024, 1, 5),
            status=RequestStatus.APPROVED,
        )
        # Cutoff on 2 Jan 2027 with three years is 1 Jan 2024. The absence ends on
        # the 5th, so it stays — although it *started* before the cutoff.
        rows = {row["key"]: row for row in retention.survey(policy, today=dt.date(2027, 1, 2))}
        assert rows["absences"]["due"] == 0

    def test_carried_leave_is_anchored_on_its_year(self, anna, policy):
        policy.keep_absences_years = 3
        policy.save()
        LeaveCarryOver.objects.create(employee=anna, year=2020, statutory_days=4)
        rows = {row["key"]: row for row in retention.survey(policy, today=dt.date(2027, 1, 2))}
        assert rows["absences"]["due"] == 1

    def test_the_roster_goes_sooner_than_the_timesheet(self, anna, policy):
        """It is a plan, and no statute requires keeping one."""
        Shift.objects.create(
            employee=anna, date=dt.date(2023, 3, 2),
            start=dt.time(8), end=dt.time(16),
        )
        _day(anna, dt.date(2023, 3, 2))
        retention.sweep(policy, today=dt.date(2027, 1, 2), dry_run=False)
        assert not Shift.objects.exists()
        assert DayRecord.objects.exists(), "ten years for a timesheet, two for a plan"


# --------------------------------------------------------------------------
# The DSGVO answer
# --------------------------------------------------------------------------

class TestAPersonIsErasedLast:
    """A name frozen into an append-only table cannot be edited out.

    ``AuditEntry.employee_label`` exists so that deleting an account does not make
    every entry say *nobody did this*. That text is personal data, and the only
    lawful way to remove it is for the entry to expire — so the person goes after
    everything about them has, and the longest period is what decides when.
    """

    def test_somebody_with_records_left_is_not_erased(self, anna, policy):
        anna.ended_on = dt.date(2020, 1, 31)
        anna.save()
        _day(anna, dt.date(2019, 6, 3))
        assert not retention.erasable_people().filter(pk=anna.pk).exists()

    def test_somebody_with_an_audit_entry_left_is_not_erased(self, anna, policy):
        anna.ended_on = dt.date(2020, 1, 31)
        anna.save()
        AuditEntry.objects.create(
            action=AuditAction.CHANGED, employee=anna, employee_label=anna.full_name,
        )
        assert not retention.erasable_people().filter(pk=anna.pk).exists()

    def test_a_contract_is_part_of_the_person_and_goes_with_them(self, anna, policy):
        """``ContractPeriod`` has no period of its own, deliberately.

        It is not an independent record with a statute behind it — it *is* the
        person, and it cascades. Giving it a class of its own would let somebody
        delete a contract history while the timesheet computed against it was
        still held, which is a month that no longer reproduces.
        """
        from apps.employees.models import ContractPeriod

        anna.ended_on = dt.date(2020, 1, 31)
        anna.save()
        AuditEntry.objects.all().purge()
        assert ContractPeriod.objects.filter(employee=anna).exists()

        retention.sweep(policy, dry_run=False)
        assert not ContractPeriod.objects.filter(employee_id=anna.pk).exists()

    def test_somebody_still_employed_is_never_erased(self, anna, policy):
        AuditEntry.objects.all().purge()
        assert anna.ended_on is None
        assert not retention.erasable_people().filter(pk=anna.pk).exists()

    def test_somebody_with_nothing_left_is_erased(self, anna, policy):
        anna.ended_on = dt.date(2020, 1, 31)
        anna.save()
        AuditEntry.objects.all().purge()

        assert retention.erasable_people().filter(pk=anna.pk).exists()
        retention.sweep(policy, dry_run=False)
        assert not Employee.objects.filter(pk=anna.pk).exists()

    def test_the_name_goes_with_the_entries_and_not_before(self, anna, policy):
        """The whole shape of the rule, in one case.

        While an entry survives, the name is still in the database — and that is
        correct: the trail is the record of what happened and it may not be
        rewritten. Once the trail has expired there is nothing left carrying the
        name, and the person can go.
        """
        anna.ended_on = dt.date(2015, 1, 31)
        anna.save()
        # Cleared *after* the save, because setting `ended_on` is itself an
        # audited change — and one entry dated today would keep her in the
        # database for ten years and make this test about the wrong thing.
        AuditEntry.objects.all().purge()

        old = dt.datetime(2015, 5, 1, 9, 0, tzinfo=dt.timezone.utc)
        entry = AuditEntry.objects.create(
            action=AuditAction.CHANGED, employee=anna, employee_label=anna.full_name,
        )
        AuditEntry.objects.filter(pk=entry.pk).update(at=old)

        # Still there: the entry is inside its period, so the name is too.
        assert not retention.erasable_people().filter(pk=anna.pk).exists()

        # Once the trail's period has run, both go — in that order, in one sweep.
        retention.sweep(policy, today=dt.date(2030, 1, 2), dry_run=False)
        assert not AuditEntry.objects.filter(pk=entry.pk).exists()
        assert not Employee.objects.filter(pk=anna.pk).exists()


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------

class TestThePage:

    def test_it_is_staff_only(self, db, org, anna, client, manager_client):
        """Staff, not manager. Deciding how long the business keeps records is
        administering the *software*, not the people."""
        assert client.get(reverse("organisation:retention")).status_code == 404
        assert manager_client.get(reverse("organisation:retention")).status_code == 404

    def test_a_staff_account_sees_every_class(self, db, org, staff):
        from django.test import Client

        session = Client()
        session.force_login(staff)
        response = session.get(reverse("organisation:retention"))
        assert response.status_code == 200
        keys = {row["key"] for row in response.context["rows"]}
        assert keys == {
            "working_time", "absences", "roster", "audit", "security_log", "people",
        }

    def test_nothing_on_the_page_deletes_anything(self, db, org, staff, anna):
        """The page saves periods and never sweeps. A button that removes ten
        years of somebody's timesheet does not belong beside a Save."""
        from django.test import Client

        org.keep_working_time_years = 2
        org.save()
        _day(anna, dt.date(2010, 3, 2))
        session = Client()
        session.force_login(staff)
        session.post(reverse("organisation:retention"), {
            "keep_working_time_years": 2, "keep_absences_years": 3,
            "keep_roster_years": 2, "keep_audit_years": 3,
            "keep_security_log_years": 1,
        })
        assert DayRecord.objects.filter(date=dt.date(2010, 3, 2)).exists()


def test_every_class_names_a_setting_that_exists(policy):
    """A renamed field must fail here rather than quietly making a class
    unbounded — ``getattr(…, 0)`` would otherwise read as "keep nothing"."""
    for entry in retention.CLASSES:
        assert hasattr(OrgSettings, entry.setting), entry.setting
        assert isinstance(getattr(policy, entry.setting), int)
