"""The planner in a real browser.

Everything in ``tests.py`` drives the server with the POST a browser *would*
send. This file checks the browser actually sends it: that a drag moves the row
and rewrites its one hidden input, that typing a name places a person and
leaves the rest as text, that the times dialog writes only what differs, and
that the list under the grid follows along. None of that can fail in a way the
Django test client would see — the page renders, and the roster saved is
simply not the one on the screen.

Optional, because it needs a browser. Run with:

    uv run --with playwright pytest apps/roster/test_browser.py

It uses an installed Chrome or Edge (``ROSTER_BROWSER_CHANNEL``, default
``msedge``) rather than downloading one, and skips — loudly, with the reason —
when neither Playwright nor a browser is available. ``collectstatic`` must have
been run since the last edit to a script, as for the rest of the suite: the
pages load the hashed files.
"""

import datetime as dt
import os
import re
from decimal import Decimal

import pytest
from django.test import Client

# Playwright's synchronous API keeps an event loop running on the test's own
# thread, and Django refuses database access from any thread with a running
# loop. The test talks to the database synchronously and on purpose, so the
# guard is switched off for this module, which is what Django documents it for.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed (uv run --with playwright ...)")

from apps.absences.models import Absence, AbsenceKind, RequestStatus  # noqa: E402
from apps.employees.models import Employee  # noqa: E402
from apps.roster.models import Area, AreaIcon, CellNote, Shift, TimeSlot  # noqa: E402

T = dt.time

pytestmark = pytest.mark.django_db(transaction=True)


# --------------------------------------------------------------------------
# The browser
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser():
    channel = os.environ.get("ROSTER_BROWSER_CHANNEL", "msedge")
    with playwright_api.sync_playwright() as p:
        try:
            instance = p.chromium.launch(channel=channel, headless=True)
        except Exception as error:  # noqa: BLE001 - any launch failure means "no browser here"
            pytest.skip(f"no {channel} browser to drive: {error}")
        yield instance
        instance.close()


@pytest.fixture(autouse=True)
def unhashed_static(settings):
    """Plain static names for the live server.

    The live server answers ``/static/`` through the staticfiles *finders*,
    which know ``roster_plan.js`` and not ``roster_plan.3f2a….js`` — so with the
    manifest storage every script 404s and the page is silently inert, which is
    exactly the failure this file exists to catch, caused by the harness.
    """
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def page(browser, live_server, manager):
    """A signed-in manager's page, failing the test on any script error.

    A script error is the one failure that leaves this page looking perfectly
    normal, which is why it is collected for every test rather than checked in
    one.
    """
    client = Client()
    client.force_login(manager.user)
    session = client.cookies["sessionid"].value
    context = browser.new_context(locale="en-GB", viewport={"width": 1500, "height": 1000})
    context.add_cookies([{
        "name": "sessionid", "value": session, "url": live_server.url,
    }])
    tab = context.new_page()
    problems = []
    tab.on("pageerror", lambda error: problems.append(str(error)))
    tab.on("console", lambda message: problems.append(message.text)
           if message.type == "error" else None)
    tab.live_server = live_server
    yield tab
    context.close()
    assert not problems, f"the page logged errors: {problems}"


def open_week(page, monday, **params):
    query = "&".join([f"week={monday.isoformat()}"] + [f"{k}={v}" for k, v in params.items()])
    page.goto(f"{page.live_server.url}/roster/?{query}")
    page.wait_for_selector("[data-grid-body]", state="attached")


def save(page):
    with page.expect_navigation():
        page.click(".form-actions button[type=submit]")
    assert page.locator(".notice--success, .messages .notice").first.is_visible()


