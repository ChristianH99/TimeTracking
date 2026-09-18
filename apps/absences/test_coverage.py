"""The manager's two new pages: who is off, and what is waiting.

Both are read-only views over data the rest of the suite already pins, so what
is tested here is the *shape* — which is where a page like this goes wrong. A
coverage grid that draws an unapproved day the same as an approved one is a page
showing cover that does not exist; a requests page that groups by anything other
than the person is the pile the tiles were built to replace.

The assertions are on the context dictionaries and never on the markup, the same
rule ``TestTheYearAsAGrid`` follows: a test that asserts on a class name fails
the day somebody renames a colour.
"""

import datetime as dt

import pytest

from apps.absences.models import Absence, AbsenceKind, RequestStatus


def _book(employee, start, end, kind=AbsenceKind.HOLIDAY, status=RequestStatus.APPROVED,
          half=False):
    absence = Absence(
        employee=employee, kind=kind, start_date=start, end_date=end,
        status=status, is_half_day=half,
    )
    absence.save()
    return absence


def _row_for(response, employee):
    return next(
        row for row in response.context["rows"]
        if row["employee"].pk == employee.pk
    )


def _cell_on(row, day):
    return next(cell for cell in row["cells"] if cell["date"] == day)


@pytest.mark.django_db
class TestTheCoverageGrid:
    """A month with a row per person, and the day the answer is about."""

    def test_a_month_is_a_row_per_active_person(self, manager_client, anna, cem, org):
        response = manager_client.get("/absences/calendar/?month=2026-03")
        names = [row["employee"].first_name for row in response.context["rows"]]
        assert "Anna" in names and "Cem" in names
        # Thirty-one squares, one a date, and the header row is drawn from the
        # same list — a grid whose header and body disagree about how many days
        # March has is one whose columns are off by one from the 29th onwards.
        assert len(response.context["days"]) == 31
        for row in response.context["rows"]:
            assert len(row["cells"]) == 31

    def test_an_approved_day_and_a_waiting_one_are_not_drawn_alike(
        self, manager_client, anna, org,
    ):
        """The whole reason the page exists in this shape.

        A manager reading it for cover has to be able to tell what is settled
        from what is still a request: those are different facts about next
        Thursday, and painting them the same is a page showing cover that does
        not exist yet — or an absence that may never happen.
        """
        _book(anna, dt.date(2026, 3, 3), dt.date(2026, 3, 3))
        _book(anna, dt.date(2026, 3, 5), dt.date(2026, 3, 5),
              status=RequestStatus.REQUESTED)

        row = _row_for(manager_client.get("/absences/calendar/?month=2026-03"), anna)
        settled = _cell_on(row, dt.date(2026, 3, 3))
        waiting = _cell_on(row, dt.date(2026, 3, 5))

        assert settled["absence"] is not None and not settled["is_pending"]
        assert waiting["absence"] is not None and waiting["is_pending"]
        assert row["away_days"] == 2
        assert row["undecided_days"] == 1

    def test_a_cancellation_is_still_in_force_and_still_undecided(
        self, manager_client, anna, org,
    ):
        """``CANCELLING`` is the fifth status and it is both at once.

        The day is still booked — it still costs the leave and still credits its
        hours — and what is waiting is the asking to remove it. A grid that drew
        it as settled would hide a question from the person who has to answer
        it; one that drew it as gone would show cover nobody has agreed to.
        """
        booked = _book(anna, dt.date(2026, 3, 10), dt.date(2026, 3, 10))
        Absence.objects.filter(pk=booked.pk).update(status=RequestStatus.CANCELLING)

        row = _row_for(manager_client.get("/absences/calendar/?month=2026-03"), anna)
        cell = _cell_on(row, dt.date(2026, 3, 10))
        assert cell["absence"] is not None
        assert cell["is_pending"]

    def test_a_declined_day_is_not_on_the_grid_at_all(self, manager_client, anna, org):
        """History, not a claim on the calendar. A refused request drawn on a
        coverage grid is cover the manager has already decided they have."""
        _book(anna, dt.date(2026, 3, 12), dt.date(2026, 3, 12),
              status=RequestStatus.REJECTED)
        row = _row_for(manager_client.get("/absences/calendar/?month=2026-03"), anna)
        assert _cell_on(row, dt.date(2026, 3, 12))["absence"] is None

    def test_a_day_that_costs_nothing_is_drawn_as_costing_nothing(
        self, manager_client, cem, org,
    ):
        """The three subtractions ``Absence.working_days`` makes.

        Cem works Monday to Wednesday. A booking that runs over his Thursday is
        not charged for it, and the grid must not claim a day the balance never
        took — otherwise the page and the balance argue with each other in front
        of the person deciding.
        """
        # Monday 2 March to Friday 6 March 2026.
        _book(cem, dt.date(2026, 3, 2), dt.date(2026, 3, 6))
        row = _row_for(manager_client.get("/absences/calendar/?month=2026-03"), cem)

        worked = [_cell_on(row, dt.date(2026, 3, day)) for day in (2, 3, 4)]
        not_worked = [_cell_on(row, dt.date(2026, 3, day)) for day in (5, 6, 7, 8)]
        assert all(cell["absence"] is not None for cell in worked)
        assert all(cell["absence"] is None for cell in not_worked)
        assert row["away_days"] == 3

    def test_days_booked_together_are_joined(self, manager_client, anna, org):
        """One booking is one bar. Separate tiles say the opposite — that these
        are five decisions which happen to be adjacent — and the run is exactly
        the unit that can be withdrawn."""
        _book(anna, dt.date(2026, 3, 2), dt.date(2026, 3, 4))
        row = _row_for(manager_client.get("/absences/calendar/?month=2026-03"), anna)

        first, middle, last = (_cell_on(row, dt.date(2026, 3, d)) for d in (2, 3, 4))
        assert not first["joins_left"] and first["joins_right"]
        assert middle["joins_left"] and middle["joins_right"]
        assert last["joins_left"] and not last["joins_right"]

    def test_the_column_footer_counts_people_not_days(self, manager_client, anna, cem, org):
        """The row the grid is this way round for: a manager opens it to find
        out about Thursday, not about Anna."""
        _book(anna, dt.date(2026, 3, 3), dt.date(2026, 3, 3))
        _book(cem, dt.date(2026, 3, 3), dt.date(2026, 3, 3))
        _book(cem, dt.date(2026, 3, 4), dt.date(2026, 3, 4))

        response = manager_client.get("/absences/calendar/?month=2026-03")
        away = response.context["away_per_day"]
        assert len(away) == 31
        assert away[2] == 2   # the 3rd
        assert away[3] == 1   # the 4th
        assert away[0] == 0

    def test_a_month_that_cannot_be_read_falls_back_rather_than_raising(
        self, manager_client, anna, org,
    ):
        """It arrives in a query string. A 500 on ``?month=banana`` is a page
        somebody can break with a typo in the address bar."""
        response = manager_client.get("/absences/calendar/?month=banana")
        assert response.status_code == 200
        assert response.context["month"].day == 1

    def test_an_ordinary_employee_cannot_open_it(self, client, anna, cem, org):
        """Everybody's time off is everybody's data. The page is
        ``manager_required`` and ``test_privacy`` walks the URLconf for the
        general case; this is the one that names it."""
        assert client.get("/absences/calendar/").status_code == 404


