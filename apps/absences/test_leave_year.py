"""Half days, credited hours, contract changes, and leave that expires.

Four features that all move the same two numbers — how many days somebody has
and how many hours a week is worth — and every one of them is wrong in a way
that renders perfectly. That is the reason for the density of assertions here:
none of these failures announces itself.
"""

import datetime as dt
from decimal import Decimal

import pytest

from apps.absences.carryover import LeaveCarryOver, expire_due
from apps.absences.models import Absence, AbsenceKind, Balance, RequestStatus
from apps.timesheets.hours import contracted_minutes
from apps.timesheets.views import build_week


# --------------------------------------------------------------------------
# Half days
# --------------------------------------------------------------------------

class TestHalfDays:
    def test_a_half_day_costs_half_a_day(self, org, anna, monday):
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            is_half_day=True, status=RequestStatus.APPROVED,
        )
        assert absence.working_days() == Decimal("0.5")
        assert absence.days_charged() == Decimal("0.5")

    def test_a_whole_day_still_costs_one(self, org, anna, monday):
        absence = Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.APPROVED,
        )
        assert absence.working_days() == Decimal("1")

    def test_a_half_day_on_a_range_is_refused(self, org, anna, monday):
        """Four more states, every one of which has to be right in three places.
        Two rows is one more click and no ambiguity at all about what was
        booked."""
        absence = Absence(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday + dt.timedelta(days=2),
            is_half_day=True,
        )
        with pytest.raises(Exception):
            absence.full_clean()

    def test_a_half_day_on_a_day_off_still_costs_nothing(self, org, cem, monday):
        """Half of a day somebody does not work is still nothing. The three
        subtractions come first and the halving comes after."""
        thursday = monday + dt.timedelta(days=3)  # cem works Mon-Wed
        absence = Absence.objects.create(
            employee=cem, kind=AbsenceKind.HOLIDAY,
            start_date=thursday, end_date=thursday,
            is_half_day=True, status=RequestStatus.APPROVED,
        )
        assert absence.working_days() == Decimal("0")

    def test_the_balance_adds_halves_without_a_float(self, org, anna, monday):
        """0.5 has to survive being added to 2 and compared against an
        entitlement. Doing it in floats is how a balance page ends up reading
        17.499999999999996."""
        for offset in (0, 1, 2):
            Absence.objects.create(
                employee=anna, kind=AbsenceKind.HOLIDAY,
                start_date=monday + dt.timedelta(days=offset),
                end_date=monday + dt.timedelta(days=offset),
                is_half_day=True, status=RequestStatus.APPROVED,
            )
        balance = Balance(anna, monday.year)
        assert balance.taken == Decimal("1.5")


# --------------------------------------------------------------------------
# Absence credits the contracted hours
# --------------------------------------------------------------------------