def drag(page, source, target, copy=False):
    """A real pointer drag: press, move in steps, release."""
    start = source.bounding_box()
    end = target.bounding_box()
    page.mouse.move(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
    page.mouse.down()
    page.mouse.move(start["x"] + start["width"] / 2 + 10, start["y"] + start["height"] / 2 + 10, steps=3)
    page.mouse.move(end["x"] + end["width"] / 2, end["y"] + min(end["height"] / 2, 20), steps=8)
    if copy:
        page.keyboard.down("Control")
    page.mouse.up()
    if copy:
        page.keyboard.up("Control")


def cell(page, slot, day, area=None):
    return page.locator(f'[data-cell="{slot}|{day.isoformat()}|{area or ""}"]')


def chips_in(page, slot, day, area=None):
    return [text.strip() for text in
            cell(page, slot, day, area).locator("[data-chip-label]").all_inner_texts()]


def pool(page, day):
    return page.locator(f'[data-pool="{day.isoformat()}"]')


def pool_names(page, day):
    return pool(page, day).locator(".rpool-chip").all_inner_texts()


# --------------------------------------------------------------------------
# A week to plan
# --------------------------------------------------------------------------

@pytest.fixture
def week(org, monday, anna, cem, dilan, manager):
    """Monday's grid: an early slot, a morning split into two rooms, lunch.

    Anna in room 1, Dilan in the early slot from 07:30, and the word "Break" in
    Monday's lunch cell.
    """
    one = Area.objects.create(name="Room 1", icon=AreaIcon.STAR, position=1)
    two = Area.objects.create(name="Room 2", icon=AreaIcon.MOON, position=2)
    early = TimeSlot.objects.create(week=monday, start=T(7, 15), end=T(8, 0))
    morning = TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(12, 0))
    morning.areas.set([one, two])
    lunch = TimeSlot.objects.create(week=monday, start=T(12, 0), end=T(12, 30))
    anna_shift = Shift.objects.create(employee=anna, date=monday, slot=morning, area=one,
                                      start=T(8, 0), end=T(12, 0))
    Shift.objects.create(employee=dilan, date=monday, slot=early, start=T(7, 30), end=T(8, 0))
    CellNote.objects.create(slot=lunch, date=monday, text="Break")
    return {"one": one, "two": two, "early": early, "morning": morning, "lunch": lunch,
            "anna_shift": anna_shift}


# --------------------------------------------------------------------------
# What the page draws
# --------------------------------------------------------------------------

class TestTheGrid:
    def test_rows_are_slots_and_areas(self, page, week, monday):
        open_week(page, monday)
        # early (1 row) + morning split in two (2 rows) + lunch (1 row)
        assert page.locator("[data-grid-body] tr").count() == 4
        assert page.locator(".rgrid-area").all_inner_texts() == ["Room 1", "Room 2"]
        # The slots come out in clock order whatever order they arrived in.
        starts = page.locator("[data-grid-body] .rgrid-time input[name$='-start']")
        assert [starts.nth(i).input_value() for i in range(starts.count())] == ["07:15", "08:00", "12:00"]

    def test_every_cell_has_a_box_and_names_are_where_their_rows_say(self, page, week, monday):
        open_week(page, monday)
        assert page.locator("[data-grid-body] [data-cell]").count() == 4 * 5
        assert page.locator("[data-grid-body] [data-cell] [data-cell-input]").count() == 4 * 5
        assert chips_in(page, week["morning"].pk, monday, week["one"].pk) == ["Anna"]

    def test_only_the_time_that_differs_is_written(self, page, week, monday):
        open_week(page, monday)
        assert chips_in(page, week["early"].pk, monday) == ["Dilan (07:30)"]

    def test_text_is_shown_in_its_cell(self, page, week, monday):
        open_week(page, monday)
        assert cell(page, week["lunch"].pk, monday).locator("[data-cell-input]").input_value() == "Break"

    def test_the_list_under_the_grid_is_who_is_not_placed(self, page, week, monday):
        open_week(page, monday)
        # Monday: Anna and Dilan are placed; Cem and Ben are not.
        assert pool_names(page, monday) == ["Ben", "Cem"]
        # Tuesday: nobody is placed.
        assert sorted(pool_names(page, monday + dt.timedelta(days=1))) == ["Anna", "Ben", "Cem", "Dilan"]

    def test_no_hours_that_day_is_lighter_and_last(self, page, week, monday):
        open_week(page, monday)
        thursday = monday + dt.timedelta(days=3)
        cem_chip = pool(page, thursday).locator(".rpool-chip", has_text="Cem")
        assert "is-off" in cem_chip.get_attribute("class")
        assert pool_names(page, thursday)[-1] == "Cem"

    def test_somebody_away_is_red_in_the_list_and_in_a_cell(self, page, week, monday, cem, anna):
        Absence.objects.create(employee=cem, kind=AbsenceKind.SICK, start_date=monday,
                               end_date=monday, status=RequestStatus.REQUESTED)
        Absence.objects.create(employee=anna, kind=AbsenceKind.HOLIDAY, start_date=monday,
                               end_date=monday, status=RequestStatus.REQUESTED)
        open_week(page, monday)
        cem_chip = pool(page, monday).locator(".rpool-chip", has_text="Cem")
        assert "is-away" in cem_chip.get_attribute("class")
        assert "is-pending" not in cem_chip.get_attribute("class")
        anna_chip = cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]")
        assert "is-away" in anna_chip.get_attribute("class")
        assert "is-pending" in anna_chip.get_attribute("class")
        colour = cem_chip.evaluate("el => getComputedStyle(el).color")
        assert colour == "rgb(179, 38, 30)"            # --away, which is --danger's red

    def test_icons_come_from_the_sprite(self, page, week, monday):
        open_week(page, monday)
        href = page.locator(".rgrid-area use").first.get_attribute("href")
        assert re.search(r"/static/icons/areas(\.[0-9a-f]+)?\.svg#star$", href)


