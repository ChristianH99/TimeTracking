"""Nobody sees anybody else's time unless they are a manager.

Written as a **sweep rather than a list**, for the same reason
``test_every_manager_route_refuses_an_ordinary_employee`` is: the exposure is
never a check somebody removed, it is a check somebody forgot on a page added
last Tuesday. A list of routes is a list that stops being complete the moment
the app grows, and stops being complete silently.

The three doors this walks are the three the app has, and they answer different
questions:

* **``LoginRequiredMiddleware``** — is anybody signed in at all. Gated on an
  enumerated open list rather than per-view decorators, because a forgotten
  decorator leaves a page that answers to the world and looks completely normal.
* **``own_or_manager``** — may *this* account see *this* person's time.
* **``manager_required`` / ``staff_required``** — may they plan the roster, or
  administer the software. Different sets of people, deliberately.

Every one of them answers **404 rather than 403**. There is nothing to conceal
either way, since the links are only in the sidebar for the people who may
follow them, and a bare 403 is a dead end with no way back into the app.
"""

import datetime as dt

import pytest
from django.contrib.auth.models import User
from django.urls import URLPattern, URLResolver, get_resolver

from apps.absences.carryover import LeaveCarryOver
from apps.absences.models import Absence, AbsenceKind, RequestStatus
from apps.employees.models import Employee
from apps.timesheets.models import DayRecord, WorkSegment


def _all_routes():
    """Every named route in the project, with its namespace."""
    found = []

    def walk(resolver, app_name):
        for entry in resolver.url_patterns:
            if isinstance(entry, URLResolver):
                walk(entry, entry.app_name or app_name)
            elif isinstance(entry, URLPattern) and entry.name:
                found.append((app_name, entry))

    walk(get_resolver(), "")
    return found


@pytest.fixture
def other(db):
    """Somebody who is not the signed-in employee, with hours on the record.

    Given a real day and a real absence, because a route that 404s for want of
    an *object* would pass an access-control test for entirely the wrong reason.
    """
    person = Employee.objects.create(first_name="Other", username="other.person")
    person.set_hours([8, 8, 8, 8, 8, 0, 0], valid_from=dt.date(2000, 1, 1))
    record = DayRecord.objects.create(employee=person, date=dt.date.today())
    WorkSegment.objects.create(day=record, start=dt.time(8), end=dt.time(16))
    Absence.objects.create(
        employee=person, kind=AbsenceKind.HOLIDAY,
        start_date=dt.date.today(), end_date=dt.date.today(),
        status=RequestStatus.REQUESTED,
    )
    LeaveCarryOver.objects.create(
        employee=person, year=dt.date.today().year, statutory_days=5,
    )
    return person


class TestSomebodyElsesTime:
    """The rule every timesheet and absence view shares."""

    def test_an_employee_cannot_open_another_persons_week(self, org, anna, other, client):
        assert client.get(f"/team/{other.pk}/").status_code == 404

    def test_an_employee_cannot_open_another_persons_day(self, org, anna, other, client):
        today = dt.date.today().isoformat()
        assert client.get(f"/team/{other.pk}/{today}/").status_code == 404
        assert client.get(f"/timesheet/{other.pk}/{today}/").status_code == 404

    def test_an_employee_cannot_clock_another_person_in(self, org, anna, other, client):
        assert client.post(f"/timesheet/{other.pk}/clock/").status_code == 404
        assert not WorkSegment.objects.filter(day__employee=other, end__isnull=True).exists()

    def test_an_employee_cannot_confirm_another_persons_day(self, org, anna, other, client):
        today = dt.date.today().isoformat()
        assert client.post(f"/timesheet/{other.pk}/{today}/confirm/").status_code == 404

    def test_an_employee_cannot_see_another_persons_leave(self, org, anna, other, client):
        assert client.get(f"/employees/{other.pk}/leave/").status_code == 404

    def test_an_employee_cannot_decide_a_request(self, org, anna, other, client):
        waiting = other.absences.get()
        response = client.post(f"/absences/requests/{waiting.pk}/decide/", {"approve": "1"})
        assert response.status_code == 404
        waiting.refresh_from_db()
        assert waiting.status == RequestStatus.REQUESTED

    def test_an_employee_cannot_withdraw_another_persons_request(
        self, org, anna, other, client,
    ):
        """Scoped by ``employee=`` on the lookup rather than by a check
        afterwards, so the row is not even fetched. A 404 here means "not one of
        yours", which is exactly what it is."""
        waiting = other.absences.get()
        assert client.post(f"/absences/requests/{waiting.pk}/cancel/").status_code == 404
        waiting.refresh_from_db()
        assert waiting.status == RequestStatus.REQUESTED

    def test_an_employee_cannot_extend_another_persons_deadline(
        self, org, anna, other, client,
    ):
        carried = other.carried_leave.get()
        response = client.post(
            f"/absences/year-end/{carried.pk}/extend/",
            {"statutory_deadline": "2030-01-01", "extension_reason": "because"},
        )
        assert response.status_code == 404
        carried.refresh_from_db()
        assert carried.statutory_deadline is None

    def test_an_employee_cannot_change_another_persons_contract(
        self, org, anna, other, client,
    ):
        response = client.post(f"/employees/{other.pk}/contract/", {
            "valid_from": dt.date.today().isoformat(), "hours_mon": "1",
        })
        assert response.status_code == 404
        assert other.contract_periods.count() == 1

    def test_a_manager_can(self, org, manager, manager_client, other):
        """The other half. A rule that refused everybody would pass every test
        above and make the app useless, so the permission is asserted from both
        sides."""
        assert manager_client.get(f"/team/{other.pk}/").status_code == 200
        assert manager_client.get(f"/employees/{other.pk}/leave/").status_code == 200


