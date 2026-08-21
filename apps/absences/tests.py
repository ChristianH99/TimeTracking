"""Absence: the day-counting rule, the German holidays, and the request flow.

The value is concentrated in ``working_days``. Every leave figure anybody ever
disputes comes out of it, and the three subtractions it makes — a day the
contract gives no hours, a public holiday, a date outside the employment — are
each invisible when wrong. A version that just subtracted two dates would be
right for a full-time employee taking a whole week and wrong for everybody else.
"""

import datetime as dt
from decimal import Decimal

import pytest

from apps.absences.bankholidays import easter_sunday, holidays, repentance_day
from apps.absences.models import (
    Absence, AbsenceKind, Balance, BankHoliday, CompanyClosure, RequestStatus,
)
from apps.organisation.models import Land


class TestWhatADayOffActuallyCosts:
    """The three subtractions, each on its own and then together."""

    def test_a_full_week_costs_a_full_timers_five_days(self, org, anna, monday):
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=6),
            status=RequestStatus.APPROVED,
        )
        assert absence.working_days() == 5

    def test_a_day_the_contract_gives_no_hours_costs_nothing(self, org, cem, monday):
        """Cem works Monday, Tuesday and Wednesday. Thursday and Friday off is
        not time off — he was not due in."""
        thursday = monday + dt.timedelta(days=3)
        absence = Absence.objects.create(
            employee=cem, kind=AbsenceKind.HOLIDAY,
            start_date=thursday, end_date=thursday + dt.timedelta(days=1),
            status=RequestStatus.APPROVED,
        )
        assert absence.working_days() == 0

    def test_a_part_timer_spends_only_their_own_days(self, org, cem, monday):
        absence = Absence.objects.create(
            employee=cem, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=6),
            status=RequestStatus.APPROVED,
        )
        assert absence.working_days() == 3

    def test_a_public_holiday_in_the_middle_is_not_charged(self, org, anna, monday):
        BankHoliday.objects.create(date=monday + dt.timedelta(days=2), name="Test")
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=4),
            status=RequestStatus.APPROVED,
        )
        assert absence.working_days() == 4

    def test_dates_before_they_started_are_not_charged(self, org, anna, monday):
        anna.started_on = monday + dt.timedelta(days=2)
        anna.save()
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=4),
            status=RequestStatus.APPROVED,
        )
        assert absence.working_days() == 3

    def test_both_ends_of_the_range_are_included(self, org, anna, monday):
        """"Off from the 3rd to the 7th" is five dates. A half-open range here
        would be an off-by-one waiting to be introduced by whoever writes the
        next page, so it is pinned."""
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.APPROVED,
        )
        assert absence.working_days() == 1