# --------------------------------------------------------------------------
# Placing people
# --------------------------------------------------------------------------

class TestDragging:
    def test_from_the_list_into_a_cell(self, page, week, monday, cem):
        open_week(page, monday)
        drag(page, pool(page, monday).locator(".rpool-chip", has_text="Cem"),
             cell(page, week["morning"].pk, monday, week["two"].pk))
        assert chips_in(page, week["morning"].pk, monday, week["two"].pk) == ["Cem"]
        assert "Cem" not in pool_names(page, monday)
        save(page)
        shift = Shift.objects.get(employee=cem)
        assert (shift.date, shift.slot, shift.area, shift.start, shift.end) == (
            monday, week["morning"], week["two"], T(8, 0), T(12, 0))

    def test_between_cells_moves_the_same_row(self, page, week, monday):
        open_week(page, monday)
        wednesday = monday + dt.timedelta(days=2)
        drag(page, cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]"),
             cell(page, week["morning"].pk, wednesday, week["two"].pk))
        assert chips_in(page, week["morning"].pk, monday, week["one"].pk) == []
        assert chips_in(page, week["morning"].pk, wednesday, week["two"].pk) == ["Anna"]
        save(page)
        moved = Shift.objects.get(pk=week["anna_shift"].pk)
        assert (moved.date, moved.area) == (wednesday, week["two"])

    def test_with_ctrl_held_it_copies(self, page, week, monday, anna):
        open_week(page, monday)
        tuesday = monday + dt.timedelta(days=1)
        drag(page, cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]"),
             cell(page, week["morning"].pk, tuesday, week["one"].pk), copy=True)
        assert chips_in(page, week["morning"].pk, monday, week["one"].pk) == ["Anna"]
        assert chips_in(page, week["morning"].pk, tuesday, week["one"].pk) == ["Anna"]
        save(page)
        assert Shift.objects.filter(employee=anna).count() == 2

    def test_own_times_go_when_moved_to_another_slot(self, page, week, monday, dilan):
        open_week(page, monday)
        drag(page, cell(page, week["early"].pk, monday).locator("[data-placement]"),
             cell(page, week["lunch"].pk, monday))
        assert chips_in(page, week["lunch"].pk, monday) == ["Dilan"]
        save(page)
        shift = Shift.objects.get(employee=dilan)
        assert (shift.start, shift.end) == (T(12, 0), T(12, 30))

    def test_back_to_the_list_takes_them_out(self, page, week, monday):
        open_week(page, monday)
        drag(page, cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]"),
             pool(page, monday))
        assert "Anna" in pool_names(page, monday)
        save(page)
        assert not Shift.objects.filter(pk=week["anna_shift"].pk).exists()

    def test_two_places_at_once_is_marked_while_dragging(self, page, week, monday):
        open_week(page, monday)
        drag(page, cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]"),
             cell(page, week["morning"].pk, monday, week["two"].pk), copy=True)
        chips = page.locator("[data-grid-body] [data-placement].is-clash")
        assert chips.count() == 2