class TestYourOwnTimeIsAlwaysYours:
    def test_an_employee_reaches_their_own_pages(self, org, anna, client):
        today = dt.date.today().isoformat()
        assert client.get(f"/timesheet/{anna.pk}/{today}/").status_code == 200
        assert client.get("/timesheet/").status_code == 200
        assert client.get("/absences/").status_code == 200


class TestAnUnlinkedEmployeeIsNobodys:
    def test_a_null_account_does_not_match_a_null_account(self, org, anna, client, db):
        """``own_or_manager`` checks ``user_id is not None`` before comparing.

        With both sides null a bare ``==`` is True, which would hand every
        not-yet-signed-in employee's timesheet to anybody with an account — and
        on day one that is the entire team.
        """
        from apps.employees.permissions import own_or_manager

        stranger = Employee.objects.create(first_name="Nobody", username="nobody.test")
        assert stranger.user_id is None

        class _Request:
            user = User(pk=None)

        blank = _Request()
        blank.user = User.objects.create_user("blank")
        assert not own_or_manager(blank, stranger)


class TestNothingAnswersTheWorld:
    """Every route either needs a login or is on the enumerated open list.

    Discovered from the URLconf, so a page added next month is covered the day
    it lands. The open list is ``apps/accounts/pages.py`` and it is a *list*
    precisely so that adding to it is a decision somebody makes on purpose.
    """

    def test_every_route_needs_a_login_or_says_it_does_not(self, db, org):
        from django.test import Client

        from apps.accounts.pages import OPEN

        anonymous = Client()
        today = dt.date.today().isoformat()
        checked = 0

        for namespace, pattern in _all_routes():
            if namespace == "admin":
                # Django's own admin has its own gate, and walking it would be
                # testing Django rather than this app.
                continue
            name = f"{namespace}:{pattern.name}" if namespace else pattern.name
            if (namespace, pattern.name) in OPEN:
                continue

            from django.urls import reverse

            url = None
            for args in ([], [1], [1, 1], [1, today]):
                try:
                    url = reverse(name, args=args)
                    break
                except Exception:  # noqa: BLE001 - the wrong arity is the reason
                    continue
            if url is None:
                continue

            checked += 1
            for response in (anonymous.get(url), anonymous.post(url)):
                assert response.status_code in (302, 404, 405), (
                    f"{name} answered {response.status_code} to nobody at all. "
                    "Either it needs the login gate or it belongs on the open list "
                    "in apps/accounts/pages.py — and that is a decision, not an "
                    "oversight."
                )
                if response.status_code == 302:
                    assert "/accounts/" in response["Location"] or "login" in response["Location"], (
                        f"{name} redirected somewhere other than sign-in"
                    )

        assert checked > 20, "the sweep found almost nothing, so it is broken"
