"""The week grid.

The tests worth most here are the ones about the **seams**: a placement is a
``Shift``, the timesheet reads joined stretches of them, and the browser points
placements at slots that may not exist yet. Each seam is a place where the page
can look completely right while the saved roster is something else:

* consecutive slots must read as *one* stretch on the timesheet, or every
  honest single entry is flagged "different from the roster";
* a placement pointing at a new slot by its browser key must land on the row
  that key became;
* a draft copied from last week must save when posted back unchanged — the
  trap being that Django reads an unchanged extra row as empty and skips it;
* a cell key is whatever the browser sent, and must be checked against the
  week being edited.
"""

import datetime as dt
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.urls import reverse

from apps.absences.models import Absence, AbsenceKind, BankHoliday, RequestStatus
from apps.roster.forms import cell_key, parse_cell
from apps.roster.models import (
    Area, AreaIcon, CellNote, PlannedWeek, Shift, TimeSlot, join_shifts,
    planned_spans, spans_overlap,
)
from apps.timesheets.models import DayRecord

T = dt.time


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _management(prefix, total, initial=0):
    return {
        f"{prefix}-TOTAL_FORMS": str(total),
        f"{prefix}-INITIAL_FORMS": str(initial),
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }


def week_post(monday, slots=(), places=(), notes=()):
    """A POST as the browser sends it.

    Each of ``slots``, ``places`` and ``notes`` is a list of dicts of field
    values; a row with an ``id`` counts towards INITIAL_FORMS and must come
    first, exactly as Django renders them.
    """
    data = {"week": monday.isoformat()}
    for prefix, rows in (("slot", slots), ("place", places), ("note", notes)):
        rows = list(rows)
        initial = sum(1 for row in rows if row.get("id"))
        data.update(_management(prefix, len(rows), initial))
        for index, row in enumerate(rows):
            for name, value in row.items():
                if name == "areas":
                    data[f"{prefix}-{index}-areas"] = [str(v) for v in value]
                elif name == "DELETE":
                    if value:
                        data[f"{prefix}-{index}-DELETE"] = "on"
                elif value is None:
                    data[f"{prefix}-{index}-{name}"] = ""
                else:
                    data[f"{prefix}-{index}-{name}"] = str(value)
    return data


def post_rendered(client, response, week):
    """Post a rendered planner back exactly as it came — what pressing Save on
    an untouched page does. Built from the unbound forms' initial values."""
    grid = response.context["grid"]
    data = {"week": week.isoformat()}
    for formset in (grid.slots, grid.places, grid.notes):
        management = formset.management_form
        for name in ("TOTAL_FORMS", "INITIAL_FORMS", "MIN_NUM_FORMS", "MAX_NUM_FORMS"):
            data[f"{formset.prefix}-{name}"] = str(management[name].value())
        for form in formset.forms:
            for bound in form:
                value = bound.value()
                if bound.name == "DELETE":
                    continue
                if isinstance(value, (list, tuple)):
                    data[bound.html_name] = [str(v) for v in value]
                elif value is None:
                    data[bound.html_name] = ""
                elif hasattr(value, "hour"):
                    data[bound.html_name] = value.strftime("%H:%M")
                else:
                    data[bound.html_name] = str(value)
    return client.post(reverse("roster:save"), data)


def errors_of(response):
    return response.context["grid"].errors if response.context else []


@pytest.fixture
def plan_url():
    return reverse("roster:save")


@pytest.fixture
def rooms(db):
    one = Area.objects.create(name="Room 1", icon=AreaIcon.STAR, position=1)
    two = Area.objects.create(name="Room 2", icon=AreaIcon.MOON, position=2)
    return one, two


# --------------------------------------------------------------------------
# Joining placements into stretches
# --------------------------------------------------------------------------

