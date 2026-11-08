"""The line the month draws on the day a contract changed, and the manager's
way from one person's month to the next.

Both exist for the same reason and it is worth saying once: the ``Soll`` column
is read straight down, and the two things that make it step — a different
contract, or a different person — are the two things the grid itself cannot say.
"""

import datetime as dt
from decimal import Decimal

import pytest

from apps.timesheets.views import build_month


def _row_on(month, day):
    return next(row for row in month["rows"] if row["date"] == day)


@pytest.mark.django_db
class TestTheContractChangeIsSaidOnTheMonth:

    def test_the_day_a_change_takes_effect_carries_it(self, anna, org):
        """The row the note is drawn above, and only that row."""
        anna.set_hours(
            [Decimal("8"), Decimal("8"), Decimal("8"), Decimal("6"), Decimal("0"),
             Decimal("0"), Decimal("0")],
            valid_from=dt.date(2026, 3, 16),
        )
        month = build_month(anna, dt.date(2026, 3, 1))

        assert _row_on(month, dt.date(2026, 3, 16))["contract_change"] is not None
        assert _row_on(month, dt.date(2026, 3, 15))["contract_change"] is None
        assert _row_on(month, dt.date(2026, 3, 17))["contract_change"] is None
        assert sum(1 for row in month["rows"] if row["contract_change"]) == 1

    def test_it_names_what_the_hours_moved_from(self, anna, org):
        """A change is two figures and the row below it only carries one. The
        month says both or it says nothing worth reading."""
        anna.set_hours(
            [Decimal("8"), Decimal("8"), Decimal("8"), Decimal("6"), Decimal("0"),
             Decimal("0"), Decimal("0")],
            valid_from=dt.date(2026, 3, 16),
        )
        row = _row_on(build_month(anna, dt.date(2026, 3, 1)), dt.date(2026, 3, 16))

        assert row["contract_change"].weekly_hours == Decimal("30")
        assert row["contract_change"].working_days_per_week == 4
        assert row["contract_before"].weekly_hours == Decimal("40")
        assert row["contract_before"].working_days_per_week == 5

    def test_the_first_contract_is_never_a_change(self, anna, org):
        """Everybody has one. It is their contract rather than a change to one,
        and a note reading "the hours changed" on somebody's first day would be
        on every timesheet in the house saying nothing."""
        first = anna.contract_periods.order_by("valid_from").first()
        month = build_month(anna, dt.date(first.valid_from.year, first.valid_from.month, 1))
        assert _row_on(month, first.valid_from)["contract_change"] is None

    def test_a_change_in_another_month_is_not_on_this_one(self, anna, org):
        anna.set_hours(
            [Decimal("6")] * 5 + [Decimal("0"), Decimal("0")],
            valid_from=dt.date(2026, 5, 4),
        )
        month = build_month(anna, dt.date(2026, 3, 1))
        assert not any(row["contract_change"] for row in month["rows"])

    def test_the_soll_column_actually_steps_across_it(self, anna, org):
        """The note is only worth drawing because the figure below it moves. If
        this ever stopped being true the note would be explaining something that
        did not happen."""
        anna.set_hours(
            [Decimal("8"), Decimal("8"), Decimal("8"), Decimal("0"), Decimal("0"),
             Decimal("0"), Decimal("0")],
            valid_from=dt.date(2026, 3, 16),
        )
        month = build_month(anna, dt.date(2026, 3, 1))
        # Thursday 12 March under the old contract, Thursday 19 under the new.
        assert _row_on(month, dt.date(2026, 3, 12))["contracted_minutes"] == 8 * 60
        assert _row_on(month, dt.date(2026, 3, 19))["contracted_minutes"] == 0


@pytest.mark.django_db
class TestSteppingFromOnePersonToTheNext:

    def test_a_manager_gets_the_list_and_the_two_neighbours(
        self, manager_client, anna, cem, dilan, org,
    ):
        response = manager_client.get(f"/team/{cem.pk}/")
        names = [person.first_name for person in response.context["people"]]
        # Employee.Meta.ordering — the order the People page is in, so "next"
        # means the next name somebody would have found by scrolling.
        assert names == sorted(names)
        assert response.context["previous_person"].first_name == "Ben"
        assert response.context["next_person"].first_name == "Dilan"

    def test_the_ends_of_the_list_do_not_wrap(self, manager_client, anna, cem, org):
        """An arrow that lands somewhere its direction did not promise is a
        control that lies; the disclosure beside it is how somebody gets back to
        the top."""
        people = manager_client.get(f"/team/{anna.pk}/").context["people"]
        first, last = people[0], people[-1]

        assert manager_client.get(f"/team/{first.pk}/").context["previous_person"] is None
        assert manager_client.get(f"/team/{last.pk}/").context["next_person"] is None

    def test_it_is_not_offered_on_your_own_timesheet(self, client, anna, cem, org):
        """There is nowhere to step to, and offering the control would be
        offering eleven timesheets to somebody entitled to one."""
        assert "people" not in client.get("/timesheet/").context

    def test_a_leaver_is_named_but_not_stepped_into(self, manager_client, anna, cem, org):
        """A manager opens a leaver's September precisely because they have
        left. A picker whose list did not contain the person it is naming would
        show the wrong name — the fault the month grid replaced a `<select>` to
        escape — but nobody else's arrows should walk into them."""
        cem.is_active = False
        cem.save()

        theirs = manager_client.get(f"/team/{cem.pk}/").context["people"]
        assert any(person.pk == cem.pk for person in theirs)

        others = manager_client.get(f"/team/{anna.pk}/").context["people"]
        assert not any(person.pk == cem.pk for person in others)