class TestTyping:
    def test_a_name_from_the_suggestions_places_the_person(self, page, week, monday, cem):
        open_week(page, monday)
        box = cell(page, week["lunch"].pk, monday).locator("[data-cell-input]")
        box.click()
        box.press("End")
        box.type(" Ce")
        options = page.locator("#roster-suggest [role=option]")
        assert options.first.inner_text().startswith("Cem Test")
        box.press("Enter")
        assert chips_in(page, week["lunch"].pk, monday) == ["Cem"]
        assert box.input_value() == "Break"               # the typed name came back out
        save(page)
        assert Shift.objects.get(employee=cem).slot == week["lunch"]
        assert CellNote.objects.get(slot=week["lunch"]).text == "Break"

    def test_text_alone_stays_text(self, page, week, monday):
        open_week(page, monday)
        tuesday = monday + dt.timedelta(days=1)
        box = cell(page, week["lunch"].pk, tuesday).locator("[data-cell-input]")
        box.fill("Outing")
        box.press("Enter")                             # must not save the page
        assert page.url.endswith(f"week={monday.isoformat()}")
        save(page)
        assert CellNote.objects.get(date=tuesday).text == "Outing"

    def test_somebody_already_in_the_cell_is_not_suggested(self, page, week, monday):
        open_week(page, monday)
        box = cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-cell-input]")
        box.click()
        box.type("Ann")
        assert page.locator("#roster-suggest").is_hidden()

    def test_umlauts_and_case_do_not_matter(self, page, week, monday):
        Employee.objects.create(first_name="Jürgen", last_name="Öz", username="joez").set_hours(
            [Decimal(8)] * 5 + [Decimal(0)] * 2, valid_from=dt.date(2000, 1, 1))
        open_week(page, monday)
        box = cell(page, week["lunch"].pk, monday + dt.timedelta(days=1)).locator("[data-cell-input]")
        box.click()
        box.type("oz")
        assert page.locator("#roster-suggest [role=option]").first.inner_text().startswith("Jürgen Öz")

    def test_away_people_are_offered_last_and_in_red(self, page, week, monday, cem):
        Absence.objects.create(employee=cem, kind=AbsenceKind.HOLIDAY, start_date=monday,
                               end_date=monday, status=RequestStatus.APPROVED)
        open_week(page, monday)
        box = cell(page, week["lunch"].pk, monday).locator("[data-cell-input]")
        box.fill("")
        box.type("t")                                   # every fixture's surname is "Test"
        options = page.locator("#roster-suggest [role=option]")
        classes = [options.nth(i).get_attribute("class") for i in range(options.count())]
        away = [c for c in classes if "is-away" in c]
        assert away and classes[-len(away):] == away