class TestJoiningShifts:
    def _shift(self, employee, day, start, end, area=None):
        return Shift(employee=employee, date=day, start=start, end=end, area=area)

    def test_consecutive_slots_are_one_stretch(self, anna, monday):
        spans = join_shifts([
            self._shift(anna, monday, T(8, 0), T(12, 0)),
            self._shift(anna, monday, T(7, 0), T(7, 15)),
            self._shift(anna, monday, T(7, 15), T(8, 0)),
        ])
        assert [(s.start, s.end) for s in spans] == [(T(7, 0), T(12, 0))]

    def test_a_gap_stays_a_gap(self, anna, monday):
        """In for the morning and back for the afternoon is two stretches. The
        time between is not work, and joining across it would roster it."""
        spans = join_shifts([
            self._shift(anna, monday, T(7, 0), T(11, 0)),
            self._shift(anna, monday, T(14, 0), T(17, 0)),
        ])
        assert [(s.start, s.end) for s in spans] == [(T(7, 0), T(11, 0)), (T(14, 0), T(17, 0))]

    def test_a_night_shift_joins_onto_the_slot_before_it(self, anna, monday):
        spans = join_shifts([
            self._shift(anna, monday, T(22, 0), T(6, 0)),
            self._shift(anna, monday, T(20, 0), T(22, 0)),
        ])
        assert [(s.start, s.end) for s in spans] == [(T(20, 0), T(6, 0))]

    def test_an_overlap_is_still_one_stretch(self, anna, monday):
        spans = join_shifts([
            self._shift(anna, monday, T(8, 0), T(12, 0)),
            self._shift(anna, monday, T(9, 0), T(10, 0)),
        ])
        assert [(s.start, s.end) for s in spans] == [(T(8, 0), T(12, 0))]

    def test_the_stretch_names_the_areas_it_crossed(self, anna, monday, rooms):
        one, two = rooms
        spans = join_shifts([
            self._shift(anna, monday, T(8, 0), T(10, 0), one),
            self._shift(anna, monday, T(10, 0), T(12, 0), two),
            self._shift(anna, monday, T(12, 0), T(13, 0), one),
        ])
        assert spans[0].note == "Room 1, Room 2"

    def test_minutes_are_the_whole_stretch(self, anna, monday):
        spans = join_shifts([
            self._shift(anna, monday, T(7, 0), T(7, 15)),
            self._shift(anna, monday, T(7, 15), T(8, 0)),
        ])
        assert spans[0].minutes == 60

    def test_planned_spans_groups_by_date(self, anna, monday):
        tuesday = monday + dt.timedelta(days=1)
        Shift.objects.create(employee=anna, date=monday, start=T(8, 0), end=T(9, 0))
        Shift.objects.create(employee=anna, date=monday, start=T(9, 0), end=T(10, 0))
        Shift.objects.create(employee=anna, date=tuesday, start=T(8, 0), end=T(9, 0))
        found = planned_spans(anna, monday, tuesday)
        assert [(s.start, s.end) for s in found[monday]] == [(T(8, 0), T(10, 0))]
        assert len(found[tuesday]) == 1

    @pytest.mark.parametrize("a,b,expected", [
        ((T(7, 0), T(8, 0)), (T(8, 0), T(9, 0)), False),     # touching
        ((T(7, 0), T(8, 30)), (T(8, 0), T(9, 0)), True),
        ((T(22, 0), T(6, 0)), (T(23, 0), T(23, 30)), True),   # inside a night shift
        ((T(22, 0), T(6, 0)), (T(6, 0), T(7, 0)), False),     # different stretch of clock
    ])
    def test_overlap(self, a, b, expected):
        assert spans_overlap(*a, *b) is expected
        assert spans_overlap(*b, *a) is expected


class TestTheTimesheetReadsStretches:
    """The reason ``planned_spans`` exists."""

    @pytest.fixture
    def three_slots(self, anna, monday):
        week = TimeSlot.objects.create(week=monday, start=T(7, 0), end=T(7, 15))
        for slot, (start, end) in zip(
            [week,
             TimeSlot.objects.create(week=monday, start=T(7, 15), end=T(8, 0)),
             TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(12, 0))],
            [(T(7, 0), T(7, 15)), (T(7, 15), T(8, 0)), (T(8, 0), T(12, 0))],
        ):
            Shift.objects.create(employee=anna, date=monday, slot=slot, start=start, end=end)

    def test_confirming_copies_one_segment(self, org, anna, monday, three_slots, client):
        response = client.post(reverse("timesheets:confirm-day", args=[anna.pk, monday.isoformat()]))
        assert response.status_code == 302
        record = DayRecord.objects.get(employee=anna, date=monday)
        assert [(s.start, s.end) for s in record.segments.all()] == [(T(7, 0), T(12, 0))]

    def test_one_honest_entry_matches_the_roster(self, org, anna, monday, three_slots):
        from apps.timesheets.views import build_week

        record = DayRecord.objects.create(employee=anna, date=monday)
        record.segments.create(position=0, start=T(7, 0), end=T(12, 0))
        row = build_week(anna, monday)["rows"][0]
        assert row["planned_minutes"] == 300
        assert not row["differs_from_roster"]

    def test_the_day_page_shows_one_span(self, org, anna, monday, three_slots, client):
        response = client.get(reverse("timesheets:day", args=[anna.pk, monday.isoformat()]))
        assert len(response.context["shifts"]) == 1
        assert response.context["planned_minutes"] == 300


# --------------------------------------------------------------------------
# The planner page
# --------------------------------------------------------------------------

class TestThePage:
    def test_a_manager_sees_the_grid(self, manager_client, org, monday):
        response = manager_client.get(reverse("roster:plan"), {"week": monday.isoformat()})
        assert response.status_code == 200
        body = response.content.decode()
        assert "data-grid-body" in body
        assert "roster-data" in body

    def test_five_days_monday_to_friday(self, manager_client, org, monday):
        response = manager_client.get(reverse("roster:plan"), {"week": monday.isoformat()})
        days = response.context["page_data"]["days"]
        assert days == [(monday + dt.timedelta(days=n)).isoformat() for n in range(5)]

    def test_any_day_of_the_week_lands_on_its_monday(self, manager_client, org, monday):
        response = manager_client.get(
            reverse("roster:plan"), {"week": (monday + dt.timedelta(days=3)).isoformat()})
        assert response.context["monday"] == monday

    def test_nonsense_in_the_address_bar_is_this_week(self, manager_client, org):
        assert manager_client.get(reverse("roster:plan"), {"week": "banana"}).status_code == 200

    def test_an_ordinary_employee_is_turned_away(self, client, org, anna, monday):
        assert client.get(reverse("roster:plan")).status_code == 404
        assert client.post(reverse("roster:save"), week_post(monday)).status_code == 404
        assert client.get(reverse("roster:areas")).status_code == 404

    def test_shifts_the_grid_cannot_draw_are_named(self, manager_client, org, anna, monday):
        saturday = monday + dt.timedelta(days=5)
        Shift.objects.create(employee=anna, date=saturday, start=T(9, 0), end=T(12, 0))
        response = manager_client.get(reverse("roster:plan"), {"week": monday.isoformat()})
        assert [s.date for s in response.context["outside"]] == [saturday]

    def test_shifts_on_the_grid_are_not_listed_as_outside_it(self, manager_client, org, anna, monday):
        slot = TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(9, 0))
        Shift.objects.create(employee=anna, date=monday, slot=slot, start=T(8, 0), end=T(9, 0))
        response = manager_client.get(reverse("roster:plan"), {"week": monday.isoformat()})
        assert response.context["outside"] == []


