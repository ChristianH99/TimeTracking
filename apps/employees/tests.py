"""The contract, the account behind it, and who may look at somebody else's.

The two things worth the most here are the **link by directory name**, which is
the one automatic action in this app that could sign somebody in as their
colleague, and the **manager/staff split**, which is the permission boundary a
forgotten decorator would quietly open.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from apps.employees.models import Employee
from apps.employees.permissions import is_manager


class TestTheContractIsSevenColumns:
    def test_the_working_days_are_the_days_with_hours(self, cem):
        assert cem.working_days_per_week == 3
        assert cem.weekly_hours == Decimal("20.00")

    def test_a_day_with_no_hours_is_not_a_working_day(self, cem, monday):
        """The question every leave figure turns on. Cem works Monday, Tuesday
        and Wednesday; being away on the Thursday costs him nothing."""
        import datetime as dt

        assert cem.works_on(monday)
        assert not cem.works_on(monday + dt.timedelta(days=3))

    def test_twenty_hours_over_three_days_is_not_the_same_as_over_five(self, org, cem):
        """The case a single "hours per week" field cannot express, and the
        whole reason the contract is seven columns. Both are 20 hours; they are
        different contracts and carry different leave."""
        five_short = Employee.objects.create(
            first_name="Fee", username="fee.test",
        )
        five_short.set_hours([4, 4, 4, 4, 4, 0, 0], valid_from=dt.date(2000, 1, 1))
        assert five_short.weekly_hours == cem.weekly_hours
        assert five_short.working_days_per_week != cem.working_days_per_week
        assert five_short.annual_leave_days(org) != cem.annual_leave_days(org)

    def test_the_pattern_is_always_seven_long(self, cem):
        """A list rather than seven template lookups, so a page cannot render
        six days by forgetting one — which looks fine until the person who works
        Saturdays opens it."""
        assert len(cem.weekly_pattern) == 7
        assert [index for index, _label, _hours in cem.weekly_pattern] == list(range(7))

    def test_somebody_who_has_left_works_no_days(self, anna, monday):
        import datetime as dt

        anna.ended_on = monday - dt.timedelta(days=1)
        anna.save()
        assert not anna.works_on(monday)

    def test_an_override_replaces_the_calculation_rather_than_adding(self, org, cem):
        """A model where both applied would make "30 days" on a contract mean 30
        plus whatever the policy says, and the day somebody raises the full-time
        entitlement every overridden contract would move too."""
        computed = cem.annual_leave_days(org)
        cem.leave_days_override = Decimal("26.0")
        cem.save()
        assert cem.annual_leave_days(org) == Decimal("26.0") != computed

        org.full_time_leave_days = Decimal("40.0")
        org.save()
        assert cem.annual_leave_days(org) == Decimal("26.0")


class TestLinkingAnAccountToAnEmployee:
    """The one automatic action in this app whose wrong answer signs somebody in
    as their colleague.

    The key is the **directory name** — the `preferred_username` the provider
    read out of LDAP — and not an e-mail address. That is a correction rather
    than a preference: an address is something a person may have several of, may
    share with a spouse, and may not have at all, so the address version had to
    refuse to link in exactly the cases a small organisation actually has.
    """

    def test_a_matching_directory_name_links(self, db):
        employee = Employee.objects.create(
            first_name="Anna", username="anna.berger",
        )
        # The local username is the opaque `sub` on a real SSO account, so the
        # directory name is passed in separately — it is what the token carried.
        user = User.objects.create_user("2f1c-9a")
        assert Employee.link_by_username(user, "anna.berger") == employee
        employee.refresh_from_db()
        assert employee.user == user

    def test_it_is_case_insensitive(self, db):
        """A directory does not distinguish `Anna.Berger` from `anna.berger`
        and neither may this."""
        Employee.objects.create(first_name="Anna", username="anna.berger")
        user = User.objects.create_user("2f1c-9a")
        assert Employee.link_by_username(user, "Anna.BERGER") is not None

    def test_a_local_account_falls_back_to_its_own_username(self, db):
        """Right for a local account — somebody typed that name themselves — and
        harmlessly wrong for an SSO one, where the local username is the `sub`
        and simply will not match anything."""
        employee = Employee.objects.create(
            first_name="Anna", username="anna.berger",
        )
        user = User.objects.create_user("anna.berger", password="pw")
        assert Employee.link_by_username(user) == employee

    def test_an_account_with_no_name_links_to_nobody(self, db):
        Employee.objects.create(first_name="Anna", username="anna.berger")
        user = User.objects.create_user("someone")
        assert Employee.link_by_username(user, "") is None

    def test_an_employee_already_linked_is_not_stolen(self, db):
        first = User.objects.create_user("first")
        Employee.objects.create(
            first_name="Anna", username="anna.berger", user=first,
        )
        second = User.objects.create_user("second")
        assert Employee.link_by_username(second, "anna.berger") is None

    def test_an_account_that_already_has_an_employee_is_left_alone(self, db):
        user = User.objects.create_user("anna")
        mine = Employee.objects.create(
            first_name="Anna", username="anna.berger", user=user,
        )
        Employee.objects.create(first_name="Other", username="other.person")
        assert Employee.link_by_username(user, "other.person") is None
        user.refresh_from_db()
        assert user.employee == mine

    def test_two_employees_cannot_claim_one_directory_name(self, db):
        """The ambiguity the e-mail version had to refuse — two people sharing a
        family address — cannot arise, because the database will not hold it.

        That is the whole reason the key changed: what used to be a refusal to
        link is now simply a link.
        """
        from django.db import IntegrityError

        Employee.objects.create(first_name="Anna", username="anna.berger")
        with pytest.raises(IntegrityError):
            Employee.objects.create(
                first_name="Anna", username="Anna.Berger",
            )

    def test_signing_in_makes_the_link(self, db):
        """The moment the whole nullable ``Employee.user`` exists for: a manager
        rosters people before any of them has ever signed in."""
        from django.test import Client

        employee = Employee.objects.create(
            first_name="Zoe", username="zoe.lang",
        )
        User.objects.create_user("zoe.lang", password="pw")

        assert Client().login(username="zoe.lang", password="pw")
        employee.refresh_from_db()
        assert employee.user is not None

    def test_a_failure_never_breaks_the_login(self, db, monkeypatch):
        """This runs inside the login transaction, including the OIDC callback,
        where an exception is a sign-in that fails with no explanation and no
        way round it. A missed link is a page saying "no contract"; a raised
        exception is an app nobody can get into."""
        from django.test import Client

        def explode(user, directory_name=None):
            raise RuntimeError("boom")

        monkeypatch.setattr(Employee, "link_by_username", staticmethod(explode))
        User.objects.create_user("zoe.lang", password="pw")
        assert Client().login(username="zoe.lang", password="pw")


class TestTheSuggestedSignInName:
    """Filled in when somebody types a name, and never applied behind their back
    — the directory is the authority on what an account is called."""

    @pytest.mark.parametrize("first, last, expected", [
        ("Anna", "Berger", "anna.berger"),
        ("Jürgen", "Müller", "juergen.mueller"),
        ("Ömer", "Öztürk", "oemer.oeztuerk"),
        ("Hans-Peter", "Groß", "hans-peter.gross"),
        ("René", "Åberg", "rene.aberg"),
        ("Anna", "", "anna"),
        ("", "", ""),
    ])
    def test_it_transliterates_rather_than_dropping(self, first, last, expected):
        """ä becomes ae the way German directories do it, not nothing —
        `mller` is nobody's account name."""
        assert Employee.suggest_username(first, last) == expected