class TestOwnTimes:
    def _open(self, page, chip):
        chip.click(button="right")
        page.wait_for_selector("[data-times-modal]:not([hidden])")

    def test_right_click_writes_only_the_start_that_differs(self, page, week, monday):
        open_week(page, monday)
        chip = cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]")
        self._open(page, chip)
        page.fill("[data-times-start]", "830")
        page.click("[data-times-form] button[type=submit]")
        assert chips_in(page, week["morning"].pk, monday, week["one"].pk) == ["Anna (08:30)"]
        save(page)
        shift = Shift.objects.get(pk=week["anna_shift"].pk)
        assert (shift.start, shift.end) == (T(8, 30), T(12, 0))

    def test_an_end_alone_is_written_after_a_dash(self, page, week, monday):
        open_week(page, monday)
        chip = cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]")
        self._open(page, chip)
        page.fill("[data-times-end]", "11:45")
        page.click("[data-times-form] button[type=submit]")
        assert chips_in(page, week["morning"].pk, monday, week["one"].pk) == ["Anna (–11:45)"]

    def test_both_differ_both_are_written(self, page, week, monday):
        open_week(page, monday)
        chip = cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]")
        self._open(page, chip)
        page.fill("[data-times-start]", "8:15")
        page.fill("[data-times-end]", "11,5")
        page.click("[data-times-form] button[type=submit]")
        assert chips_in(page, week["morning"].pk, monday, week["one"].pk) == ["Anna (08:15–11:30)"]

    def test_enter_in_a_box_applies_what_was_typed(self, page, week, monday):
        open_week(page, monday)
        self._open(page, cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]"))
        page.fill("[data-times-start]", "915")
        page.press("[data-times-start]", "Enter")
        assert page.locator("[data-times-modal]").is_hidden()
        assert chips_in(page, week["morning"].pk, monday, week["one"].pk) == ["Anna (09:15)"]

    def test_back_to_the_range(self, page, week, monday, dilan):
        open_week(page, monday)
        self._open(page, cell(page, week["early"].pk, monday).locator("[data-placement]"))
        assert page.input_value("[data-times-start]") == "07:30"
        page.click("[data-times-reset]")
        assert chips_in(page, week["early"].pk, monday) == ["Dilan"]
        save(page)
        assert Shift.objects.get(employee=dilan).start == T(7, 15)

    def test_a_time_with_no_length_is_refused_in_the_dialog(self, page, week, monday):
        open_week(page, monday)
        self._open(page, cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]"))
        page.fill("[data-times-start]", "12:00")
        page.click("[data-times-form] button[type=submit]")
        assert page.locator("[data-times-error]").is_visible()
        assert page.locator("[data-times-modal]").is_visible()

    def test_a_long_press_on_a_touch_screen_opens_it(self, page, week, monday):
        open_week(page, monday)
        chip = cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]")
        chip.dispatch_event("pointerdown", {
            "pointerType": "touch", "pointerId": 7, "button": 0, "isPrimary": True, "bubbles": True,
        })
        page.wait_for_selector("[data-times-modal]:not([hidden])", timeout=2000)

    def test_from_the_keyboard(self, page, week, monday):
        open_week(page, monday)
        chip = cell(page, week["morning"].pk, monday, week["one"].pk).locator("[data-placement]")
        chip.focus()
        page.keyboard.press("Enter")
        page.wait_for_selector("[data-times-modal]:not([hidden])")
        page.keyboard.press("Escape")
        chip.focus()
        page.keyboard.press("Delete")
        assert chips_in(page, week["morning"].pk, monday, week["one"].pk) == []


# --------------------------------------------------------------------------
# Changing the rows
# --------------------------------------------------------------------------