class TestWhoTheListShows:
    """The per-day state the browser draws the list under the grid from."""

    def _people(self, manager_client, monday):
        response = manager_client.get(reverse("roster:plan"), {"week": monday.isoformat()})
        return {p["full"]: p for p in response.context["page_data"]["people"]}

    def test_on_and_off_follow_the_contract(self, manager_client, org, cem, monday):
        cem_days = self._people(manager_client, monday)["Cem Test"]["days"]
        assert cem_days[monday.isoformat()]["state"] == "on"
        thursday = (monday + dt.timedelta(days=3)).isoformat()
        assert cem_days[thursday]["state"] == "off"       # no hours, still listed

    def test_leave_is_away(self, manager_client, org, anna, monday):
        Absence.objects.create(employee=anna, kind=AbsenceKind.HOLIDAY, start_date=monday,
                               end_date=monday, status=RequestStatus.APPROVED)
        state = self._people(manager_client, monday)["Anna Test"]["days"][monday.isoformat()]
        assert state["state"] == "away"
        assert not state["pending"]

    def test_a_pending_request_is_away_and_pending(self, manager_client, org, anna, monday):
        Absence.objects.create(employee=anna, kind=AbsenceKind.HOLIDAY, start_date=monday,
                               end_date=monday, status=RequestStatus.REQUESTED)
        state = self._people(manager_client, monday)["Anna Test"]["days"][monday.isoformat()]
        assert state["state"] == "away"
        assert state["pending"]

    def test_sickness_is_never_pending(self, manager_client, org, anna, monday):
        """Sickness is stated, not asked for — reported is away."""
        Absence.objects.create(employee=anna, kind=AbsenceKind.SICK, start_date=monday,
                               end_date=monday, status=RequestStatus.REQUESTED)
        state = self._people(manager_client, monday)["Anna Test"]["days"][monday.isoformat()]
        assert state == {"state": "away", "label": "Sick", "pending": False}

    def test_a_declined_request_is_not_away(self, manager_client, org, anna, monday):
        Absence.objects.create(employee=anna, kind=AbsenceKind.HOLIDAY, start_date=monday,
                               end_date=monday, status=RequestStatus.REJECTED)
        state = self._people(manager_client, monday)["Anna Test"]["days"][monday.isoformat()]
        assert state["state"] == "on"

    def test_nobody_is_offered_outside_their_employment(self, manager_client, org, anna, monday):
        anna.ended_on = monday + dt.timedelta(days=1)
        anna.save()
        anna_days = self._people(manager_client, monday)["Anna Test"]["days"]
        assert monday.isoformat() in anna_days
        assert (monday + dt.timedelta(days=2)).isoformat() not in anna_days

    def test_somebody_who_has_left_is_not_listed(self, manager_client, org, anna, monday):
        anna.is_active = False
        anna.save()
        assert "Anna Test" not in self._people(manager_client, monday)

    def test_two_people_with_one_first_name_get_an_initial(self, manager_client, org, monday):
        from decimal import Decimal

        from apps.employees.models import Employee

        for last, username in (("Berger", "sberger"), ("Kaya", "skaya")):
            sam = Employee.objects.create(first_name="Sam", last_name=last, username=username)
            sam.set_hours([Decimal(8)] * 5 + [Decimal(0)] * 2, valid_from=dt.date(2000, 1, 1))
        people = self._people(manager_client, monday)
        assert people["Sam Berger"]["name"] == "Sam B."
        assert people["Sam Kaya"]["name"] == "Sam K."


# --------------------------------------------------------------------------
# Saving
# --------------------------------------------------------------------------

