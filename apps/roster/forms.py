"""The week planner's formset.

The whole week is **one formset of ``Shift`` rows**, and the seven columns on
the page are a rendering of it rather than seven separate things. That shape is chosen for one
reason: dragging a card between columns has to move *the form row itself*, not
copy a value out of one place into another. Two representations of one
week — the cards you can see and a hidden list of what they mean — is the bug
where the picture and the saved roster disagree, and the first edit to disagree
looks like a save that did not take.

So each card carries its own ``date`` as a hidden field, and a drag rewrites
exactly that one input. Everything else about the row travels with it, because
it never left.
"""

import datetime as dt

from django import forms
from django.forms import modelformset_factory
from django.utils.translation import gettext_lazy as _

from apps.employees.models import Employee
from apps.roster.models import Shift
from apps.timesheets.fields import TimeOfDayField


class ShiftForm(forms.ModelForm):
    start = TimeOfDayField(label=_("From"))
    end = TimeOfDayField(label=_("To"))

    class Meta:
        model = Shift
        fields = ["employee", "date", "start", "end", "note"]
        widgets = {
            # Hidden and not disabled: a disabled input is not submitted at all,
            # so a dragged card would come back with no date and the row would
            # be saved onto whatever the form's initial was — silently putting
            # the shift back where it came from.
            "date": forms.HiddenInput(),
            "note": forms.TextInput(attrs={"maxlength": 100}),
        }

    def __init__(self, *args, week_dates=None, employees=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.week_dates = week_dates
        if employees is not None:
            self.fields["employee"].queryset = employees
        self.fields["note"].required = False

    def clean_date(self):
        """A card may only land on a day of the week being edited.

        The date arrives in a hidden field, so it is whatever the browser sent —
        and a page that trusted it would let a bug in the drag handler (or
        anybody with the developer tools open) write a shift into next March
        from a form that says it is editing this week. The page would then look
        completely correct: the row simply would not be on it.
        """
        day = self.cleaned_data["date"]
        if self.week_dates and day not in self.week_dates:
            raise forms.ValidationError(_("That day is not in the week being planned."))
        return day

    def clean(self):
        data = super().clean()
        start, end = data.get("start"), data.get("end")
        if start and end and start == end:
            self.add_error("end", _("A shift needs a length."))
        return data


BaseShiftFormSet = modelformset_factory(
    Shift, form=ShiftForm,
    # extra=0, deliberately: a spare blank card is one somebody has to get rid
    # of, and a formset that mints another when they do is one they cannot. New
    # cards come from the "+" at the foot of a column, which puts one *in the
    # day it was pressed on*.
    extra=0, can_delete=True,
)


class ShiftFormSet(BaseShiftFormSet):
    """Passes the week and the roster-able people down to every row."""

    def __init__(self, *args, week_dates=None, employees=None, **kwargs):
        self.week_dates = week_dates
        self.employees = employees
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["week_dates"] = self.week_dates
        kwargs["employees"] = self.employees
        return kwargs


def rosterable(on_date=None):
    """The people who may be given a shift.

    Employed, and — when a date is given — employed *then*. A select offering
    somebody who left in March is a select that invites a shift nobody will
    work, and the roster is the one page where that mistake is invisible: the
    card looks exactly like every other card.
    """
    people = Employee.objects.filter(is_active=True)
    if on_date is not None:
        people = people.exclude(ended_on__lt=on_date).exclude(started_on__gt=on_date)
    return people


class CopyWeekForm(forms.Form):
    """Which week to copy this one from."""

    source_monday = forms.DateField(
        label=_("copy from the week beginning"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean_source_monday(self):
        day = self.cleaned_data["source_monday"]
        # Normalised rather than refused. Somebody picking a date from a browser
        # date field will land on a Wednesday sooner or later, and "that is not
        # a Monday" is a refusal with nothing useful behind it — the week they
        # meant is unambiguous.
        return day - dt.timedelta(days=day.weekday())