class TestTimeRanges:
    def test_adding_a_range_and_filling_it_before_the_first_save(self, page, week, monday, cem):
        open_week(page, monday)
        page.click("[data-slot-add]")
        new_row = page.locator("[data-grid-body] tr").last
        assert new_row.locator("input[name$='-start']").input_value() == "12:30"
        assert new_row.locator("input[name$='-end']").input_value() == "13:30"
        key = new_row.locator("input[name$='-key']").input_value()
        assert key.startswith("new-")
        box = cell(page, key, monday).locator("[data-cell-input]")
        box.click()
        box.type("Cem")
        box.press("Enter")
        save(page)
        slot = TimeSlot.objects.get(week=monday, start=T(12, 30))
        assert Shift.objects.get(employee=cem).slot == slot

    def test_editing_a_range_reorders_and_relabels(self, page, week, monday):
        open_week(page, monday)
        start = page.locator("[data-grid-body] input[name$='-start']").last    # lunch, 12:00
        start.fill("615")
        page.locator("[data-grid-body] input[name$='-end']").last.click()        # leave the box
        page.wait_for_function(
            "() => document.querySelector('[data-grid-body] tr input[name$=\"-start\"]').value === '06:15'")
        # Dilan's own start is 07:30, still inside her slot's new reading.
        assert chips_in(page, week["early"].pk, monday) == ["Dilan (07:30)"]

    def test_splitting_a_range_moves_its_people_into_the_first_area(self, page, week, monday):
        open_week(page, monday)
        lunch_row = page.locator(f'[data-cell^="{week["lunch"].pk}|"]').first.locator("xpath=..")
        lunch_row.locator("[data-slot-areas] summary").click()
        lunch_row.locator(f'[data-area-choice="{week["two"].pk}"] input').check()
        assert cell(page, week["lunch"].pk, monday, week["two"].pk).count() == 1
        assert cell(page, week["lunch"].pk, monday).count() == 0
        save(page)
        assert list(TimeSlot.objects.get(pk=week["lunch"].pk).areas.all()) == [week["two"]]

    def test_unsplitting_keeps_the_people(self, page, week, monday, anna):
        open_week(page, monday)
        row = cell(page, week["morning"].pk, monday, week["one"].pk).locator("xpath=..")
        row.locator("[data-slot-areas] summary").click()
        row.locator(f'[data-area-choice="{week["one"].pk}"] input').uncheck()
        row = cell(page, week["morning"].pk, monday, week["two"].pk).locator("xpath=..")
        row.locator(f'[data-area-choice="{week["two"].pk}"] input').uncheck()
        assert chips_in(page, week["morning"].pk, monday) == ["Anna"]
        save(page)
        shift = Shift.objects.get(pk=week["anna_shift"].pk)
        assert shift.area is None

    def test_removing_a_range_asks_and_takes_its_people(self, page, week, monday):
        open_week(page, monday)
        row = cell(page, week["early"].pk, monday).locator("xpath=..")
        row.locator("[data-slot-remove]").click()
        page.wait_for_selector("[data-app-dialog]:not([hidden])")
        page.click("[data-dialog-accept]")
        assert cell(page, week["early"].pk, monday).count() == 0
        assert "Dilan" in pool_names(page, monday)
        save(page)
        assert not TimeSlot.objects.filter(pk=week["early"].pk).exists()


class TestANewWeek:
    def test_it_starts_as_a_copy_and_saves_as_one(self, page, week, monday, dilan):
        following = monday + dt.timedelta(days=7)
        open_week(page, following)
        assert page.locator(".roster-notice").first.is_visible()
        assert page.locator("[data-grid-body] tr").count() == 4
        assert chips_in(page, "new-1", following) == ["Dilan (07:30)"]
        save(page)
        assert TimeSlot.objects.filter(week=following).count() == 3
        copied = Shift.objects.get(employee=dilan, date=following)
        assert (copied.start, copied.end) == (T(7, 30), T(8, 0))

    def test_an_empty_week_on_request(self, page, week, monday):
        open_week(page, monday + dt.timedelta(days=7), empty="1")
        assert page.locator("[data-grid-body] tr").count() == 0
        assert page.locator("[data-grid-empty]").is_visible()


class TestThePhoneWidth:
    def test_the_grid_scrolls_and_the_page_does_not(self, page, week, monday):
        page.set_viewport_size({"width": 390, "height": 800})
        open_week(page, monday)
        page_width = page.evaluate("() => document.documentElement.scrollWidth")
        assert page_width <= 390 + 1
        scroller = page.locator(".rgrid-scroll")
        assert scroller.evaluate("el => el.scrollWidth > el.clientWidth")


def test_the_areas_page_saves_an_icon(page, org):
    page.goto(f"{page.live_server.url}/roster/areas/")
    page.click("[data-rows-add='areas']")
    page.fill("input[name='area-0-name']", "Garden")
    page.click(".icon-choice:has(input[name='area-0-icon'][value='tree'])")
    with page.expect_navigation():
        page.click(".form-actions button[type=submit]")
    area = Area.objects.get()
    assert (area.name, area.icon) == ("Garden", "tree")