class TestSaving:
    def test_a_new_slot_and_a_placement_in_it_save_together(
        self, manager_client, org, anna, monday, plan_url,
    ):
        """The placement points at a slot that has no row yet, by its key."""
        response = manager_client.post(plan_url, week_post(
            monday,
            slots=[{"key": "new-1", "start": "07:00", "end": "07:15"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday)}],
        ))
        assert response.status_code == 302, errors_of(response)
        slot = TimeSlot.objects.get(week=monday)
        shift = Shift.objects.get(employee=anna)
        assert shift.slot == slot
        assert (shift.date, shift.start, shift.end) == (monday, T(7, 0), T(7, 15))
        assert PlannedWeek.objects.filter(week=monday).exists()

    def test_times_are_read_however_they_were_typed(self, manager_client, org, monday, plan_url):
        manager_client.post(plan_url, week_post(
            monday, slots=[{"key": "new-1", "start": "715", "end": "8"}]))
        slot = TimeSlot.objects.get()
        assert (slot.start, slot.end) == (T(7, 15), T(8, 0))

    def test_own_times_are_stored_as_the_shift(self, manager_client, org, anna, monday, plan_url):
        manager_client.post(plan_url, week_post(
            monday,
            slots=[{"key": "new-1", "start": "07:15", "end": "08:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday),
                     "custom_start": "07:30"}],
        ))
        shift = Shift.objects.get()
        assert (shift.start, shift.end) == (T(7, 30), T(8, 0))

    def test_own_times_come_back_as_only_what_differs(self, manager_client, org, anna, monday):
        slot = TimeSlot.objects.create(week=monday, start=T(7, 15), end=T(8, 0))
        Shift.objects.create(employee=anna, date=monday, slot=slot, start=T(7, 30), end=T(8, 0))
        response = manager_client.get(reverse("roster:plan"), {"week": monday.isoformat()})
        form = response.context["grid"].places.forms[0]
        assert form.initial["custom_start"] == T(7, 30)
        assert "custom_end" not in form.initial
        assert form.initial["cell"] == cell_key(slot.pk, monday)

    def test_moving_a_slot_moves_the_people_who_follow_it(
        self, manager_client, org, anna, dilan, monday, plan_url,
    ):
        """A placement without its own time follows the slot; one with its own
        time keeps it. That is what each of the two means."""
        slot = TimeSlot.objects.create(week=monday, start=T(7, 0), end=T(8, 0))
        follows = Shift.objects.create(employee=anna, date=monday, slot=slot, start=T(7, 0), end=T(8, 0))
        own = Shift.objects.create(employee=dilan, date=monday, slot=slot, start=T(7, 30), end=T(8, 0))
        response = manager_client.post(plan_url, week_post(
            monday,
            slots=[{"id": slot.pk, "key": slot.pk, "start": "06:30", "end": "08:30"}],
            places=[
                {"id": follows.pk, "employee": anna.pk, "cell": cell_key(slot.pk, monday)},
                {"id": own.pk, "employee": dilan.pk, "cell": cell_key(slot.pk, monday),
                 "custom_start": "07:30", "custom_end": "08:00"},
            ],
        ))
        assert response.status_code == 302, errors_of(response)
        follows.refresh_from_db()
        own.refresh_from_db()
        assert (follows.start, follows.end) == (T(6, 30), T(8, 30))
        assert (own.start, own.end) == (T(7, 30), T(8, 0))

    def test_dragging_rewrites_the_same_row(self, manager_client, org, anna, monday, plan_url):
        slot = TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(9, 0))
        shift = Shift.objects.create(employee=anna, date=monday, slot=slot, start=T(8, 0), end=T(9, 0))
        wednesday = monday + dt.timedelta(days=2)
        manager_client.post(plan_url, week_post(
            monday,
            slots=[{"id": slot.pk, "start": "08:00", "end": "09:00"}],
            places=[{"id": shift.pk, "employee": anna.pk, "cell": cell_key(slot.pk, wednesday)}],
        ))
        assert list(Shift.objects.values_list("pk", "date")) == [(shift.pk, wednesday)]

    def test_taking_somebody_out_deletes_their_shift(self, manager_client, org, anna, monday, plan_url):
        slot = TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(9, 0))
        shift = Shift.objects.create(employee=anna, date=monday, slot=slot, start=T(8, 0), end=T(9, 0))
        manager_client.post(plan_url, week_post(
            monday,
            slots=[{"id": slot.pk, "start": "08:00", "end": "09:00"}],
            places=[{"id": shift.pk, "employee": anna.pk, "cell": cell_key(slot.pk, monday),
                     "DELETE": True}],
        ))
        assert not Shift.objects.exists()

    def test_a_removed_unsaved_placement_is_not_created(self, manager_client, org, anna, monday, plan_url):
        manager_client.post(plan_url, week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "09:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday), "DELETE": True}],
        ))
        assert not Shift.objects.exists()

    def test_removing_a_slot_takes_what_is_in_it(self, manager_client, org, anna, monday, plan_url):
        slot = TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(9, 0))
        shift = Shift.objects.create(employee=anna, date=monday, slot=slot, start=T(8, 0), end=T(9, 0))
        note = CellNote.objects.create(slot=slot, date=monday, text="Break")
        response = manager_client.post(plan_url, week_post(
            monday,
            slots=[{"id": slot.pk, "start": "08:00", "end": "09:00", "DELETE": True}],
            places=[{"id": shift.pk, "employee": anna.pk, "cell": cell_key(slot.pk, monday)}],
            notes=[{"id": note.pk, "cell": cell_key(slot.pk, monday), "text": "Break"}],
        ))
        assert response.status_code == 302, errors_of(response)
        assert not TimeSlot.objects.exists()
        assert not Shift.objects.exists()
        assert not CellNote.objects.exists()

    def test_somebody_moved_out_of_a_removed_slot_survives(
        self, manager_client, org, anna, monday, plan_url,
    ):
        doomed = TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(9, 0))
        kept = TimeSlot.objects.create(week=monday, start=T(9, 0), end=T(10, 0))
        shift = Shift.objects.create(employee=anna, date=monday, slot=doomed, start=T(8, 0), end=T(9, 0))
        response = manager_client.post(plan_url, week_post(
            monday,
            slots=[{"id": doomed.pk, "start": "08:00", "end": "09:00", "DELETE": True},
                   {"id": kept.pk, "start": "09:00", "end": "10:00"}],
            places=[{"id": shift.pk, "employee": anna.pk, "cell": cell_key(kept.pk, monday)}],
        ))
        assert response.status_code == 302, errors_of(response)
        moved = Shift.objects.get(employee=anna)
        assert (moved.slot, moved.start) == (kept, T(9, 0))

    def test_an_empty_week_can_be_saved_and_stays_empty(self, manager_client, org, monday, plan_url):
        """A week cleared on purpose is planned — and must not be helpfully
        filled in from the week before on the next visit."""
        before = monday - dt.timedelta(days=7)
        TimeSlot.objects.create(week=before, start=T(8, 0), end=T(9, 0))
        assert manager_client.post(plan_url, week_post(monday)).status_code == 302
        response = manager_client.get(reverse("roster:plan"), {"week": monday.isoformat()})
        assert response.context["draft_source"] is None
        assert response.context["grid"].slots.forms == []