class TestAnEmployeeWithoutAnAccount:
    def test_they_can_still_be_rostered_and_given_leave(self, org, cem, monday):
        """The state the roster has to work in from day one."""
        import datetime as dt

        from apps.absences.models import Absence, AbsenceKind, RequestStatus
        from apps.roster.models import Shift

        assert cem.user is None
        Shift.objects.create(employee=cem, date=monday,
                             start=dt.time(8, 0), end=dt.time(16, 0))
        Absence.objects.create(
            employee=cem, kind=AbsenceKind.HOLIDAY,
            start_date=monday, end_date=monday, status=RequestStatus.APPROVED,
        )
        assert cem.shifts.count() == 1
        assert cem.absences.get().working_days() == 1

    def test_deleting_the_account_keeps_the_employee_and_the_hours(self, org, anna, monday):
        """``SET_NULL``, not ``CASCADE``. Somebody who has left still worked the
        hours and payroll may need them for years — an app that discarded them
        because an account was tidied up would destroy the only record."""
        import datetime as dt

        from apps.timesheets.models import DayRecord, WorkSegment

        record = DayRecord.objects.create(employee=anna, date=monday)
        WorkSegment.objects.create(day=record, start=dt.time(8, 0), end=dt.time(16, 0))

        anna.user.delete()
        anna.refresh_from_db()
        assert anna.user is None
        assert anna.days.get().gross_minutes == 480

    def test_a_signed_in_account_with_no_contract_gets_a_page_not_a_crash(self, client, user, org):
        """A real state — an administrator who does not work shifts — and the
        day somebody in that position clicks Time off is not a day this app
        should fall over.

        Note that the ``anna`` fixture is deliberately *not* requested: it is
        what would give this account a contract.
        """
        assert Employee.for_user(user) is None
        assert client.get("/absences/").status_code == 200
        assert client.get("/").status_code == 200
        assert client.get("/timesheet/").status_code == 200


