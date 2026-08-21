"""The contract form, the special leave granted with it, and changing hours.

**The seven hour boxes are not fields on ``Employee`` any more.** They belong to
a ``ContractPeriod`` — one row per change, each with the date it took effect —
and this form is the door between "a manager typed seven numbers" and "the
employee is on these hours from this date".

That door has two sides and they are deliberately different forms:

* ``EmployeeForm`` sets up somebody. The hours it takes are their *first*
  contract, in force from the day they started.
* ``ContractChangeForm`` changes somebody. It insists on a date and defends the
  thing the whole model exists for — that a change dated in the past silently
  rewrites weeks that have already been worked, signed off and possibly paid.
"""

import datetime as dt
from decimal import Decimal

from django import forms
from django.db import models
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from apps.employees.models import (
    HOURS_FIELDS, WEEKDAYS, ContractPeriod, Employee, SpecialLeaveGrant,
)
from apps.organisation.models import OrgSettings, SpecialLeaveType
from apps.timesheets.fields import ContractHoursField, SignedDurationField
from apps.timesheets.zones import DEFAULT_ZONE, all_zone_names


def _hour_fields():
    """The seven boxes, in weekday order.

    Read by ``apps/timesheets/timeparse.py``, so "8", "8:30", "8,5" and "830"
    all work. A ``NumberInput`` refuses a colon outright, which is the notation
    half the people filling this in will reach for first — see
    ``apps/timesheets/fields.py`` for the full argument against the native
    widgets.
    """
    return {
        name: ContractHoursField(label=label, required=False)
        for name, (_index, label) in zip(HOURS_FIELDS, WEEKDAYS)
    }


def _zone_choices(current=""):
    """Every zone this machine knows, with "same as the workplace" at the top.

    A select rather than a text box, because a mistyped key falls back silently
    to the default (``apps/timesheets/zones.py``) and a silent fallback is
    exactly what a settings page must not have. The blank option is the answer
    for everybody in an ordinary business and is therefore first.
    """
    names = all_zone_names()
    if current and current not in names:
        # A zone stored before this machine's tzdata was cut back. Keeping it on
        # the list means opening the page does not quietly change it to Berlin.
        names = sorted({*names, current})
    return [("", _("the same as the workplace"))] + [(name, name) for name in names]


