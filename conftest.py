"""Shared fixtures.

The tests run in English. The app's default language is German, and a test that
asserts on a German string is a test that fails the day somebody improves the
wording of a translation — which is not the thing under test. So the language is
pinned here and assertions are written against the source strings.

The employee fixtures are chosen the same way the demo seed is: to cover the
cases that *differ*, not to look plausible. ``anna`` works five equal days,
``cem`` three unequal ones, and ``dilan`` five short ones — which is the case
that catches an entitlement scaled by hours instead of by days, because she
works half of Anna's hours across the same number of days and is entitled to
exactly the same leave.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import translation


@pytest.fixture(autouse=True)
def forget_sso_configuration():
    """Drop the cached SSO configuration around every test.

    ``apps/accounts/sso.py`` caches it for thirty seconds so that the two
    gunicorn workers are not each running a query per request. In a test run
    that cache spans tests, so one test that saves a configuration decides what
    the next one sees — and the symptom is a suite that passes alone and fails
    in order, which is the worst kind to chase.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def no_outbound_requests(monkeypatch):
    """Nothing in a test run may talk to the network.

    The SSO settings page reads the provider's discovery document *as part of
    saving*, so a test that posts that form would otherwise resolve a real
    hostname — turning a unit test into something that is slow on a good day,
    fails on an aeroplane, and behaves differently in CI than on a laptop.

    The stub fails the way an unreachable provider fails, so the paths that
    handle "discovery did not work" are what runs by default. A test that wants
    a document back installs one with ``discovery_document`` below, which is
    the only way to get an answer out of this.
    """
    import requests

    def refuse(*args, **kwargs):
        raise requests.exceptions.ConnectionError("no network in tests")

    monkeypatch.setattr("apps.accounts.sso_views.requests.get", refuse)
    monkeypatch.setattr("apps.accounts.sso_views.requests.head", refuse)


@pytest.fixture
def discovery_document(monkeypatch):
    """Install a discovery document for the addresses a test names.

    Takes ``{url: document}``; anything not named refuses the connection, which
    is what makes "the first candidate 404s and the second answers" testable.
    """
    import requests

    def install(documents):
        def get(url, **kwargs):
            if url not in documents:
                raise requests.exceptions.ConnectionError("no such host")
            return _Response(documents[url])

        monkeypatch.setattr("apps.accounts.sso_views.requests.get", get)

    return install


class _Response:
    """The two attributes ``_fetch_json`` reads. A real Response is a lot of
    machinery to build for a dict."""

    status_code = 200

    def __init__(self, document):
        import json

        self.content = json.dumps(document).encode()


@pytest.fixture(autouse=True)
def english(settings):
    """Both halves are needed.

    ``LANGUAGE_CODE`` is what ``LocaleMiddleware`` falls back to when a request
    carries no session, cookie or Accept-Language — which is every request the
    test client makes. Without it a rendered page comes back in German however
    much the code around it has overridden the active language, because the
    middleware resolves it again per request.

    ``translation.override`` covers everything outside a request: a form's error
    message, a model's verbose name, a string built in a helper.
    """
    settings.LANGUAGE_CODE = "en"
    with translation.override("en"):
        yield


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------

@pytest.fixture
def user(db):
    """An ordinary signed-in employee."""
    return User.objects.create_user(
        username="anna", password="pw", first_name="Anna",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="bernd", password="pw")


@pytest.fixture
def staff(db):
    """Staff, which in this app means "may administer the software" — not "may
    manage the roster". The two are deliberately different rights; see
    apps/employees/permissions.py."""
    return User.objects.create_user(username="admin", password="pw", is_staff=True)


@pytest.fixture
def client(user):
    """A client that is already signed in, since almost nothing is reachable
    otherwise. Tests about *being* signed out use `anon` below."""
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def anon():
    return Client()


# --------------------------------------------------------------------------
# The organisation
# --------------------------------------------------------------------------

@pytest.fixture
def org(db):
    """Saved settings with the two default break tiers.

    Saved rather than left as the unsaved default, because ``required_break``
    takes a different path when there is no row (it falls back to the module
    constant) and most tests want the stored one — the fallback has a test of
    its own.
    """
    from apps.organisation.models import DEFAULT_BREAK_RULES, BreakRule, OrgSettings

    settings = OrgSettings.current()
    settings.save()
    BreakRule.objects.bulk_create([
        BreakRule(settings=settings, over_minutes=over, break_minutes=length)
        for over, length in DEFAULT_BREAK_RULES
    ])
    return settings


def _employee(first, hours, contract_from=None, **extra):
    """One employee on one contract.

    ``contract_from`` is the date the hours take effect and defaults to well
    before anything a test looks at — the contract is a history now
    (``employees.ContractPeriod``), and a fixture whose period started today
    would give every past date no hours at all, which is a whole suite failing
    for one reason that has nothing to do with what it tests.
    """
    from apps.employees.models import Employee

    # `username` is the directory name — deliberately not the local account
    # name, because in the real deployment they differ and a fixture where they
    # are equal would hide every place the app has to know which is which.
    employee = Employee(first_name=first, last_name="Test",
                        username=f"{first.lower()}.test", **extra)
    employee.save()
    employee.set_hours(
        [Decimal(str(value)) for value in hours],
        valid_from=contract_from or employee.started_on or dt.date(2000, 1, 1),
    )
    return employee


@pytest.fixture
def anna(db, user):
    """Five equal days, full time, with an account. The denominator."""
    return _employee("Anna", [8, 8, 8, 8, 8, 0, 0], user=user)


@pytest.fixture
def cem(db):
    """Three unequal days (8, 8, 4) and no account.

    Both halves matter. The unequal days are what a single "hours per week"
    field cannot express; the missing account is the state every employee is in
    before they have ever signed in, which is the one the roster has to work in
    from day one.
    """
    return _employee("Cem", [8, 8, 4, 0, 0, 0, 0])


@pytest.fixture
def dilan(db):
    """Five short days — half Anna's hours, the same number of days.

    The fixture that catches an entitlement scaled by hours rather than by days.
    Her leave must equal Anna's exactly.
    """
    return _employee("Dilan", [4, 4, 4, 4, 4, 0, 0])


@pytest.fixture
def manager(db):
    """Somebody who manages the roster and is *not* Django staff."""
    account = User.objects.create_user(username="ben", password="pw")
    return _employee("Ben", [8, 8, 0, 8, 8, 0, 0], user=account, is_manager=True)


@pytest.fixture
def manager_client(manager):
    c = Client()
    c.force_login(manager.user)
    return c


@pytest.fixture
def monday(db):
    """A Monday well clear of any real public holiday, so a test that counts
    working days is not quietly changed by the calendar it happens to run on."""
    return dt.date(2026, 3, 2)