class TestAreas:
    def test_a_placement_in_an_area(self, manager_client, org, anna, monday, rooms, plan_url):
        one, two = rooms
        response = manager_client.post(plan_url, week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "12:00", "areas": [one.pk, two.pk]}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday, two.pk)}],
        ))
        assert response.status_code == 302, errors_of(response)
        assert Shift.objects.get().area == two
        assert set(TimeSlot.objects.get().areas.all()) == {one, two}

    def test_an_area_the_slot_does_not_have_is_refused(
        self, manager_client, org, anna, monday, rooms, plan_url,
    ):
        one, two = rooms
        response = manager_client.post(plan_url, week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "12:00", "areas": [one.pk]}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday, two.pk)}],
        ))
        assert response.status_code == 200
        assert "That area is not part of this time range." in errors_of(response)
        assert not TimeSlot.objects.exists()           # nothing half-saved

    def test_a_slot_split_into_areas_has_no_undivided_cell(
        self, manager_client, org, anna, monday, rooms, plan_url,
    ):
        one, _two = rooms
        response = manager_client.post(plan_url, week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "12:00", "areas": [one.pk]}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday)}],
        ))
        assert "That area is not part of this time range." in errors_of(response)

    def test_an_area_on_a_slot_with_none_is_refused(
        self, manager_client, org, anna, monday, rooms, plan_url,
    ):
        one, _two = rooms
        response = manager_client.post(plan_url, week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "12:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday, one.pk)}],
        ))
        assert "That time range is not split into areas." in errors_of(response)


class TestTheCellKeyIsChecked:
    """It is whatever the browser sent."""

    def _post(self, manager_client, monday, anna, cell):
        return manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "09:00"}],
            places=[{"employee": anna.pk, "cell": cell}],
        ))

    def test_a_date_in_another_week(self, manager_client, org, anna, monday):
        response = self._post(manager_client, monday, anna,
                              cell_key("new-1", monday + dt.timedelta(days=200)))
        assert "That day is not in the week being planned." in errors_of(response)
        assert not Shift.objects.exists()

    def test_a_saturday(self, manager_client, org, anna, monday):
        response = self._post(manager_client, monday, anna,
                              cell_key("new-1", monday + dt.timedelta(days=5)))
        assert "That day is not in the week being planned." in errors_of(response)

    def test_a_slot_that_is_not_on_the_page(self, manager_client, org, anna, monday):
        other = TimeSlot.objects.create(week=monday - dt.timedelta(days=7), start=T(8, 0), end=T(9, 0))
        response = self._post(manager_client, monday, anna, cell_key(other.pk, monday))
        assert "That time range is not on this page." in errors_of(response)

    def test_garbage(self, manager_client, org, anna, monday):
        response = self._post(manager_client, monday, anna, "nonsense")
        assert "That is not a cell on this page." in errors_of(response)

    def test_an_existing_slot_cannot_be_renamed_by_its_key(self, manager_client, org, anna, monday):
        """An existing slot is its pk whatever ``key`` says, so a tampered key
        cannot make a placement land in a row it does not name."""
        slot = TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(9, 0))
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"id": slot.pk, "key": "new-9", "start": "08:00", "end": "09:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-9", monday)}],
        ))
        assert "That time range is not on this page." in errors_of(response)

    def test_a_new_slot_needs_a_new_key(self, manager_client, org, monday):
        response = manager_client.post(reverse("roster:save"), week_post(
            monday, slots=[{"key": "17", "start": "08:00", "end": "09:00"}]))
        assert "A new time range arrived without a name the page could use." in errors_of(response)

    def test_the_cell_key_round_trips(self, monday):
        assert parse_cell(cell_key("new-3", monday, 7)) == ("new-3", monday, 7)
        assert parse_cell(cell_key(12, monday)) == ("12", monday, None)