class EmployeeForm(forms.ModelForm):
    """Who somebody is, plus the hours they start on."""

    class Meta:
        model = Employee
        fields = [
            "first_name", "last_name", "username", "time_zone",
            "is_manager", "is_active", "started_on", "ended_on",
            "leave_days_override",
            "opening_balance_minutes", "opening_leave_days", "opening_balance_on",
        ]
        widgets = {
            "started_on": forms.DateInput(attrs={"type": "date"}),
            "ended_on": forms.DateInput(attrs={"type": "date"}),
            "opening_balance_on": forms.DateInput(attrs={"type": "date"}),
            # data-username-target is what static/js/employee_form.js fills from
            # the two name boxes. A suggestion, never applied behind somebody's
            # back — see Employee.suggest_username.
            "username": forms.TextInput(attrs={
                "autocomplete": "off", "spellcheck": "false",
                "data-username-target": "1", "placeholder": "anna.berger",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in _hour_fields().items():
            self.fields[name] = field

        # Signed, because somebody can arrive owing hours as easily as being
        # owed them, and read by the same parser as every other duration — so
        # "-14", "-14:00" and "-14,0" are one answer. `type="text"`, never
        # `type="number"`: a number input rejects "-8:30" by *emptying itself*,
        # which is the one thing a box whose validation message quotes the value
        # back cannot afford.
        self.fields["opening_balance_minutes"] = SignedDurationField(
            label=_("hours brought with them"), required=False,
            max_minutes=520 * 60,
            help_text=_(
                "Hours already owed to them, or by them, on the date below. "
                "Write a minus in front if they start in debit — “-14” or “-14:00”."
            ),
        )
        self.fields["opening_leave_days"].required = False
        self.fields["opening_balance_on"].required = False

        self.fields["time_zone"] = forms.ChoiceField(
            label=_("time zone"), required=False,
            choices=_zone_choices(getattr(self.instance, "time_zone", "")),
            help_text=_("Only for somebody who works in a different one from the workplace."),
        )

        # The hours the boxes start with are **the contract in force today**,
        # not the newest row. Those differ for a change a manager has already
        # dated into next month, and showing the future one would make this page
        # say somebody is on hours they are not yet on.
        contract = self.instance.current_contract if self.instance.pk else None
        if contract is not None:
            for name in HOURS_FIELDS:
                self.fields[name].initial = getattr(contract, name)

    def clean_username(self):
        """Folded to lower case, because a directory does not distinguish.

        Stored folded rather than merely compared folded, so the People page and
        the contract show the same string — two rows reading `Anna.Berger` and
        `anna.berger` are one person to LDAP and look like two here.
        """
        return (self.cleaned_data["username"] or "").strip().lower()

    def clean_time_zone(self):
        value = (self.cleaned_data.get("time_zone") or "").strip()
        return "" if value == DEFAULT_ZONE and not self.instance.pk else value

    def clean_opening_balance_minutes(self):
        """An empty box is nought, not ``None``.

        The column is NOT NULL and "nothing brought with them" is what almost
        every row says — turning a blank into an error would make a manager
        answer a question about a case that does not apply to them.
        """
        return self.cleaned_data.get("opening_balance_minutes") or 0

    def clean_opening_leave_days(self):
        return self.cleaned_data.get("opening_leave_days") or Decimal("0")

    def clean(self):
        data = super().clean()
        started, ended = data.get("started_on"), data.get("ended_on")
        if started and ended and ended < started:
            self.add_error("ended_on", _("They cannot leave before they started."))

        # An opening figure with no date cannot be attributed to a year, so the
        # leave half of it would be counted into none — stored, invisible, and
        # impossible to explain. Filled in rather than refused, because the
        # answer is always the day they started and asking for it twice is
        # asking somebody to do the computer's job.
        opening = data.get("opening_balance_on")
        brought = data.get("opening_balance_minutes") or 0
        days = data.get("opening_leave_days") or Decimal("0")
        if (brought or days) and not opening:
            if started:
                data["opening_balance_on"] = started
            else:
                self.add_error("opening_balance_on", _(
                    "Say when those figures were true. Without a date the leave days "
                    "cannot be counted into a year, and they would be lost."
                ))
        if opening and started and opening < started:
            self.add_error("opening_balance_on", _(
                "That is before they started here. The figures they arrived with are "
                "true on their first day, not before it."
            ))

        worked = sum(
            (data.get(name) or Decimal("0")) for name in HOURS_FIELDS
        )
        if worked <= 0 and data.get("is_active"):
            # Not a formality. Every leave figure divides by the number of
            # working days, and a contract with none is somebody who can be
            # rostered, can request holiday, and is entitled to nothing — which
            # is a page of zeros nobody can explain.
            self.add_error(None, _(
                "This contract has no working hours in it. Give at least one day "
                "some hours, or switch the employee off if they have left."
            ))
        return data

    def save(self, commit=True):
        """Save the person, then write the hours as a contract period.

        The period is dated from the day they started, or from today for a row
        that does not say. Editing the boxes on this page **moves that same
        period** rather than adding a second one: fixing a typo in somebody's
        Tuesday an hour after creating them is a correction, and recording it as
        a mid-year contract change would put a change on their record that never
        happened. Changing hours for real is ``ContractChangeForm``, which is a
        separate page with a date on it and says so.
        """
        employee = super().save(commit=commit)
        if not commit:
            return employee
        hours = [self.cleaned_data.get(name) or Decimal("0") for name in HOURS_FIELDS]
        first = employee.contract_periods.order_by("valid_from").first()
        employee.set_hours(
            hours,
            valid_from=first.valid_from if first else (employee.started_on or dt.date.today()),
            note=first.note if first else "",
        )
        return employee


class ContractChangeForm(forms.ModelForm):
    """New hours from a date. The one way a contract changes after day one.

    Separate from ``EmployeeForm`` on purpose. A manager who opens the contract
    page to correct a spelling must not be able to rewrite somebody's working
    week as a side effect, and a manager who *means* to change the hours needs
    to be asked the one question that page cannot ask: **from when**.

    Everything before that date keeps the previous hours, which is what makes an
    already-confirmed week reproduce. Everything after it — the leave
    entitlement, whether a Wednesday is a working day, what the roster expects —
    follows the new row without anything being recalculated and stored, because
    none of it was ever stored in the first place.
    """

    class Meta:
        model = ContractPeriod
        fields = ["valid_from", "note"]
        widgets = {
            "valid_from": forms.DateInput(attrs={"type": "date"}),
            "note": forms.TextInput(attrs={"maxlength": 200}),
        }

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        self.fields["note"].required = False
        for name, field in _hour_fields().items():
            self.fields[name] = field
            if employee is not None and not self.is_bound:
                contract = employee.current_contract
                if contract is not None:
                    field.initial = getattr(contract, name)

    def clean_valid_from(self):
        """Refuse a date before the employee existed, and warn about the past.

        A change dated before somebody started has no meaning — there is no
        earlier contract for it to succeed — and it would leave the first period
        stranded behind a row that claims to precede it.
        """
        day = self.cleaned_data["valid_from"]
        started = getattr(self.employee, "started_on", None)
        if started and day < started:
            raise forms.ValidationError(_(
                "That is before %(name)s started on %(started)s. A contract cannot "
                "begin before the employment does."
            ) % {
                "name": self.employee.full_name,
                "started": started.strftime("%d.%m.%Y"),
            })
        return day

    def clean(self):
        data = super().clean()
        worked = sum((data.get(name) or Decimal("0")) for name in HOURS_FIELDS)
        if worked <= 0:
            self.add_error(None, _(
                "This contract has no working hours in it. Give at least one day some "
                "hours — a contract of nothing is not how somebody stops working here."
            ))
        return data

    @property
    def rewrites_confirmed_days(self):
        """Whether this change is dated over days somebody has already signed off.

        Not an error and not blocked — backdating a change is a real and ordinary
        thing, because paperwork is slow and the agreement was made in April even
        if it was typed in June. What it must not be is *silent*: the days
        between the date and today were confirmed against the old contract, and
        their shortfall or surplus is about to move. The page says how many, and
        the manager decides.
        """
        day = self.cleaned_data.get("valid_from") if self.is_bound else None
        if not day or day >= dt.date.today() or self.employee is None:
            return 0
        return self.employee.days.filter(
            date__gte=day, date__lt=dt.date.today(), confirmed_at__isnull=False,
        ).count()

    def save(self, commit=True):
        period = super().save(commit=False)
        period.employee = self.employee
        for name in HOURS_FIELDS:
            setattr(period, name, self.cleaned_data.get(name) or Decimal("0"))
        if commit:
            # update_or_create rather than save, so that correcting a change
            # made this morning replaces it instead of failing on the one
            # contract per start date constraint — which is what a manager
            # fixing their own typo would otherwise hit.
            period = self.employee.set_hours(
                [getattr(period, name) for name in HOURS_FIELDS],
                valid_from=period.valid_from, note=period.note,
            )
        return period


class SpecialLeaveGrantForm(forms.ModelForm):
    class Meta:
        model = SpecialLeaveGrant
        fields = ["leave_type", "days_override"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # An inactive type must not be offered to anybody new, but a grant that
        # already names one has to keep it: narrowing the queryset to active
        # types alone would make the existing row invalid, and saving the page
        # for an unrelated reason would then silently drop somebody's leave.
        # So the current value is added back to whatever is on offer.
        offered = SpecialLeaveType.objects.filter(is_active=True)
        current = getattr(self.instance, "leave_type_id", None)
        if current:
            offered = SpecialLeaveType.objects.filter(
                models.Q(is_active=True) | models.Q(pk=current)
            )
        self.fields["leave_type"].queryset = offered


SpecialLeaveGrantFormSet = inlineformset_factory(
    Employee, SpecialLeaveGrant, form=SpecialLeaveGrantForm,
    extra=0, can_delete=True,
)


def leave_preview(employee, settings=None, year=None):
    """What this contract is worth in leave, for the panel beside the hours.

    Two figures rather than one, and the pair is the point: what a *full year*
    of these hours buys, and what this person is entitled to in *this* year.
    They differ whenever somebody joined mid-year or their hours changed, which
    is exactly when the difference needs explaining and exactly when a single
    number would be quietly answering the wrong question.
    """
    settings = settings or OrgSettings.current()
    year = year or dt.date.today().year
    return {
        "working_days": employee.working_days_per_week,
        "weekly_hours": employee.weekly_hours,
        "computed": settings.leave_days_for(employee.working_days_per_week),
        "actual": employee.annual_leave_days(settings),
        "this_year": employee.leave_days_in_year(year, settings),
        "year": year,
        "is_override": employee.leave_days_override is not None,
        "full_time_days": settings.full_time_days_per_week,
        "full_time_leave": settings.full_time_leave_days,
        "periods": list(employee.contract_periods.all()),
        "opening_minutes": employee.opening_balance_minutes,
        "opening_leave": employee.opening_leave_days,
        "opening_on": employee.opening_date,
    }