class TestWhatComesOffTheBalance:
    def test_sickness_costs_no_leave_but_still_has_a_length(self, org, anna, monday):
        """Two columns, not one. A sick absence is five working days long and
        costs nothing — a single figure would have to show it as nought, which
        reads as somebody having been ill for no days."""
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.SICK,
            start_date=monday, end_date=monday + dt.timedelta(days=4),
            status=RequestStatus.APPROVED,
        )
        assert absence.working_days() == 5
        assert absence.days_charged() == 0

    def test_a_request_still_waiting_is_not_spent(self, org, anna, monday):
        """The one that matters most to whoever is looking at their balance:
        somebody whose request is declined must not find they have already spent
        the days."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=4),
            status=RequestStatus.REQUESTED,
        )
        balance = Balance(anna, monday.year, org)
        assert balance.taken == 0
        assert balance.pending == 5
        assert balance.remaining == balance.entitlement
        assert balance.remaining_if_all_approved == balance.entitlement - 5

    def test_a_declined_request_gives_the_days_back(self, org, anna, monday):
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=4),
            status=RequestStatus.REQUESTED,
        )
        absence.decide(approved=False, by=anna.user, note="not that week")
        balance = Balance(anna, monday.year, org)
        assert balance.taken == 0 and balance.pending == 0

    def test_a_closure_comes_off_by_default(self, org, anna, monday):
        closure = CompanyClosure.objects.create(
            name="Betriebsferien", start_date=monday,
            end_date=monday + dt.timedelta(days=4),
        )
        closure.apply()
        balance = Balance(anna, monday.year, org)
        assert balance.taken == 5

    def test_a_closure_the_employer_pays_for_does_not(self, org, anna, monday):
        closure = CompanyClosure.objects.create(
            name="Brückentag", start_date=monday, end_date=monday,
            deducts_leave=False,
        )
        closure.apply()
        assert Balance(anna, monday.year, org).taken == 0

    def test_applying_a_closure_twice_does_not_charge_it_twice(self, org, anna, monday):
        closure = CompanyClosure.objects.create(
            name="Betriebsferien", start_date=monday,
            end_date=monday + dt.timedelta(days=4),
        )
        closure.apply()
        closure.apply()
        assert anna.absences.filter(kind=AbsenceKind.CLOSURE).count() == 1
        assert Balance(anna, monday.year, org).taken == 5

    def test_moving_a_closure_moves_the_absence_rather_than_adding_one(self, org, anna, monday):
        closure = CompanyClosure.objects.create(
            name="Betriebsferien", start_date=monday, end_date=monday,
        )
        closure.apply()
        closure.start_date = monday + dt.timedelta(days=7)
        closure.end_date = monday + dt.timedelta(days=7)
        closure.save()
        closure.apply()
        rows = list(anna.absences.filter(kind=AbsenceKind.CLOSURE))
        assert len(rows) == 1
        assert rows[0].start_date == monday + dt.timedelta(days=7)

    def test_special_leave_is_counted_against_its_own_type(self, org, anna, monday):
        from apps.employees.models import SpecialLeaveGrant
        from apps.organisation.models import AssignmentMode, SpecialLeaveType

        training = SpecialLeaveType.objects.create(
            name="Fortbildung", mode=AssignmentMode.FIXED, days=Decimal("2.0"),
        )
        SpecialLeaveGrant.objects.create(employee=anna, leave_type=training)
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.SPECIAL, special_type=training,
            start_date=monday, end_date=monday,
            status=RequestStatus.APPROVED,
        )
        balance = Balance(anna, monday.year, org)
        # Not off the annual entitlement — that is the whole point of a named
        # type, and folding it in would make both figures wrong at once.
        assert balance.taken == 0
        grant, entitled, taken, left = balance.special()[0]
        assert entitled == Decimal("2.0") and taken == 1 and left == Decimal("1.0")


class TestTheGermanPublicHolidays:
    @pytest.mark.parametrize("year, expected", [
        (2024, dt.date(2024, 3, 31)),
        (2025, dt.date(2025, 4, 20)),
        (2026, dt.date(2026, 4, 5)),
        (2027, dt.date(2027, 3, 28)),
        (2030, dt.date(2030, 4, 21)),
    ])
    def test_easter_is_right_for_known_years(self, year, expected):
        """Four of the thirteen holidays are offsets from this date, so getting
        it wrong moves a quarter of the year at once. Named dates rather than
        "returns a Sunday", which every wrong answer also does."""
        assert easter_sunday(year) == expected

    @pytest.mark.parametrize("year, expected", [
        (2024, dt.date(2024, 11, 20)),
        (2025, dt.date(2025, 11, 19)),
        (2026, dt.date(2026, 11, 18)),
    ])
    def test_repentance_day_is_the_wednesday_before_the_23rd(self, year, expected):
        assert repentance_day(year) == expected
        assert expected.weekday() == 2

    def test_the_nine_nationwide_days_are_everywhere(self):
        nationwide = {
            "Neujahr", "Karfreitag", "Ostermontag", "Tag der Arbeit",
            "Christi Himmelfahrt", "Pfingstmontag", "Tag der Deutschen Einheit",
            "1. Weihnachtstag", "2. Weihnachtstag",
        }
        for land in Land:
            names = {name for _date, name in holidays(2026, land)}
            assert nationwide <= names, f"{land} is missing {nationwide - names}"

    def test_the_regional_days_are_only_where_they_belong(self):
        """The failure this catches is an app that hands everybody in Hamburg
        three Bavarian holidays — which shows up as somebody marked absent on a
        day they were expected at work."""
        bavaria = {name for _d, name in holidays(2026, Land.BY)}
        hamburg = {name for _d, name in holidays(2026, Land.HH)}
        saxony = {name for _d, name in holidays(2026, Land.SN)}

        assert "Fronleichnam" in bavaria and "Fronleichnam" not in hamburg
        assert "Allerheiligen" in bavaria and "Allerheiligen" not in hamburg
        assert "Reformationstag" in hamburg and "Reformationstag" not in bavaria
        assert "Buß- und Bettag" in saxony and "Buß- und Bettag" not in bavaria
        assert "Mariä Himmelfahrt" in {name for _d, name in holidays(2026, Land.SL)}

    def test_brandenburg_gets_the_two_sundays(self):
        """The only Land where the two Sundays are themselves public holidays.
        It changes nothing for a Monday-to-Friday business and everything for
        one that opens at the weekend."""
        names = {name for _d, name in holidays(2026, Land.BB)}
        assert {"Ostersonntag", "Pfingstsonntag"} <= names

    def test_generating_replaces_its_own_rows_and_spares_hand_added_ones(self, db):
        """The whole reason ``is_generated`` exists. Fronleichnam is decided
        municipally in parts of Saxony, so an administrator has to be able to
        add it — and regenerating the year must not silently undo that."""
        BankHoliday.generate(2026, Land.HH)
        BankHoliday.objects.create(
            date=dt.date(2026, 6, 4), name="Fronleichnam (Gemeinde)", is_generated=False,
        )
        added, removed = BankHoliday.generate(2026, Land.HH)

        assert removed > 0
        names = set(BankHoliday.objects.filter(date__year=2026).values_list("name", flat=True))
        assert "Fronleichnam (Gemeinde)" in names
        assert BankHoliday.objects.filter(date__year=2026).count() == added + 1

    def test_a_hand_added_row_wins_the_date(self, db):
        """An administrator who has already answered for a date has answered for
        it. Writing the generated row over the top would replace their name with
        ours and look like the edit had not saved."""
        BankHoliday.objects.create(
            date=dt.date(2026, 1, 1), name="Neujahr (unser Name)", is_generated=False,
        )
        BankHoliday.generate(2026, Land.HH)
        row = BankHoliday.objects.get(date=dt.date(2026, 1, 1))
        assert row.name == "Neujahr (unser Name)"


class TestTheRequestFlow:
    def test_an_employee_asks_and_it_waits(self, org, anna, client, monday):
        response = client.post("/absences/request/", {
            "kind": AbsenceKind.HOLIDAY,
            "start_date": (monday + dt.timedelta(days=30)).isoformat(),
            "end_date": (monday + dt.timedelta(days=32)).isoformat(),
            "reason": "",
        })
        assert response.status_code == 302
        absence = anna.absences.get()
        assert absence.status == RequestStatus.REQUESTED

    def test_a_request_worth_no_days_is_refused_with_a_reason(self, org, cem, monday):
        """Cem does not work Thursdays or Fridays. A request worth nothing is
        one a manager has to read, decide and explain — refusing it here says
        the useful thing instead."""
        from apps.absences.forms import AbsenceRequestForm

        form = AbsenceRequestForm(data={
            "kind": AbsenceKind.HOLIDAY,
            "start_date": (monday + dt.timedelta(days=3)).isoformat(),
            "end_date": (monday + dt.timedelta(days=4)).isoformat(),
        }, employee=cem)
        assert not form.is_valid()
        assert "not due to work" in str(form.errors)

    def test_overlapping_time_off_is_refused(self, org, anna, monday):
        from apps.absences.forms import AbsenceRequestForm

        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=4),
            status=RequestStatus.APPROVED,
        )
        form = AbsenceRequestForm(data={
            "kind": AbsenceKind.HOLIDAY,
            "start_date": (monday + dt.timedelta(days=2)).isoformat(),
            "end_date": (monday + dt.timedelta(days=6)).isoformat(),
        }, employee=anna)
        assert not form.is_valid()
        assert "overlap" in str(form.errors)

    def test_a_declined_request_does_not_block_the_dates(self, org, anna, monday):
        """It is history, not a claim on the calendar. Counting it would leave
        somebody unable to re-ask for the week they were refused."""
        from apps.absences.forms import AbsenceRequestForm

        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=4),
            status=RequestStatus.REJECTED,
        )
        form = AbsenceRequestForm(data={
            "kind": AbsenceKind.HOLIDAY,
            "start_date": monday.isoformat(),
            "end_date": (monday + dt.timedelta(days=4)).isoformat(),
        }, employee=anna)
        assert form.is_valid(), form.errors

    def test_sickness_counts_before_anybody_acknowledges_it(self, org, anna, client, monday):
        """The acknowledgement is a receipt, not a permission.

        A manager confirms that a report reached them, and that is worth
        recording. What must never happen is the *counting* waiting on it: an
        employee off with flu for a fortnight while their manager is away would
        otherwise show eighty hours of shortfall, which is a debt §3 EFZG says
        outright they do not owe. So the row waits on the manager's list and the
        absence itself takes effect immediately.
        """
        client.post("/absences/sick/", {"start_date": monday.isoformat(), "end_date": ""})
        absence = anna.absences.get()
        assert absence.kind == AbsenceKind.SICK
        assert absence.status == RequestStatus.REQUESTED
        assert absence.credits_hours, "a reported sick day counts from the moment it is reported"
        assert not absence.costs_leave, "sickness never comes off the leave balance"

    def test_only_a_refusal_stops_a_sick_day_counting(self, org, anna, client, monday):
        """The one act that withholds the credit, and it is a positive one.

        An employer disputing an absence — no Krankmeldung arrived, the dates
        are wrong — is real and rare. It is not the same state as a report
        nobody has looked at yet, and the two must not be one status.
        """
        client.post("/absences/sick/", {"start_date": monday.isoformat(), "end_date": ""})
        absence = anna.absences.get()

        absence.status = RequestStatus.REJECTED
        assert not absence.credits_hours
        # Blank end means today, not null: on the morning somebody rings in
        # nobody knows when it ends.
        assert absence.end_date == absence.start_date

    def test_declining_without_a_reason_is_refused(self, org, anna, manager_client, monday):
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.REQUESTED,
        )
        manager_client.post(f"/absences/requests/{absence.pk}/decide/", {"note": ""})
        absence.refresh_from_db()
        assert absence.status == RequestStatus.REQUESTED

    def test_a_decision_records_who_made_it(self, org, anna, manager, manager_client, monday):
        """The question asked months later when a balance is disputed, and it is
        unanswerable from a status column alone."""
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.REQUESTED,
        )
        manager_client.post(f"/absences/requests/{absence.pk}/decide/",
                            {"approve": "1", "note": ""})
        absence.refresh_from_db()
        assert absence.status == RequestStatus.APPROVED
        assert absence.decided_by == manager.user
        assert absence.decided_at is not None

    def test_an_ordinary_employee_cannot_decide_anything(self, org, anna, client, monday):
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.REQUESTED,
        )
        response = client.post(f"/absences/requests/{absence.pk}/decide/",
                               {"approve": "1", "note": ""})
        assert response.status_code == 404
        absence.refresh_from_db()
        assert absence.status == RequestStatus.REQUESTED

    def test_withdrawing_keeps_the_row(self, org, anna, client, monday):
        """Withdrawn rather than deleted, so the record still says the
        conversation happened."""
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday + dt.timedelta(days=30),
            end_date=monday + dt.timedelta(days=31),
            status=RequestStatus.REQUESTED,
        )
        client.post(f"/absences/request/{absence.pk}/withdraw/")
        absence.refresh_from_db()
        assert absence.status == RequestStatus.WITHDRAWN
