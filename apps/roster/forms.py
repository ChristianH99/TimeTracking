"""The week grid's forms.

The page is **three formsets** and one coordinator:

* ``slot``  — the week's time ranges, each with the areas it is split into;
* ``place`` — one row per person placed in a cell, which is a ``Shift``;
* ``note``  — the text typed into a cell.

and ``WeekGrid`` validates them against each other and saves them together.

---- the cell key ----

A placement and a note each say where they are with **one hidden input**,
``cell``, holding ``<slot>|<date>|<area>``. Dragging a name to another cell
rewrites exactly that one input and nothing else — the card is the form row and
the drag moves the row, the rule the planner has always kept (see
``static/js/roster_plan.js``). There is never a second representation of the
week to disagree with the first.

``<slot>`` is the slot's primary key, or ``new-N`` for a slot added in the
browser and not yet saved. That is what lets somebody add a time range and
fill it in before the first Save: the placements point at the slot by the key
it was minted with, and ``WeekGrid.save`` swaps the key for the row it became.

---- why the server checks what the browser already arranged ----

The browser keeps every placement inside a cell that exists. But a cell key is
whatever the browser sent, and a page that trusted it would let a bug in the
drag handler write a shift into next March from a form that says it is editing
this week — the row would simply not be on the page that saved it.
"""

import datetime as dt
from functools import cached_property

from django import forms
from django.db import transaction
from django.forms import modelformset_factory
from django.utils.formats import date_format
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.employees.models import Employee
from apps.roster.models import (
    GRID_DAYS, Area, CellNote, PlannedWeek, Shift, TimeSlot, spans_overlap,
)
from apps.timesheets.fields import TimeOfDayField

NEW_SLOT_PREFIX = "new-"


def cell_key(slot_key, day, area_id=None):
    """The value of a ``cell`` input. The inverse of ``parse_cell``."""
    return f"{slot_key}|{day.isoformat()}|{area_id or ''}"


def parse_cell(raw):
    """``(slot_key, date, area_id or None)``, or ``ValueError``."""
    parts = str(raw or "").split("|")
    if len(parts) != 3 or not parts[0]:
        raise ValueError(raw)
    slot_key, day, area = parts
    return slot_key, dt.date.fromisoformat(day), (int(area) if area else None)


def rosterable(on_date=None):
    """The people who may be given a shift.

    Employed, and — when a date is given — employed *then*. A list offering
    somebody who left in March invites a shift nobody will work, and the
    roster is the one page where that mistake is invisible: the name looks
    exactly like every other name.
    """
    people = Employee.objects.filter(is_active=True)
    if on_date is not None:
        people = people.exclude(ended_on__lt=on_date).exclude(started_on__gt=on_date)
    return people


def employed_on(employee, day):
    if employee.started_on and day < employee.started_on:
        return False
    return not (employee.ended_on and day > employee.ended_on)


# --------------------------------------------------------------------------
# The three kinds of row
# --------------------------------------------------------------------------