class TestRefusals:
    def test_somebody_in_two_areas_at_once(self, manager_client, org, anna, monday, rooms):
        one, two = rooms
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "12:00", "areas": [one.pk, two.pk]}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday, one.pk)},
                    {"employee": anna.pk, "cell": cell_key("new-1", monday, two.pk)}],
        ))
        assert response.status_code == 200
        message = "Anna Test is in two places at once on Monday at 08:00."
        assert message in errors_of(response)
        assert response.context["grid"].placement_errors == {
            "place-0": [message], "place-1": [message],
        }
        assert not Shift.objects.exists()

    def test_consecutive_slots_are_not_a_clash(self, manager_client, org, anna, monday):
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "07:00", "end": "07:15"},
                   {"key": "new-2", "start": "07:15", "end": "08:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday)},
                    {"employee": anna.pk, "cell": cell_key("new-2", monday)}],
        ))
        assert response.status_code == 302, errors_of(response)
        assert Shift.objects.count() == 2

    def test_own_times_reaching_into_the_next_slot_are_a_clash(self, manager_client, org, anna, monday):
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "07:00", "end": "08:00"},
                   {"key": "new-2", "start": "08:00", "end": "09:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday), "custom_end": "08:30"},
                    {"employee": anna.pk, "cell": cell_key("new-2", monday)}],
        ))
        assert "Anna Test is in two places at once on Monday at 08:00." in errors_of(response)

    def test_the_same_person_on_two_days_is_fine(self, manager_client, org, anna, monday):
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "09:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday)},
                    {"employee": anna.pk, "cell": cell_key("new-1", monday + dt.timedelta(days=1))}],
        ))
        assert response.status_code == 302, errors_of(response)

    def test_a_slot_needs_a_length(self, manager_client, org, monday):
        response = manager_client.post(reverse("roster:save"), week_post(
            monday, slots=[{"key": "new-1", "start": "08:00", "end": "8"}]))
        assert response.status_code == 200
        assert not TimeSlot.objects.exists()

    def test_an_unreadable_time_is_refused_not_guessed(self, manager_client, org, monday):
        response = manager_client.post(reverse("roster:save"), week_post(
            monday, slots=[{"key": "new-1", "start": "8:3o", "end": "09:00"}]))
        assert response.status_code == 200
        assert not TimeSlot.objects.exists()

    def test_own_times_need_a_length(self, manager_client, org, anna, monday):
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "07:00", "end": "08:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday), "custom_start": "08:00"}],
        ))
        assert "Anna Test’s times need a length." in errors_of(response)

    def test_somebody_not_yet_employed(self, manager_client, org, anna, monday):
        anna.started_on = monday + dt.timedelta(days=1)
        anna.save()
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "09:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday)}],
        ))
        assert "Anna Test is not employed on that day." in errors_of(response)

    def test_somebody_who_has_left_cannot_be_added(self, manager_client, org, anna, monday):
        anna.is_active = False
        anna.save()
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "09:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday)}],
        ))
        assert "Anna Test is not employed on that day." in errors_of(response)

    def test_but_a_past_week_with_them_in_it_can_still_be_saved(self, manager_client, org, anna, monday):
        """Re-saving a week somebody worked before they left must not be refused
        over a placement nobody touched."""
        slot = TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(9, 0))
        shift = Shift.objects.create(employee=anna, date=monday, slot=slot, start=T(8, 0), end=T(9, 0))
        anna.is_active = False
        anna.save()
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"id": slot.pk, "start": "08:00", "end": "09:00"}],
            places=[{"id": shift.pk, "employee": anna.pk, "cell": cell_key(slot.pk, monday)}],
            notes=[{"cell": cell_key(slot.pk, monday), "text": "Handover"}],
        ))
        assert response.status_code == 302, errors_of(response)
        assert CellNote.objects.get().text == "Handover"

    def test_a_refused_save_shows_every_row_again(self, manager_client, org, anna, monday):
        """A refusal re-renders the bound rows — nothing typed is lost."""
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "08:00", "end": "09:00"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday + dt.timedelta(days=9))}],
            notes=[{"cell": cell_key("new-1", monday), "text": "Outing"}],
        ))
        body = response.content.decode()
        assert 'value="new-1"' in body
        assert 'value="Outing"' in body


class TestCellText:
    def test_text_is_saved_per_cell(self, manager_client, org, monday, rooms):
        one, _two = rooms
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "12:00", "end": "12:30", "areas": [one.pk]}],
            notes=[{"cell": cell_key("new-1", monday, one.pk), "text": "  Break "}],
        ))
        assert response.status_code == 302, errors_of(response)
        note = CellNote.objects.get()
        assert (note.text, note.area, note.date) == ("Break", one, monday)

    def test_blank_boxes_write_nothing(self, manager_client, org, monday):
        manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "12:00", "end": "12:30"}],
            notes=[{"cell": cell_key("new-1", monday + dt.timedelta(days=n)), "text": ""}
                   for n in range(5)],
        ))
        assert not CellNote.objects.exists()

    def test_emptying_a_box_deletes_its_text(self, manager_client, org, monday):
        slot = TimeSlot.objects.create(week=monday, start=T(12, 0), end=T(12, 30))
        note = CellNote.objects.create(slot=slot, date=monday, text="Break")
        manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"id": slot.pk, "start": "12:00", "end": "12:30"}],
            notes=[{"id": note.pk, "cell": cell_key(slot.pk, monday), "text": ""}],
        ))
        assert not CellNote.objects.exists()

    def test_editing_a_text(self, manager_client, org, monday):
        slot = TimeSlot.objects.create(week=monday, start=T(12, 0), end=T(12, 30))
        note = CellNote.objects.create(slot=slot, date=monday, text="Break")
        manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"id": slot.pk, "start": "12:00", "end": "12:30"}],
            notes=[{"id": note.pk, "cell": cell_key(slot.pk, monday), "text": "Lunch"}],
        ))
        assert list(CellNote.objects.values_list("pk", "text")) == [(note.pk, "Lunch")]

    def test_one_text_per_cell(self, manager_client, org, monday):
        manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "12:00", "end": "12:30"}],
            notes=[{"cell": cell_key("new-1", monday), "text": "Break"},
                   {"cell": cell_key("new-1", monday), "text": "Lunch"}],
        ))
        assert list(CellNote.objects.values_list("text", flat=True)) == ["Break"]

    def test_text_in_an_area_taken_off_its_slot_goes(self, manager_client, org, monday, rooms):
        """The browser has already taken it off the page; refusing the save over
        text nobody can see any more would be a dead end."""
        one, two = rooms
        slot = TimeSlot.objects.create(week=monday, start=T(12, 0), end=T(12, 30))
        slot.areas.set([one, two])
        note = CellNote.objects.create(slot=slot, date=monday, area=two, text="Garden")
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"id": slot.pk, "start": "12:00", "end": "12:30", "areas": [one.pk]}],
            notes=[{"id": note.pk, "cell": cell_key(slot.pk, monday, two.pk), "text": "Garden"}],
        ))
        assert response.status_code == 302, errors_of(response)
        assert not CellNote.objects.exists()

    def test_a_cell_may_hold_names_and_text(self, manager_client, org, anna, monday):
        response = manager_client.post(reverse("roster:save"), week_post(
            monday,
            slots=[{"key": "new-1", "start": "12:00", "end": "12:30"}],
            places=[{"employee": anna.pk, "cell": cell_key("new-1", monday)}],
            notes=[{"cell": cell_key("new-1", monday), "text": "Break supervision"}],
        ))
        assert response.status_code == 302, errors_of(response)
        assert Shift.objects.count() == CellNote.objects.count() == 1


