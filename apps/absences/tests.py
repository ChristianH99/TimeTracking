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
        response = client.post("/absences/book/", {
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

    def test_sickness_is_asked_for_and_credits_nothing_until_it_is_decided(
        self, org, anna, client, monday,
    ):
        """**Sickness behaves like every other absence**, and this is the test
        that says so.

        It used to be the exception: reported rather than requested, credited
        the moment it was entered, and stopped only by a positive refusal. One
        kind behaving unlike the rest meant the timesheet had to say two
        different things about what a waiting day was worth. The one difference
        that survives is the only one that was ever about sickness itself — it
        costs no leave.
        """
        client.post("/absences/book/", {
            "kind": AbsenceKind.SICK,
            "start_date": monday.isoformat(), "end_date": monday.isoformat(),
        })
        absence = anna.absences.get()
        assert absence.kind == AbsenceKind.SICK
        assert absence.status == RequestStatus.REQUESTED
        assert not absence.credits_hours, "nothing is credited before it is approved"
        assert not absence.costs_leave, "sickness never comes off the leave balance"

        absence.status = RequestStatus.APPROVED
        assert absence.credits_hours
        assert not absence.costs_leave, "and still does not, once approved"

    def test_an_end_date_is_required_for_sickness(self, org, anna, client, monday):
        """It used to be optional — blank meant "today, and I will say later",
        which is the honest state on the morning somebody rings in and is also
        what made an open-ended absence possible. Somebody who does not know yet
        books the days they know about."""
        client.post("/absences/book/", {
            "kind": AbsenceKind.SICK,"start_date": monday.isoformat(), "end_date": ""})
        assert not anna.absences.exists()

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

    # -- taking back what has already been approved ------------------------
    #
    # The line is approval, and it is the same line for every kind. Nothing a
    # manager has not answered is theirs yet; something they have approved is a
    # day the roster was built around and the leave already spent against.

    @pytest.mark.parametrize("kind", [AbsenceKind.HOLIDAY, AbsenceKind.SICK])
    def test_an_approved_absence_is_asked_about_rather_than_withdrawn(
        self, org, anna, client, monday, kind,
    ):
        """And **it stays in force while the asking waits.** A cancellation that
        took effect on the press would move the balance and the credited hours
        before anybody had answered — which is the same fault as spending
        pending days, in the other direction."""
        absence = Absence.objects.create(
            employee=anna, kind=kind,
            start_date=monday, end_date=monday,
            status=RequestStatus.APPROVED,
        )
        client.post(f"/absences/request/{absence.pk}/withdraw/")
        absence.refresh_from_db()
        assert absence.status == RequestStatus.CANCELLING
        assert absence.credits_hours, "still booked until the manager answers"
        assert absence.is_decidable, "and on their list until they do"

    def test_a_manager_agreeing_takes_it_off(self, org, anna, manager, manager_client, monday):
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.CANCELLING,
        )
        manager_client.post(f"/absences/requests/{absence.pk}/decide/",
                            {"approve": "1", "note": ""})
        absence.refresh_from_db()
        assert absence.status == RequestStatus.WITHDRAWN
        assert absence.decided_by == manager.user

    def test_a_manager_refusing_leaves_it_exactly_as_it_was(
        self, org, anna, manager_client, monday,
    ):
        """Refused is ``APPROVED`` and not a state of its own: an absence whose
        cancellation was declined is an ordinary approved absence, and
        "approved, but somebody once asked to cancel it" is a state nothing else
        in the app knows how to read."""
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.CANCELLING,
        )
        manager_client.post(f"/absences/requests/{absence.pk}/decide/",
                            {"note": "Der Dienstplan steht schon."})
        absence.refresh_from_db()
        assert absence.status == RequestStatus.APPROVED
        assert absence.costs_leave
        assert absence.decision_note

    def test_refusing_a_cancellation_without_a_reason_is_refused(
        self, org, anna, manager_client, monday,
    ):
        """The same rule as declining a request, through the same form: a no
        without a sentence sends somebody to go and ask for one."""
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.CANCELLING,
        )
        manager_client.post(f"/absences/requests/{absence.pk}/decide/", {"note": ""})
        absence.refresh_from_db()
        assert absence.status == RequestStatus.CANCELLING

    def test_asking_twice_changes_nothing(self, org, anna, client, monday):
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.CANCELLING,
        )
        client.post(f"/absences/request/{absence.pk}/withdraw/")
        absence.refresh_from_db()
        assert absence.status == RequestStatus.CANCELLING