class SlotForm(forms.ModelForm):
    key = forms.CharField(widget=forms.HiddenInput(), required=False)
    start = TimeOfDayField(label=_("From"))
    end = TimeOfDayField(label=_("To"))
    areas = forms.ModelMultipleChoiceField(
        label=_("Areas"), queryset=Area.objects.all(), required=False,
        widget=forms.CheckboxSelectMultiple(),
    )

    class Meta:
        model = TimeSlot
        fields = ["start", "end", "areas"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["key"] = str(self.instance.pk)

    @cached_property
    def slot_key(self):
        """How placements refer to this slot.

        An existing slot is its primary key whatever the browser sent in
        ``key`` — the hidden field is only trusted to name slots that do not
        exist yet, so a tampered key cannot make one row answer for another.

        Cached, and that is load-bearing: a new slot gains a primary key the
        moment it is saved, and a key read again after that would answer "17"
        where every placement pointing at it says "new-1".
        """
        if self.instance.pk:
            return str(self.instance.pk)
        raw = self.data.get(self.add_prefix("key"), "") if self.is_bound else self.initial.get("key", "")
        return str(raw or "")

    def clean(self):
        data = super().clean()
        start, end = data.get("start"), data.get("end")
        if start and end and start == end:
            self.add_error("end", gettext("A time range needs a length."))
        return data


class PlacementForm(forms.ModelForm):
    """One person in one cell. The times are only what *differs* from the slot.

    Blank ``custom_start`` / ``custom_end`` mean "the slot's own time", and that
    is stored as the slot's time on the ``Shift`` at save. So a placement that
    follows the slot keeps following it when the manager moves the slot, and one
    with its own time keeps that — which is what the two cases each mean.
    """

    employee = forms.ModelChoiceField(
        queryset=Employee.objects.all(), widget=forms.HiddenInput(),
    )
    cell = forms.CharField(widget=forms.HiddenInput())
    custom_start = TimeOfDayField(required=False, widget=forms.HiddenInput())
    custom_end = TimeOfDayField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Shift
        fields = ["employee"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        shift = self.instance
        if shift.pk and shift.slot_id:
            self.initial["cell"] = cell_key(shift.slot_id, shift.date, shift.area_id)
            if shift.start != shift.slot.start:
                self.initial["custom_start"] = shift.start
            if shift.end != shift.slot.end:
                self.initial["custom_end"] = shift.end


class NoteForm(forms.ModelForm):
    cell = forms.CharField(widget=forms.HiddenInput())
    text = forms.CharField(
        label=_("Text"), required=False, max_length=100,
        widget=forms.TextInput(attrs={
            "autocomplete": "off", "maxlength": 100, "data-cell-input": "",
        }),
    )

    class Meta:
        model = CellNote
        fields = ["text"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        note = self.instance
        if note.pk:
            self.initial["cell"] = cell_key(note.slot_id, note.date, note.area_id)


SlotFormSet = modelformset_factory(TimeSlot, form=SlotForm, extra=0, can_delete=True)
PlacementFormSet = modelformset_factory(Shift, form=PlacementForm, extra=0, can_delete=True)
# No DELETE on a note: emptying the box is how a note is removed, and a second
# way to say the same thing is a second thing that can disagree with the first.
NoteFormSet = modelformset_factory(CellNote, form=NoteForm, extra=0, can_delete=False)


def _is_blank_new(form):
    """An extra row that came back exactly as empty as it went out."""
    return form.instance.pk is None and not form.has_changed()


# --------------------------------------------------------------------------
# The coordinator
# --------------------------------------------------------------------------

class WeekGrid:
    """One week's grid: the three formsets, validated and saved as one.

    ``draft`` is ``(slots, placements, notes)`` as lists of initial dicts —
    the week copied forward from the last one planned. It is only ever used to
    render a page; a POST carries the rows itself and is built from them alone,
    which matters: an extra row with ``initial`` that comes back unchanged is
    read by Django as *empty* and skipped, so a draft posted against its own
    initial would save nothing at all.
    """

    def __init__(self, monday, data=None, draft=None):
        self.monday = monday
        self.days = [monday + dt.timedelta(days=offset) for offset in range(GRID_DAYS)]
        self.errors = []
        self.placement_errors = {}

        slots = TimeSlot.objects.filter(week=monday).prefetch_related("areas")
        shifts = (
            Shift.objects.filter(slot__week=monday, date__in=self.days)
            .select_related("slot", "employee", "area")
        )
        notes = CellNote.objects.filter(slot__week=monday)

        if data is not None:
            self.slots = SlotFormSet(data, queryset=slots, prefix="slot")
            self.places = PlacementFormSet(data, queryset=shifts, prefix="place")
            self.notes = NoteFormSet(data, queryset=notes, prefix="note")
        else:
            draft_slots, draft_places, draft_notes = draft or ([], [], [])
            self.slots = SlotFormSet(queryset=slots, prefix="slot", initial=draft_slots)
            self.slots.extra = len(draft_slots)
            self.places = PlacementFormSet(queryset=shifts, prefix="place", initial=draft_places)
            self.places.extra = len(draft_places)
            self.notes = NoteFormSet(queryset=notes, prefix="note", initial=draft_notes)
            self.notes.extra = len(draft_notes)

    # -- validation -------------------------------------------------------

    def is_valid(self):
        valid = all([self.slots.is_valid(), self.places.is_valid(), self.notes.is_valid()])
        if not valid:
            self.errors.append(gettext("Some entries could not be read — they are marked below."))
            return False
        self._resolve_slots()
        self._resolve_placements()
        self._resolve_notes()
        return not self.errors and not self.placement_errors

    def _resolve_slots(self):
        """``self.slot_forms``: key → the slot form that will hold it."""
        self.slot_forms = {}
        self.deleted_slot_keys = set()
        for form in self.slots.forms:
            if _is_blank_new(form):
                continue
            key = form.slot_key
            if self.slots._should_delete_form(form):
                self.deleted_slot_keys.add(key)
                continue
            if not form.instance.pk and not key.startswith(NEW_SLOT_PREFIX):
                self.errors.append(gettext("A new time range arrived without a name the page could use."))
                continue
            if key in self.slot_forms:
                self.errors.append(gettext("Two time ranges arrived under the same name."))
                continue
            self.slot_forms[key] = form

    def _place(self, raw):
        """``(slot form, date, area or None)`` for a cell key, or an error text.

        Returns ``None`` for a cell in a slot that is being deleted: what is in
        it goes with it, which is what removing a row of the grid means.
        """
        try:
            slot_key, day, area_id = parse_cell(raw)
        except (TypeError, ValueError):
            return gettext("That is not a cell on this page.")
        if slot_key in self.deleted_slot_keys:
            return None
        slot_form = self.slot_forms.get(slot_key)
        if slot_form is None:
            return gettext("That time range is not on this page.")
        if day not in self.days:
            return gettext("That day is not in the week being planned.")
        areas = {area.pk: area for area in slot_form.cleaned_data.get("areas") or []}
        if areas and area_id not in areas:
            return gettext("That area is not part of this time range.")
        if not areas and area_id is not None:
            return gettext("That time range is not split into areas.")
        return slot_form, day, areas.get(area_id)

    def _resolve_placements(self):
        """``self.placements``: ``(form, slot form, date, area, start, end)``."""
        self.placements = []
        self.doomed_placements = []
        for form in self.places.forms:
            if _is_blank_new(form):
                continue
            if self.places._should_delete_form(form):
                if form.instance.pk:
                    self.doomed_placements.append(form)
                continue
            where = self._place(form.cleaned_data["cell"])
            if where is None:
                continue                     # its slot is being removed
            if isinstance(where, str):
                self._fail(form, where)
                continue
            slot_form, day, area = where
            employee = form.cleaned_data["employee"]
            changed = (
                not form.instance.pk
                or form.instance.employee_id != employee.pk
                or form.instance.date != day
            )
            if changed and not (employee.is_active and employed_on(employee, day)):
                self._fail(form, gettext("%(name)s is not employed on that day.")
                           % {"name": employee.full_name})
                continue
            start = form.cleaned_data.get("custom_start") or slot_form.cleaned_data["start"]
            end = form.cleaned_data.get("custom_end") or slot_form.cleaned_data["end"]
            if start == end:
                self._fail(form, gettext("%(name)s’s times need a length.")
                           % {"name": employee.full_name})
                continue
            self.placements.append((form, slot_form, day, area, start, end))

        # Somebody in two places at once. Compared as spans of the day rather
        # than as slots, so a custom start reaching into the slot above is
        # caught too, and two consecutive slots — touching, not overlapping —
        # are not.
        by_person_day = {}
        for entry in self.placements:
            employee = entry[0].cleaned_data["employee"]
            by_person_day.setdefault((employee.pk, entry[2]), []).append(entry)
        for (_pk, day), entries in by_person_day.items():
            for index, first in enumerate(entries):
                for second in entries[index + 1:]:
                    if spans_overlap(first[4], first[5], second[4], second[5]):
                        message = gettext(
                            "%(name)s is in two places at once on %(day)s at %(time)s."
                        ) % {
                            "name": first[0].cleaned_data["employee"].full_name,
                            "day": date_format(day, "l"),
                            "time": max(first[4], second[4]).strftime("%H:%M"),
                        }
                        self._fail(first[0], message)
                        self._fail(second[0], message)

    def _fail(self, form, message):
        self.placement_errors.setdefault(form.prefix, [])
        if message not in self.placement_errors[form.prefix]:
            self.placement_errors[form.prefix].append(message)
        if message not in self.errors:
            self.errors.append(message)

    def _resolve_notes(self):
        """``self.note_rows`` to write and ``self.doomed_notes`` to delete.

        A note whose cell has gone — its area taken off the slot — is deleted
        rather than refused: the browser has already taken it off the page, and
        refusing the save over text nobody can see any more would be a dead end.
        One note per cell; a second for the same cell is dropped.
        """
        self.note_rows = []
        self.doomed_notes = []
        seen = set()
        for form in self.notes.forms:
            if _is_blank_new(form):
                continue
            text = (form.cleaned_data.get("text") or "").strip()
            where = self._place(form.cleaned_data.get("cell"))
            if not text or not isinstance(where, tuple):
                if form.instance.pk:
                    self.doomed_notes.append(form.instance)
                continue
            slot_form, day, area = where
            cell = (slot_form.slot_key, day, area.pk if area else None)
            if cell in seen:
                if form.instance.pk:
                    self.doomed_notes.append(form.instance)
                continue
            seen.add(cell)
            self.note_rows.append((form, slot_form, day, area, text))

    # -- saving -----------------------------------------------------------

    @transaction.atomic
    def save(self):
        """Write the week. Call only after ``is_valid``.

        Slots first, because placements and notes need them to exist; then
        deletions before writes, so a person moved between two cells in one
        save is never briefly in both.
        """
        for form in self.slots.forms:
            if form.instance.pk and self.slots._should_delete_form(form):
                form.instance.delete()           # takes its shifts and notes along

        saved = {}
        for key, form in self.slot_forms.items():
            slot = form.save(commit=False)
            slot.week = self.monday
            slot.save()
            form.save_m2m()
            saved[key] = slot

        for form in self.doomed_placements:
            if form.instance.pk and Shift.objects.filter(pk=form.instance.pk).exists():
                form.instance.delete()
        for note in self.doomed_notes:
            if CellNote.objects.filter(pk=note.pk).exists():
                note.delete()

        for form, slot_form, day, area, start, end in self.placements:
            shift = form.save(commit=False)
            shift.slot = saved[slot_form.slot_key]
            shift.date = day
            shift.area = area
            shift.start = start
            shift.end = end
            shift.save()

        for form, slot_form, day, area, text in self.note_rows:
            note = form.save(commit=False)
            note.slot = saved[slot_form.slot_key]
            note.date = day
            note.area = area
            note.text = text
            note.save()

        PlannedWeek.objects.update_or_create(week=self.monday)


# --------------------------------------------------------------------------
# A new week, drafted from the last one
# --------------------------------------------------------------------------

def draft_from(source_monday, target_monday, unavailable):
    """The ``(slots, placements, notes)`` initial lists for a copied week.

    ``unavailable(employee, day)`` says whether somebody cannot be placed on a
    date of the new week — away, not employed, a public holiday. Those
    placements are left out rather than copied in red, because a copied week
    full of people who are on holiday is a week the manager has to empty
    before they can start; the person is still there in the list below the
    grid, in red, which says the same thing without the clearing up.

    Returns the three lists and how many placements were left out.
    """
    offset = target_monday - source_monday
    keys = {}
    slot_rows = []
    for index, slot in enumerate(
        TimeSlot.objects.filter(week=source_monday).prefetch_related("areas"), start=1,
    ):
        key = f"{NEW_SLOT_PREFIX}{index}"
        keys[slot.pk] = key
        slot_rows.append({
            "key": key, "start": slot.start, "end": slot.end,
            "areas": [area.pk for area in slot.areas.all()],
        })

    place_rows = []
    left_out = 0
    for shift in (
        Shift.objects.filter(slot__week=source_monday, slot__isnull=False)
        .select_related("employee", "slot").order_by("date", "slot__start")
    ):
        if shift.date.weekday() >= GRID_DAYS:
            continue
        day = shift.date + offset
        if unavailable(shift.employee, day):
            left_out += 1
            continue
        row = {"employee": shift.employee_id,
               "cell": cell_key(keys[shift.slot_id], day, shift.area_id)}
        if shift.start != shift.slot.start:
            row["custom_start"] = shift.start
        if shift.end != shift.slot.end:
            row["custom_end"] = shift.end
        place_rows.append(row)

    note_rows = [
        {"cell": cell_key(keys[note.slot_id], note.date + offset, note.area_id), "text": note.text}
        for note in CellNote.objects.filter(slot__week=source_monday)
    ]
    return (slot_rows, place_rows, note_rows), left_out


# --------------------------------------------------------------------------
# The areas themselves
# --------------------------------------------------------------------------

class AreaForm(forms.ModelForm):
    class Meta:
        model = Area
        fields = ["name", "icon", "is_active"]
        widgets = {
            # Radio buttons drawn as the icons themselves (templates/roster/
            # areas.html): a select of words like "Palette" asks somebody to
            # imagine the picture the cell will show.
            "icon": forms.RadioSelect(),
            "name": forms.TextInput(attrs={"maxlength": 60}),
        }


AreaFormSet = modelformset_factory(Area, form=AreaForm, extra=0, can_delete=True)