@pytest.mark.django_db
class TestRequestsAreAPersonAtATime:
    """The tiles, and the case behind one of them."""

    def test_one_tile_a_person_however_many_requests(self, manager_client, anna, cem, org):
        """Three of Anna's requests are one conversation and one balance. In the
        flat list this replaced they sat wherever their start dates put them,
        with other people's cards in between — so approving the second without
        having seen the other two was the ordinary way to use the page."""
        for start in (dt.date(2026, 3, 3), dt.date(2026, 3, 10), dt.date(2026, 3, 17)):
            _book(anna, start, start, status=RequestStatus.REQUESTED)
        _book(cem, dt.date(2026, 3, 4), dt.date(2026, 3, 4),
              status=RequestStatus.REQUESTED)

        tiles = manager_client.get("/absences/requests/").context["tiles"]
        assert len(tiles) == 2
        mine = next(tile for tile in tiles if tile["employee"].pk == anna.pk)
        assert mine["count"] == 3
        assert mine["since"] == dt.date(2026, 3, 3)

    def test_a_tile_page_carries_no_calendar_and_a_person_page_does(
        self, manager_client, anna, org,
    ):
        _book(anna, dt.date(2026, 3, 3), dt.date(2026, 3, 3),
              status=RequestStatus.REQUESTED)

        assert "months" not in manager_client.get("/absences/requests/").context
        opened = manager_client.get(f"/absences/requests/?person={anna.pk}")
        assert opened.context["chosen"].pk == anna.pk
        assert opened.context["months"]

    def test_the_calendar_is_cut_to_the_months_the_requests_are_in(
        self, manager_client, anna, org,
    ):
        """Not all twelve. The question here is a decision about three specific
        days, and ten empty month blocks around them are ten blocks somebody has
        to look past. The months either side come with it, because "is that week
        already thin" is a question about the fortnight rather than about the
        calendar month it happens to sit in."""
        _book(anna, dt.date(2026, 6, 3), dt.date(2026, 6, 3),
              status=RequestStatus.REQUESTED)
        opened = manager_client.get(f"/absences/requests/?person={anna.pk}")
        assert [block["number"] for block in opened.context["months"]] == [5, 6, 7]

    def test_the_calendar_year_follows_the_request_not_the_clock(
        self, manager_client, anna, org,
    ):
        """A request made in December for January is the ordinary case, and a
        calendar showing this year would have nothing lit on it."""
        year = dt.date.today().year + 1
        _book(anna, dt.date(year, 1, 12), dt.date(year, 1, 12),
              status=RequestStatus.REQUESTED)
        opened = manager_client.get(f"/absences/requests/?person={anna.pk}")
        assert opened.context["calendar_year"] == year

    def test_the_waiting_days_are_the_ones_drawn_as_waiting(
        self, manager_client, anna, org,
    ):
        _book(anna, dt.date(2026, 3, 3), dt.date(2026, 3, 3))
        _book(anna, dt.date(2026, 3, 5), dt.date(2026, 3, 5),
              status=RequestStatus.REQUESTED)
        opened = manager_client.get(f"/absences/requests/?person={anna.pk}")
        march = next(b for b in opened.context["months"] if b["number"] == 3)
        cells = {
            cell["date"]: cell
            for week in march["weeks"] for cell in week if cell
        }
        assert not cells[dt.date(2026, 3, 3)]["is_pending"]
        assert cells[dt.date(2026, 3, 5)]["is_pending"]

    def test_naming_somebody_with_nothing_waiting_falls_back_to_the_tiles(
        self, manager_client, anna, cem, org,
    ):
        """Read out of the *waiting* list rather than looked up by key. A
        ``?person=`` naming somebody with nothing outstanding would otherwise
        render a case with no requests and a calendar with nothing lit on it,
        and leave the manager wondering what they had missed."""
        _book(anna, dt.date(2026, 3, 3), dt.date(2026, 3, 3),
              status=RequestStatus.REQUESTED)
        for raw in (cem.pk, "banana", 99999):
            response = manager_client.get(f"/absences/requests/?person={raw}")
            assert response.context["chosen"] is None
            assert response.context["tiles"]

    def test_deciding_stays_on_the_person_while_they_have_more(
        self, manager_client, anna, org,
    ):
        """The unit is the person and the redirect has to agree. Going back to
        the pile after each press would throw a manager out of the case they are
        in the middle of, three times over, and make them reopen the same
        calendar each time."""
        first = _book(anna, dt.date(2026, 3, 3), dt.date(2026, 3, 3),
                      status=RequestStatus.REQUESTED)
        _book(anna, dt.date(2026, 3, 10), dt.date(2026, 3, 10),
              status=RequestStatus.REQUESTED)

        response = manager_client.post(
            f"/absences/requests/{first.pk}/decide/", {"approve": "1"},
        )
        assert response.url == f"/absences/requests/?person={anna.pk}"

    def test_and_returns_to_the_pile_once_they_are_cleared(
        self, manager_client, anna, org,
    ):
        """A case with nothing left in it is a page about nothing, and the pile
        is where the next one is."""
        only = _book(anna, dt.date(2026, 3, 3), dt.date(2026, 3, 3),
                     status=RequestStatus.REQUESTED)
        response = manager_client.post(
            f"/absences/requests/{only.pk}/decide/", {"approve": "1"},
        )
        assert response.url == "/absences/requests/"