# --------------------------------------------------------------------------
# A new week starts from the last one
# --------------------------------------------------------------------------

class TestTheDraft:
    @pytest.fixture
    def last_week(self, org, anna, cem, monday, rooms):
        """The week before ``monday``: two slots, one split, three people, a
        text, and somebody with their own start time."""
        one, two = rooms
        before = monday - dt.timedelta(days=7)
        early = TimeSlot.objects.create(week=before, start=T(7, 15), end=T(8, 0))
        main = TimeSlot.objects.create(week=before, start=T(8, 0), end=T(12, 0))
        main.areas.set([one, two])
        Shift.objects.create(employee=anna, date=before, slot=early, start=T(7, 30), end=T(8, 0))
        Shift.objects.create(employee=anna, date=before, slot=main, area=one, start=T(8, 0), end=T(12, 0))
        Shift.objects.create(employee=cem, date=before + dt.timedelta(days=1), slot=main, area=two,
                             start=T(8, 0), end=T(12, 0))
        CellNote.objects.create(slot=early, date=before, text="Open up")
        PlannedWeek.objects.create(week=before)
        return before

    def _get(self, client, monday, **params):
        return client.get(reverse("roster:plan"), {"week": monday.isoformat(), **params})

    def test_an_unplanned_week_is_filled_from_the_last_planned(self, manager_client, last_week, monday):
        response = self._get(manager_client, monday)
        grid = response.context["grid"]
        assert response.context["draft_source"] == last_week
        assert [f.initial["key"] for f in grid.slots.forms] == ["new-1", "new-2"]
        assert len(grid.places.forms) == 3
        assert grid.notes.forms[0].initial["text"] == "Open up"
        assert grid.notes.forms[0].initial["cell"] == cell_key("new-1", monday)

    def test_looking_writes_nothing(self, manager_client, last_week, monday):
        self._get(manager_client, monday)
        assert not TimeSlot.objects.filter(week=monday).exists()
        assert not Shift.objects.filter(date__gte=monday).exists()
        assert not PlannedWeek.objects.filter(week=monday).exists()

    def test_saving_the_draft_untouched_saves_all_of_it(
        self, manager_client, last_week, monday, anna, cem, rooms,
    ):
        """The trap: an extra row posted back equal to its initial is read by
        Django as empty and skipped, so a draft rendered with ``initial`` and
        validated against it would save nothing at all."""
        one, two = rooms
        response = post_rendered(manager_client, self._get(manager_client, monday), monday)
        assert response.status_code == 302, errors_of(response)
        assert TimeSlot.objects.filter(week=monday).count() == 2
        copied = {
            (s.employee_id, s.date, s.start, s.end, s.area_id)
            for s in Shift.objects.filter(date__gte=monday)
        }
        assert copied == {
            (anna.pk, monday, T(7, 30), T(8, 0), None),
            (anna.pk, monday, T(8, 0), T(12, 0), one.pk),
            (cem.pk, monday + dt.timedelta(days=1), T(8, 0), T(12, 0), two.pk),
        }
        assert CellNote.objects.filter(slot__week=monday).get().text == "Open up"

    def test_the_week_copied_from_is_untouched(self, manager_client, last_week, monday):
        before = set(Shift.objects.values_list("pk", "date", "start", "end"))
        post_rendered(manager_client, self._get(manager_client, monday), monday)
        assert before <= set(Shift.objects.values_list("pk", "date", "start", "end"))
        assert TimeSlot.objects.filter(week=last_week).count() == 2

    def test_somebody_on_holiday_is_left_out(self, manager_client, last_week, monday, anna):
        Absence.objects.create(employee=anna, kind=AbsenceKind.HOLIDAY, start_date=monday,
                               end_date=monday, status=RequestStatus.APPROVED)
        response = self._get(manager_client, monday)
        employees = [f.initial["employee"] for f in response.context["grid"].places.forms]
        assert anna.pk not in employees
        assert response.context["left_out"] == 2

    def test_a_pending_request_is_not_enough_to_leave_somebody_out(
        self, manager_client, last_week, monday, anna,
    ):
        Absence.objects.create(employee=anna, kind=AbsenceKind.HOLIDAY, start_date=monday,
                               end_date=monday, status=RequestStatus.REQUESTED)
        response = self._get(manager_client, monday)
        assert response.context["left_out"] == 0

    def test_a_public_holiday_is_left_out(self, manager_client, last_week, monday):
        BankHoliday.objects.create(date=monday, name="Test holiday")
        response = self._get(manager_client, monday)
        days = {parse_cell(f.initial["cell"])[1] for f in response.context["grid"].places.forms}
        assert monday not in days

    def test_somebody_who_has_left_is_left_out(self, manager_client, last_week, monday, cem):
        cem.ended_on = monday
        cem.save()
        response = self._get(manager_client, monday)
        employees = [f.initial["employee"] for f in response.context["grid"].places.forms]
        assert cem.pk not in employees

    def test_the_last_planned_week_not_merely_the_previous(self, manager_client, last_week, monday):
        """The week before may have been the summer closure."""
        response = self._get(manager_client, monday + dt.timedelta(days=21))
        assert response.context["draft_source"] == last_week

    def test_an_empty_week_on_request(self, manager_client, last_week, monday):
        response = self._get(manager_client, monday, empty="1")
        assert response.context["draft_source"] is None
        assert response.context["grid"].slots.forms == []

    def test_a_planned_week_is_never_drafted_over(self, manager_client, last_week, monday):
        TimeSlot.objects.create(week=monday, start=T(9, 0), end=T(10, 0))
        response = self._get(manager_client, monday)
        assert response.context["draft_source"] is None
        assert len(response.context["grid"].slots.forms) == 1

    def test_the_draft_says_it_is_one(self, manager_client, last_week, monday):
        body = self._get(manager_client, monday).content.decode()
        assert "data-roster-draft" in body
        assert "has not been planned yet" in body