class TestAbsenceCreditsHours:
    """A sick day is paid as though it had been worked, and so is a day of leave.

    The earlier version credited nothing, so a fortnight's flu showed as eighty
    hours of shortfall — a debt German law says outright the employee does not
    owe. That was not a conservative simplification; it was a wrong figure in
    the direction that costs the employee.
    """

    def test_sickness_credits_the_contracted_hours(self, org, anna, monday):
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.SICK,
            start_date=monday, end_date=monday,
            status=RequestStatus.APPROVED,
        )
        week = build_week(anna, monday)
        row = week["rows"][0]
        assert row["credited_minutes"] == contracted_minutes(Decimal("8"))
        assert row["worked_minutes"] is None, "nobody worked it, and the row says so"
        # The day comes out level: eight credited against eight contracted. The
        # rest of the week is still unanswered, which is a different statement
        # and is why the two figures are separate columns.
        assert row["counted_minutes"] == row["contracted_minutes"]
        assert week["credited_total"] == contracted_minutes(Decimal("8"))

    def test_a_half_day_credits_half(self, org, anna, monday):
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            is_half_day=True, status=RequestStatus.APPROVED,
        )
        week = build_week(anna, monday)
        assert week["rows"][0]["credited_minutes"] == contracted_minutes(Decimal("4"))

    def test_time_off_in_lieu_credits_nothing(self, org, anna, monday):
        """The whole mechanism of overtime, in one assertion. The shortfall on
        that day *is* the overtime being taken back — crediting it would cancel
        the draw-down and leave the app inventing a second set of figures to
        disagree with the first."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.OVERTIME,
            start_date=monday, end_date=monday,
            status=RequestStatus.APPROVED,
        )
        week = build_week(anna, monday)
        row = week["rows"][0]
        assert row["credited_minutes"] == 0
        # A full contracted day of shortfall, with nothing credited against it.
        # That shortfall is the overtime being spent.
        assert row["counted_minutes"] == 0
        assert row["contracted_minutes"] == contracted_minutes(Decimal("8"))
        assert week["credited_total"] == 0

    def test_a_request_still_waiting_credits_nothing(self, org, anna, monday):
        """Crediting it would let a request that is later declined take hours
        off a timesheet retrospectively."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.REQUESTED,
        )
        assert build_week(anna, monday)["rows"][0]["credited_minutes"] == 0

    @pytest.mark.parametrize("status", [
        RequestStatus.REQUESTED, RequestStatus.REJECTED, RequestStatus.WITHDRAWN,
    ])
    def test_a_sick_day_that_is_not_approved_credits_nothing(
        self, org, anna, monday, status,
    ):
        """**Including one nobody has decided yet.** Sickness used to be the
        exception here — reported was as good as granted, and only a positive
        refusal stopped the credit. It behaves like every other absence now, and
        the parametrisation is the point: waiting, refused and withdrawn are one
        answer, not three."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.SICK,
            start_date=monday, end_date=monday, status=status,
        )
        assert build_week(anna, monday)["rows"][0]["credited_minutes"] == 0

    def test_an_absence_waiting_to_be_cancelled_still_counts(self, org, anna, monday):
        """Asking is not the same as being granted it. The day is still booked
        until a manager answers, so the hours are still credited — otherwise the
        figures would move on a press nobody had responded to."""
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday,
            status=RequestStatus.CANCELLING,
        )
        assert build_week(anna, monday)["rows"][0]["credited_minutes"] == (
            contracted_minutes(Decimal("8"))
        )


# --------------------------------------------------------------------------
# The contract is a history
# --------------------------------------------------------------------------

class TestChangingTheHours:
    def test_the_past_keeps_the_old_contract(self, org, anna, monday):
        """The whole reason a contract is a history. Editing seven columns in
        place would make January's Wednesday a day she never worked, with every
        page still rendering and different numbers than yesterday."""
        later = monday + dt.timedelta(weeks=13)  # a Monday, so +2 is a Wednesday
        anna.set_hours([8, 8, 0, 0, 0, 0, 0], valid_from=later, note="went to two days")

        assert anna.works_on(monday + dt.timedelta(days=2)), "the Wednesday before"
        assert not anna.works_on(later + dt.timedelta(days=2)), "and not the one after"
        assert anna.hours_on_weekday(2, on=monday) == Decimal("8.00")
        assert anna.hours_on_weekday(2, on=later) == Decimal("0.00")

    def test_the_entitlement_is_weighted_across_the_change(self, org, anna):
        """Half a year on five days and half on three is not a five-day year
        and not a three-day one. Applying today's contract to the whole year
        overpays somebody who went up and short-changes somebody who went down,
        and the second is the one that gets litigated."""
        year = 2026
        anna.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(year, 1, 1))
        anna.set_hours([8, 8, 8, 0, 0, 0, 0], valid_from=dt.date(year, 7, 1))

        full_five_days = org.leave_days_for(5)   # 30
        full_three_days = org.leave_days_for(3)  # 18
        weighted = anna.leave_days_in_year(year, org)

        assert full_three_days < weighted < full_five_days

    def test_joining_in_october_is_not_a_full_year(self, org, db):
        """Somebody who started in October is not entitled to a full year's
        leave. The version that showed them one was not generous; it was wrong
        on the page they use to decide whether they can afford Christmas.

        Both figures are asserted, because the pair is the point: the contract
        is worth a full 30 days a year, and *this* year it bought a quarter of
        that. A single number would be quietly answering the wrong question.
        """
        from apps.employees.models import Employee

        started = dt.date(2020, 10, 1)
        late = Employee.objects.create(
            first_name="Late", username="late.test", started_on=started,
        )
        late.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=started)

        assert late.annual_leave_days(org) == org.leave_days_for(5)
        assert late.leave_days_in_year(2020, org) < org.leave_days_for(5)
        assert late.leave_days_in_year(2021, org) == org.leave_days_for(5)

    def test_a_contract_that_has_not_started_gives_no_hours(self, org, db):
        """A date before somebody's first contract is a date they had no
        contract on, and every caller reads that as no hours. It is the honest
        answer for a row created in advance of a start date, and it is visible —
        a page of zeros with a start date in the future explains itself."""
        from apps.employees.models import Employee

        future = dt.date.today() + dt.timedelta(days=30)
        soon = Employee.objects.create(
            first_name="Soon", username="soon.test", started_on=future,
        )
        soon.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=future)

        assert soon.contract_on(dt.date.today()) is None
        assert soon.working_days_per_week == 0
        assert soon.contract_on(future) is not None
        assert soon.hours_on_weekday(0, on=future) == Decimal("8.00")

    def test_an_override_still_replaces_the_lot(self, org, anna):
        """A contract that says 30 days says 30 days, and second-guessing it by
        month is not what it agreed to."""
        anna.leave_days_override = Decimal("30.0")
        anna.save()
        anna.set_hours([8, 8, 0, 0, 0, 0, 0], valid_from=dt.date(2026, 7, 1))
        assert anna.leave_days_in_year(2026, org) == Decimal("30.0")

    def test_the_timesheet_measures_against_the_contract_of_that_week(
        self, org, anna, monday,
    ):
        later = monday + dt.timedelta(days=90)
        anna.set_hours([4, 4, 4, 4, 4, 0, 0], valid_from=later)

        before = build_week(anna, monday)
        after = build_week(anna, later - dt.timedelta(days=later.weekday()) + dt.timedelta(days=7))
        assert before["contracted_total"] == contracted_minutes(Decimal("40"))
        assert after["contracted_total"] == contracted_minutes(Decimal("20"))


# --------------------------------------------------------------------------
# Carry-over and expiry
# --------------------------------------------------------------------------

class TestCarryingLeaveOver:
    def test_closing_a_year_splits_the_two_pots(self, org, anna):
        """Statutory and employer-granted leave expire on different terms, so
        what is left has to be split back into them — and the split assumes the
        *perishable* pot was spent first, which is the reading that protects the
        employee."""
        org.full_time_leave_days = Decimal("30.0")
        org.statutory_leave_days = Decimal("20.0")
        org.save()
        anna.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2025, 1, 1))

        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=dt.date(2025, 6, 2), end_date=dt.date(2025, 6, 13),
            status=RequestStatus.APPROVED,
        )
        taken = Balance(anna, 2025, org).taken
        row = LeaveCarryOver.close_year(anna, 2025, org)

        assert row is not None
        assert row.year == 2026
        assert row.total_days == Decimal("30") - taken
        # The statutory pot was drawn down first.
        assert row.statutory_days == Decimal("20") - taken
        assert row.employer_days == Decimal("10")

    def test_the_two_halves_always_add_up_to_what_is_left(self, org, db):
        """The invariant that caught a real bug.

        The first version took the *full-year* statutory figure as the protected
        share, so somebody who joined in July had an entitlement of 14 days of
        which "20" were statutory — a carry-over row claiming more days than the
        year it came from ever held, on a page that could never be made to
        balance. Checked across a spread of patterns and joining dates rather
        than one, because the failure only appeared when the total had been
        brought down to meet the statutory floor.
        """
        from apps.employees.models import Employee

        org.full_time_leave_days = Decimal("30.0")
        org.statutory_leave_days = Decimal("20.0")
        org.save()

        cases = [
            ("full", [8, 8, 8, 8, 8, 0, 0], None),
            ("part", [8, 8, 4, 0, 0, 0, 0], None),
            ("joined-july", [8, 8, 8, 8, 8, 0, 0], dt.date(2025, 7, 15)),
            ("joined-november", [8, 8, 8, 8, 8, 0, 0], dt.date(2025, 11, 1)),
            ("two-days-joined-october", [6, 6, 0, 0, 0, 0, 0], dt.date(2025, 10, 1)),
        ]
        for name, hours, started in cases:
            person = Employee.objects.create(
                first_name=name.title(), username=f"{name}.test", started_on=started,
            )
            person.set_hours(hours, valid_from=started or dt.date(2024, 1, 1))

            balance = Balance(person, 2025, org)
            row = LeaveCarryOver.close_year(person, 2025, org)
            if row is None:
                assert balance.remaining <= 0, name
                continue

            assert row.total_days == balance.remaining, (
                f"{name}: the two pots come to {row.total_days} but only "
                f"{balance.remaining} days were left"
            )
            assert row.statutory_days <= balance.this_year, (
                f"{name}: more statutory days carried than the year was worth"
            )
            assert row.statutory_days >= 0 and row.employer_days >= 0, name

    def test_it_is_idempotent(self, org, anna):
        """A manager who presses it twice, or presses it in January and again in
        February after a late correction, gets the right answer rather than a
        doubled one."""
        anna.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2025, 1, 1))
        first = LeaveCarryOver.close_year(anna, 2025, org)
        second = LeaveCarryOver.close_year(anna, 2025, org)
        assert first.pk == second.pk
        assert LeaveCarryOver.objects.filter(employee=anna, year=2026).count() == 1

    def test_nothing_left_writes_no_row(self, org, anna):
        """A row of zeros is noise on every page that lists these."""
        anna.leave_days_override = Decimal("0")
        anna.save()
        assert LeaveCarryOver.close_year(anna, 2025, org) is None

    def test_the_balance_includes_what_was_carried(self, org, anna):
        anna.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2025, 1, 1))
        LeaveCarryOver.close_year(anna, 2025, org, notice_given_on=dt.date(2025, 11, 1))

        balance = Balance(anna, 2026, org)
        assert balance.carried_days > 0
        assert balance.entitlement == balance.this_year + balance.carried_days


class TestTheYearEndPage:
    """The manager's door onto all of it."""

    def test_closing_a_year_closes_the_year_the_button_named(
        self, org, anna, manager, manager_client,
    ):
        """The year travels in the form body, not the query string.

        The first version of `_year_from` read only `request.GET`, so every POST
        fell back to *today's* year: the button labelled "close 2025" closed
        2026 and carried everybody into 2027. Nothing raised — the page came
        back with a cheerful message naming the wrong year, which is the only
        reason it was ever noticed.
        """
        anna.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2024, 1, 1))

        manager_client.post("/absences/year-end/close/", {
            "year": "2025", "notice_given_on": "2025-11-15",
        })

        assert LeaveCarryOver.objects.filter(employee=anna, year=2026).exists(),             "2025 was closed into 2026"
        assert not LeaveCarryOver.objects.filter(year=2027).exists(),             "and not into whatever year it happens to be today"

    def test_expiring_early_is_refused(self, org, anna, manager, manager_client):
        """The days are the employee's until the morning after the deadline, and
        there is no undo for taking them away."""
        anna.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2024, 1, 1))
        LeaveCarryOver.close_year(anna, 2025, org, notice_given_on=dt.date(2025, 11, 1))

        future = dt.date.today().year + 1
        manager_client.post("/absences/year-end/expire/", {"year": str(future)})

        row = LeaveCarryOver.objects.get(employee=anna, year=2026)
        assert not row.is_forfeited

    def test_an_ordinary_employee_cannot_close_a_year(self, org, anna, client):
        response = client.post("/absences/year-end/close/", {"year": "2025"})
        assert response.status_code == 404
        assert not LeaveCarryOver.objects.exists()