class TestWhoManagesTheRoster:
    """Manager and staff are different rights, and conflating them is the
    mistake this app is arranged to avoid: a deputy head plans the roster and
    must not create logins; whoever administers the NAS has every login right
    and may never have met the staff."""

    def test_a_manager_is_not_staff(self, manager):
        assert is_manager(manager.user)
        assert not manager.user.is_staff

    def test_staff_alone_does_not_manage_the_roster(self, staff, db):
        assert not is_manager(staff)

    def test_a_superuser_always_can(self, db):
        """An app whose only manager has left has to be recoverable without a
        shell on the NAS."""
        root = User.objects.create_user("root", password="pw", is_superuser=True)
        assert is_manager(root)

    def test_a_manager_who_has_left_no_longer_can(self, manager):
        manager.is_active = False
        manager.save()
        assert not is_manager(manager.user)


def _routes(namespace):
    found = []

    def walk(resolver, app_name):
        for entry in resolver.url_patterns:
            if isinstance(entry, URLResolver):
                walk(entry, entry.app_name or app_name)
            elif isinstance(entry, URLPattern) and entry.name and app_name == namespace:
                found.append(entry)

    walk(get_resolver(), "")
    return found


def _url_for(namespace, pattern, pk):
    """Reverse one discovered route, whatever shape its arguments are.

    Tries progressively more arguments rather than one shape and a bare
    fallback. **A route this cannot reverse must fail the test, not be skipped**
    — skipping is how a two-argument route added next month quietly stops being
    checked, which is precisely the exposure the sweep exists to catch. So the
    caller raises on ``None`` instead of moving on.

    The values are deliberately plausible-but-harmless: an id that exists and a
    date that parses. A route that 404s because the *object* is missing would
    pass this test for the wrong reason.
    """
    import datetime as dt

    today = dt.date.today().isoformat()
    for args in ([], [pk], [pk, pk], [pk, today], [pk, pk, pk]):
        try:
            return reverse(f"{namespace}:{pattern.name}", args=args)
        except Exception:  # noqa: BLE001 - the wrong arity is the only reason
            continue
    return None


@pytest.mark.parametrize("namespace", ["employees", "roster"])
def test_every_manager_route_refuses_an_ordinary_employee(client, db, org, anna, namespace):
    """Discovered from the URLconf rather than listed, so a page added next
    month is covered the day it lands — which is the point, since the exposure
    is a decorator somebody forgets on a *new* view."""
    patterns = _routes(namespace)
    assert patterns, f"no routes found for {namespace} — the walk is broken"

    for pattern in patterns:
        url = _url_for(namespace, pattern, anna.pk)
        assert url is not None, (
            f"{namespace}:{pattern.name} could not be reversed, so it is not being "
            "checked at all. Teach _url_for its argument shape rather than letting "
            "an unchecked route through."
        )
        # Both verbs. A POST-only route answers a GET with 405 from
        # @require_POST *before* the permission check runs, which would make a
        # GET-only sweep pass for entirely the wrong reason.
        for response in (client.get(url), client.post(url)):
            assert response.status_code == 404, (
                f"{namespace}:{pattern.name} answered {response.status_code} to an "
                "ordinary employee — it is missing @manager_required"
            )


def test_the_team_timesheet_routes_refuse_an_ordinary_employee(client, db, org, anna):
    """Not covered by the sweep above, because those routes live in the
    ``timesheets`` namespace alongside the ones every employee may reach."""
    import datetime as dt

    today = dt.date.today().isoformat()
    # anna *is* the signed-in employee, so her own pk would legitimately be
    # allowed. Somebody else's is the real test.
    other = Employee.objects.create(first_name="Other", username="other.test")

    for name, args, method in (
        ("team", [], "get"),
        ("employee", [other.pk], "get"),
        ("employee-day", [other.pk, today], "get"),
        # POST-only, so a GET is refused with 405 by @require_POST before the
        # permission check ever runs — which would make a GET here pass for
        # entirely the wrong reason.
        ("employee-confirm-day", [other.pk, today], "post"),
    ):
        url = reverse(f"timesheets:{name}", args=args)
        response = getattr(client, method)(url)
        assert response.status_code == 404, (
            f"timesheets:{name} answered {response.status_code} to an ordinary "
            "employee asking about somebody else"
        )