# --------------------------------------------------------------------------
# Existing shifts are moved onto the grid
# --------------------------------------------------------------------------

class TestTheMigration:
    def test_every_weekday_shift_gets_the_slot_of_its_own_times(self, anna, cem, monday):
        saturday = monday + dt.timedelta(days=5)
        a = Shift.objects.create(employee=anna, date=monday, start=T(8, 0), end=T(16, 0))
        b = Shift.objects.create(employee=cem, date=monday + dt.timedelta(days=1), start=T(8, 0), end=T(16, 0))
        c = Shift.objects.create(employee=cem, date=monday, start=T(7, 30), end=T(11, 30))
        weekend = Shift.objects.create(employee=anna, date=saturday, start=T(9, 0), end=T(12, 0))

        module = import_module("apps.roster.migrations.0003_slots_for_existing_shifts")
        module.forwards(django_apps, None)

        for shift in (a, b, c, weekend):
            shift.refresh_from_db()
        assert a.slot == b.slot
        assert (a.slot.week, a.slot.start, a.slot.end) == (monday, T(8, 0), T(16, 0))
        assert (c.slot.start, c.slot.end) == (T(7, 30), T(11, 30))
        assert weekend.slot is None
        assert TimeSlot.objects.count() == 2
        assert PlannedWeek.objects.filter(week=monday).exists()
        # Nothing about what anybody was asked to work has changed.
        assert (a.start, a.end) == (T(8, 0), T(16, 0))


# --------------------------------------------------------------------------
# The areas page
# --------------------------------------------------------------------------

def _area_post(rows):
    data = _management("area", len(rows), sum(1 for row in rows if row.get("id")))
    for index, row in enumerate(rows):
        for name, value in row.items():
            if name in ("DELETE", "is_active"):
                if value:
                    data[f"area-{index}-{name}"] = "on"
            else:
                data[f"area-{index}-{name}"] = str(value)
    return data


class TestTheAreasPage:
    def test_it_renders_every_icon(self, manager_client, org, rooms):
        response = manager_client.get(reverse("roster:areas"))
        assert response.status_code == 200
        body = response.content.decode()
        for value, _label in AreaIcon.choices:
            assert f"areas.svg#{value}" in body or f"#{value}\"" in body

    def test_adding_an_area(self, manager_client, org):
        response = manager_client.post(reverse("roster:areas"), _area_post([
            {"name": "Garden", "icon": "tree", "is_active": True},
        ]))
        assert response.status_code == 302
        area = Area.objects.get()
        assert (area.name, area.icon, area.is_active) == ("Garden", "tree", True)

    def test_an_unused_area_can_be_deleted(self, manager_client, org, rooms):
        one, two = rooms
        manager_client.post(reverse("roster:areas"), _area_post([
            {"id": one.pk, "name": one.name, "icon": one.icon, "is_active": True},
            {"id": two.pk, "name": two.name, "icon": two.icon, "is_active": True, "DELETE": True},
        ]))
        assert list(Area.objects.all()) == [one]

    def test_a_used_area_is_kept_and_the_page_says_why(self, manager_client, org, rooms, monday):
        one, _two = rooms
        TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(9, 0)).areas.set([one])
        response = manager_client.post(reverse("roster:areas"), _area_post([
            {"id": one.pk, "name": one.name, "icon": one.icon, "is_active": True, "DELETE": True},
        ]), follow=True)
        assert Area.objects.filter(pk=one.pk).exists()
        assert "has been used in the roster and was kept" in response.content.decode()

    def test_switching_one_off_keeps_it(self, manager_client, org, rooms):
        one, _two = rooms
        manager_client.post(reverse("roster:areas"), _area_post([
            {"id": one.pk, "name": one.name, "icon": one.icon, "is_active": False},
        ]))
        one.refresh_from_db()
        assert not one.is_active

    def test_an_area_in_use_cannot_be_deleted_from_under_a_shift(self, anna, monday, rooms):
        from django.db.models import ProtectedError

        one, _two = rooms
        slot = TimeSlot.objects.create(week=monday, start=T(8, 0), end=T(9, 0))
        Shift.objects.create(employee=anna, date=monday, slot=slot, area=one, start=T(8, 0), end=T(9, 0))
        with pytest.raises(ProtectedError):
            one.delete()


def test_the_sprite_draws_every_icon_the_model_offers():
    """The sprite and ``AreaIcon`` are two lists of one thing, and an icon
    missing from the sprite renders as an empty square with no error."""
    from django.conf import settings

    sprite = (settings.BASE_DIR / "static" / "icons" / "areas.svg").read_text(encoding="utf-8")
    for value, _label in AreaIcon.choices:
        assert f'<symbol id="{value}"' in sprite, f"areas.svg has no symbol for {value}"