def _square(response, day):
    """The one cell of the rendered year that is ``day``.

    Walks the whole structure rather than indexing into it, which is the half
    of the assertion that matters: a month's weeks start on a Monday and carry
    the neighbouring month's dates, so arithmetic on the offsets is exactly the
    thing that goes wrong and exactly the thing this must not repeat.
    """
    found = [
        cell
        for month in response.context["months"]
        for week in month["weeks"]
        for cell in week
        if cell is not None and cell["date"] == day
    ]
    assert len(found) == 1, (
        f"{day} appears {len(found)} times in the year; a date drawn twice is a "
        "date somebody can click twice and see two different things about"
    )
    return found[0]


class TestTheYearAsAGrid:
    """The Time off page is a year of squares and the square is the control.

    Every assertion below is about the *cell dictionary* rather than about the
    markup, because that is where the six things a day has to know at once are
    decided — and template logic asking them in six nested ``{% if %}``s is
    logic no test can reach.
    """

    def test_it_draws_the_twelve_months_of_the_year_it_was_asked_for(
        self, org, anna, client,
    ):
        response = client.get("/absences/?year=2026")
        assert response.status_code == 200
        months = response.context["months"]
        assert [month["number"] for month in months] == list(range(1, 13))

    def test_no_date_is_drawn_in_two_months(self, org, anna, client):
        """``monthdatescalendar`` hands back whole weeks, so a January block
        contains dates in December and February. Drawing them would put the
        same day on the page twice, in two blocks, each with its own button."""
        response = client.get("/absences/?year=2026")
        for month in response.context["months"]:
            for week in month["weeks"]:
                for cell in week:
                    assert cell is None or cell["date"].month == month["number"]

    def test_a_working_day_is_a_control_and_a_weekend_is_not(
        self, org, anna, client, monday,
    ):
        response = client.get(f"/absences/?year={monday.year}")
        assert _square(response, monday)["can_book"]
        saturday = monday + dt.timedelta(days=5)
        assert not _square(response, saturday)["can_book"]
        assert _square(response, saturday)["is_weekend"]

    def test_a_day_the_contract_gives_no_hours_is_not_a_control(
        self, org, cem, monday, client, user,
    ):
        """Cem works Monday to Wednesday. His Thursday is not a square anybody
        can book: it costs nothing, so the form would refuse it — and inviting
        somebody to press a control that refuses is worse than a pale square."""
        cem.user = user
        cem.save(update_fields=["user"])
        response = client.get(f"/absences/?year={monday.year}")
        assert not _square(response, monday + dt.timedelta(days=3))["can_book"]

    def test_a_public_holiday_costs_nothing_so_it_cannot_be_booked(
        self, org, anna, client,
    ):
        BankHoliday.objects.create(date=dt.date(2026, 5, 1), name="Tag der Arbeit")
        response = client.get("/absences/?year=2026")
        cell = _square(response, dt.date(2026, 5, 1))
        assert not cell["can_book"]
        assert cell["holiday"] == "Tag der Arbeit"
        # The name, because that is the one thing a square this size cannot say
        # for itself and the one thing somebody pointing at it wants.
        assert cell["title"] == "Tag der Arbeit"

    def test_approved_is_solid_and_waiting_is_dotted(self, org, anna, client, monday):
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday, status=RequestStatus.APPROVED,
        )
        tuesday = monday + dt.timedelta(days=1)
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.SICK,
            start_date=tuesday, end_date=tuesday, status=RequestStatus.REQUESTED,
        )
        response = client.get(f"/absences/?year={monday.year}")

        settled = _square(response, monday)
        assert settled["kind"] == AbsenceKind.HOLIDAY and not settled["is_pending"]
        waiting = _square(response, tuesday)
        assert waiting["kind"] == AbsenceKind.SICK and waiting["is_pending"]

    def test_a_declined_request_is_not_drawn_at_all(self, org, anna, client, monday):
        """Declined and withdrawn rows are history, not a claim on the
        calendar. They are still in the table below it, which is where the
        manager's written reply lives."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday, status=RequestStatus.REJECTED,
        )
        response = client.get(f"/absences/?year={monday.year}")
        assert _square(response, monday)["kind"] == ""
        assert _square(response, monday)["can_book"]

    def test_a_day_inside_a_range_that_cost_nothing_is_drawn_as_costing_nothing(
        self, org, anna, client, monday,
    ):
        """A fortnight booked over a weekend is not a fortnight of leave — it is
        ten days, and ``working_days`` says so. The grid has to agree with the
        balance or the page argues with itself: painting the whole stretch one
        colour would be claiming days that were never taken."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=6),
            status=RequestStatus.APPROVED,
        )
        response = client.get(f"/absences/?year={monday.year}")
        assert _square(response, monday + dt.timedelta(days=4))["kind"] == AbsenceKind.HOLIDAY
        assert _square(response, monday + dt.timedelta(days=5))["kind"] == ""

    def test_days_booked_together_are_joined_into_one_bar(
        self, org, anna, client, monday,
    ):
        """One booking, one bar. The middles of a run lose the edge that faces
        the next day, so a week off does not read as five separate bookings
        that happen to be adjacent — which is also the truth about what can be
        withdrawn, since the row is the unit."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=2),
            status=RequestStatus.APPROVED,
        )
        response = client.get(f"/absences/?year={monday.year}")
        first = _square(response, monday)
        middle = _square(response, monday + dt.timedelta(days=1))
        last = _square(response, monday + dt.timedelta(days=2))

        assert not first["joins_left"] and first["joins_right"]
        assert middle["joins_left"] and middle["joins_right"]
        assert last["joins_left"] and not last["joins_right"]

    def test_two_bookings_side_by_side_stay_two_bars(
        self, org, anna, client, monday,
    ):
        """Compared on identity and not on kind or on adjacency: two holidays
        that touch are two decisions, and withdrawing one must not look like
        withdrawing both."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday, status=RequestStatus.APPROVED,
        )
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday + dt.timedelta(days=1),
            end_date=monday + dt.timedelta(days=1),
            status=RequestStatus.APPROVED,
        )
        response = client.get(f"/absences/?year={monday.year}")
        assert not _square(response, monday)["joins_right"]
        assert not _square(response, monday + dt.timedelta(days=1))["joins_left"]

    def test_a_run_is_named_by_its_span_and_a_single_day_by_its_date(
        self, org, anna, client, monday,
    ):
        """What the pop-up is headed. A square inside a booking of several days
        is a handle on the whole booking, so naming it after the date that was
        clicked would misname what the only button on the dialog does."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=2),
            status=RequestStatus.APPROVED,
        )
        response = client.get(f"/absences/?year={monday.year}")
        middle = _square(response, monday + dt.timedelta(days=1))
        assert middle["is_group"]
        assert middle["label"] == middle["when"]

        empty = _square(response, monday + dt.timedelta(days=3))
        assert not empty["is_group"]
        assert str(monday.year) in empty["label"]
        assert empty["label"] != empty["when"]

    def test_the_square_says_which_way_taking_it_back_would_go(
        self, org, anna, client, monday,
    ):
        """The same line ``request_cancel`` draws, decided once and rendered on
        the button: nothing a manager has not answered is theirs yet, and
        something approved is a day the roster was built around."""
        waiting = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday, status=RequestStatus.REQUESTED,
        )
        response = client.get(f"/absences/?year={monday.year}")
        assert _square(response, monday)["action"] == "withdraw"

        waiting.status = RequestStatus.APPROVED
        waiting.save(update_fields=["status"])
        response = client.get(f"/absences/?year={monday.year}")
        assert _square(response, monday)["action"] == "ask"

        waiting.status = RequestStatus.CANCELLING
        waiting.save(update_fields=["status"])
        response = client.get(f"/absences/?year={monday.year}")
        # Already with the manager: still drawn, still in force, and nothing
        # left to press.
        assert _square(response, monday)["action"] == ""
        assert _square(response, monday)["is_pending"]

    def test_a_closure_is_drawn_and_cannot_be_taken_back(
        self, org, anna, client, monday,
    ):
        closure = CompanyClosure(
            name="Betriebsferien", start_date=monday, end_date=monday,
        )
        closure.save()
        closure.apply()
        response = client.get(f"/absences/?year={monday.year}")
        cell = _square(response, monday)
        assert cell["kind"] == AbsenceKind.CLOSURE
        assert not cell["can_book"], "the employer declared it; one person cannot undo it"

    def test_a_locked_day_is_not_a_control(self, org, anna, client, monday):
        """The lock is honoured by every door, this page included. A square
        that offered to book a locked day would be offering a control whose
        only answer is the refusal in ``AbsenceRequestForm``."""
        from apps.timesheets.models import DayLock

        DayLock.objects.create(employee=anna, date=monday)
        response = client.get(f"/absences/?year={monday.year}")
        assert not _square(response, monday)["can_book"]
        assert _square(response, monday)["is_locked"]


class TestTheOneDoorForAsking:
    """``book`` dispatches to the two forms and adds nothing else.

    Every rule about who may ask for what lives in ``AbsenceRequestForm`` and
    ``SickForm``; a second answer here would disagree with the first the day
    either changed. What is tested is the dispatch, and that a refusal writes
    nothing.
    """

    def test_a_day_off_and_an_illness_go_through_the_same_route(
        self, org, anna, client, monday,
    ):
        client.post("/absences/book/", {
            "kind": AbsenceKind.HOLIDAY, "year": str(monday.year),
            "start_date": monday.isoformat(), "end_date": monday.isoformat(),
        })
        tuesday = monday + dt.timedelta(days=1)
        client.post("/absences/book/", {
            "kind": AbsenceKind.SICK, "year": str(monday.year),
            "start_date": tuesday.isoformat(), "end_date": tuesday.isoformat(),
        })
        kinds = set(anna.absences.values_list("kind", flat=True))
        assert kinds == {AbsenceKind.HOLIDAY, AbsenceKind.SICK}
        assert set(anna.absences.values_list("status", flat=True)) == {
            RequestStatus.REQUESTED,
        }

    def test_extra_off_days_name_the_entitlement_they_come_out_of(
        self, org, anna, client, monday,
    ):
        from apps.employees.models import SpecialLeaveGrant
        from apps.organisation.models import AssignmentMode, SpecialLeaveType

        funeral = SpecialLeaveType.objects.create(
            name="Trauerfall", mode=AssignmentMode.FIXED, days=Decimal("2.0"),
        )
        SpecialLeaveGrant.objects.create(employee=anna, leave_type=funeral)

        client.post("/absences/book/", {
            "kind": AbsenceKind.SPECIAL, "special_type": str(funeral.pk),
            "year": str(monday.year),
            "start_date": monday.isoformat(), "end_date": monday.isoformat(),
        })
        absence = anna.absences.get()
        assert absence.kind == AbsenceKind.SPECIAL
        assert absence.special_type_id == funeral.pk

    def test_extra_off_days_without_a_type_are_refused_and_write_nothing(
        self, org, anna, client, monday,
    ):
        """Special leave that does not say which entitlement it came out of
        cannot be counted against one, so it is refused rather than saved
        against nothing."""
        response = client.post("/absences/book/", {
            "kind": AbsenceKind.SPECIAL, "year": str(monday.year),
            "start_date": monday.isoformat(), "end_date": monday.isoformat(),
        })
        assert response.status_code == 302
        assert not anna.absences.exists()

    def test_the_button_is_not_offered_to_somebody_with_no_grant(
        self, org, anna, client,
    ):
        """A type not listed on somebody's contract is not theirs — it is not
        "zero days of it" — so the form's list would be empty and its only
        possible outcome a refusal."""
        assert client.get("/absences/").context["can_ask_special"] is False

    def test_it_comes_back_to_the_year_that_was_being_looked_at(
        self, org, anna, client,
    ):
        """The year travels in the body, not only the query string. Without it
        a request made for next March would answer with this year's grid, on
        which the day just booked does not appear at all — which reads exactly
        like a save that did not take."""
        response = client.post("/absences/book/", {
            "kind": AbsenceKind.HOLIDAY, "year": "2027",
            "start_date": "2027-03-01", "end_date": "2027-03-02",
        })
        assert response["Location"].endswith("?year=2027")