class TestWhenLeaveExpires:
    """The rule that decides whether somebody's untaken days still exist.

    Under German case law the statutory part lapses **only** if the employer
    demonstrably told the employee what was left and that it was about to. An
    app that expired the days anyway would be destroying an entitlement that
    still legally exists, and the record that it existed with it.
    """

    def _carry(self, anna, org, notice=None):
        anna.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2025, 1, 1))
        return LeaveCarryOver.close_year(anna, 2025, org, notice_given_on=notice)

    def test_without_the_reminder_nothing_lapses(self, org, anna):
        row = self._carry(anna, org, notice=None)
        assert row.statutory_deadline == dt.date(2026, 3, 31)
        assert not row.expires_statutory
        assert row.blocked_by_missing_notice
        assert row.statutory_available_on(dt.date(2026, 6, 1)) == row.statutory_days

        lost = expire_due(2026, on=dt.date(2026, 6, 1), settings=org)
        assert lost == [], "days nobody was warned about do not lapse"

    def test_with_the_reminder_they_lapse_after_the_deadline(self, org, anna):
        row = self._carry(anna, org, notice=dt.date(2025, 11, 1))
        assert row.expires_statutory
        assert row.statutory_available_on(dt.date(2026, 3, 31)) == row.statutory_days
        assert row.statutory_available_on(dt.date(2026, 4, 1)) == Decimal("0")

        lost = expire_due(2026, on=dt.date(2026, 4, 1), settings=org)
        assert len(lost) == 1
        row.refresh_from_db()
        assert row.is_forfeited
        assert row.forfeited_on == dt.date(2026, 4, 1)

    def test_the_employers_extra_follows_its_own_deadline(self, org, anna):
        """The asymmetry is the point: the reminder requirement protects the
        *statutory* entitlement. Leave the employer granted on top is the
        employer's to define, and a contract that says it dies with the year is
        lawful."""
        org.employer_deadline_month = 12
        org.employer_deadline_day = 31
        org.save()
        row = self._carry(anna, org, notice=None)
        assert row.employer_deadline == dt.date(2026, 12, 31)
        assert row.employer_available_on(dt.date(2027, 1, 1)) == Decimal("0")

    def test_switching_expiry_off_carries_indefinitely(self, org, anna):
        org.statutory_expires = False
        org.employer_expires = False
        org.save()
        row = self._carry(anna, org, notice=dt.date(2025, 11, 1))
        assert row.statutory_deadline is None
        assert row.employer_deadline is None
        assert row.available_on(dt.date(2030, 1, 1)) == row.total_days

    def test_a_manager_can_extend_one_persons_deadline(self, org, anna, manager):
        """The special-circumstances door. Per person, because the
        circumstances are — and a blanket extension would be a change to the
        policy rather than an exception to it."""
        row = self._carry(anna, org, notice=dt.date(2025, 11, 1))
        row.extend(
            manager.user, statutory=dt.date(2026, 6, 30),
            reason="off sick from November to March",
        )
        row.refresh_from_db()
        assert row.statutory_deadline == dt.date(2026, 6, 30)
        assert row.extended_by == manager.user
        assert row.statutory_available_on(dt.date(2026, 4, 1)) == row.statutory_days

    def test_an_extension_needs_a_reason(self, org, anna, manager):
        """"Why is hers 30 June" is a question somebody asks months later, at
        which point the answer exists only in the head of whoever pressed the
        button."""
        row = self._carry(anna, org, notice=dt.date(2025, 11, 1))
        with pytest.raises(Exception):
            row.extend(manager.user, statutory=dt.date(2026, 6, 30), reason="  ")

    def test_days_already_spent_cannot_lapse_again(self, org, anna):
        """Somebody who used their carried days in February has nothing left to
        lose in March, and forfeiting the original figure would take days off a
        balance the same absences had already reduced."""
        row = self._carry(anna, org, notice=dt.date(2025, 11, 1))
        # Long enough to spend everything that was carried in. Eight weeks of a
        # five-day contract is forty working days against thirty carried.
        Absence.objects.create(
            employee=anna, kind=AbsenceKind.HOLIDAY,
            start_date=dt.date(2026, 1, 5), end_date=dt.date(2026, 2, 27),
            status=RequestStatus.APPROVED,
        )
        taken = Balance(anna, 2026, org).taken
        assert taken >= row.total_days, "everything carried in was spent"

        expire_due(2026, on=dt.date(2026, 4, 1), settings=org)
        row.refresh_from_db()
        assert not row.is_forfeited

    def test_a_forfeited_row_cannot_be_extended(self, org, anna, manager):
        """Moving the deadline afterwards would erase the record of a morning on
        which somebody's days stopped existing."""
        row = self._carry(anna, org, notice=dt.date(2025, 11, 1))
        expire_due(2026, on=dt.date(2026, 4, 1), settings=org)
        row.refresh_from_db()
        with pytest.raises(Exception):
            row.extend(manager.user, statutory=dt.date(2026, 9, 30), reason="late notice")

    def test_the_balance_stops_showing_lapsed_days(self, org, anna):
        """The figure on the page has to be what is spendable *now*. Asking as
        at the end of the year would go on showing lapsed days all year."""
        row = self._carry(anna, org, notice=dt.date(2025, 11, 1))
        row.statutory_deadline = dt.date(2020, 3, 31)
        row.employer_deadline = dt.date(2020, 12, 31)
        row.save()

        balance = Balance(anna, 2026, org)
        assert balance.carried_days == Decimal("0")
        assert balance.entitlement == balance.this_year
