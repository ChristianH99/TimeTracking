"""Forms for the working time rules.

Everything here edits a *policy*. That is worth stating because it changes what
validation is for: a form that records something guards against typos, and a
form that sets a rule guards against a number that will silently move every
employee's entitlement the moment it is saved. The two clean methods below are
both the second kind.
"""

from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from apps.organisation.models import (
    AssignmentMode, BreakRule, OrgSettings, SpecialLeaveThreshold, SpecialLeaveType,
)
from apps.timesheets.fields import BreakMinutesField, DurationField, TimeOfDayField
from apps.timesheets.zones import DEFAULT_ZONE, all_zone_names


class OrgSettingsForm(forms.ModelForm):
    day_start = TimeOfDayField(label=_("the day usually starts at"))

    class Meta:
        model = OrgSettings
        fields = [
            "full_time_days_per_week", "full_time_leave_days",
            "statutory_leave_days", "leave_rounding",
            "statutory_expires", "statutory_deadline_month", "statutory_deadline_day",
            "employer_expires", "employer_deadline_month", "employer_deadline_day",
            "land", "time_zone", "day_start",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A select, never a text box. A mistyped zone key falls back silently to
        # Berlin (apps/timesheets/zones.py), and a silent fallback on a settings
        # page is the one thing a settings page must not have.
        current = self.initial.get("time_zone") or getattr(self.instance, "time_zone", "")
        names = all_zone_names()
        if current and current not in names:
            names = sorted({*names, current})
        self.fields["time_zone"] = forms.ChoiceField(
            label=_("time zone"),
            choices=[(name, name) for name in names],
            initial=current or DEFAULT_ZONE,
            help_text=_(
                "The clock the workplace keeps. It decides which date a start "
                "belongs to and how long a shift across the night the clocks change "
                "actually was."
            ),
        )

    def clean(self):
        data = super().clean()
        full = data.get("full_time_leave_days")
        statutory = data.get("statutory_leave_days")
        if full is not None and statutory is not None and statutory > full:
            # Not fatal — `statutory_days_for` already caps it, erring towards
            # protection — but it is certainly a typo, and a page that accepted
            # it silently would leave an installation whose "extra" leave is a
            # negative number nobody can find.
            self.add_error("statutory_leave_days", _(
                "The statutory part cannot be more than the whole entitlement. Raise "
                "the full-time figure, or lower this one."
            ))

        for prefix in ("statutory", "employer"):
            month = data.get(f"{prefix}_deadline_month")
            day = data.get(f"{prefix}_deadline_day")
            if month and day and day > 28:
                # 31 February is a thing somebody types, and the model clamps it
                # to the end of the month rather than raising. Saying so here is
                # what stops the clamping being a surprise in a leap year.
                import calendar

                longest = max(calendar.monthrange(2024, month)[1], 28)
                if day > longest:
                    self.add_error(f"{prefix}_deadline_day", _(
                        "There is no such day in that month. It will be read as the "
                        "last day of it."
                    ))
        return data


class BreakRuleForm(forms.ModelForm):
    """One tier, typed in hours rather than minutes.

    The model stores minutes because that is what the arithmetic needs and
    because 7.5 hours is not representable as an integer of them. The *form*
    asks for hours, because a works agreement says "over six hours" and nobody
    reading this page is thinking in 360. The break stays in minutes: nobody
    writes a break as 0.75 hours.
    """

    over_hours = DurationField(
        label=_("working time over"), max_minutes=24 * 60,
        help_text=_("In hours. 6 means “more than six hours of work”."),
    )
    break_minutes = BreakMinutesField(label=_("break"), required=True)

    class Meta:
        model = BreakRule
        fields = ["break_minutes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["over_hours"].initial = self.instance.over_minutes

    def save(self, commit=True):
        rule = super().save(commit=False)
        rule.over_minutes = self.cleaned_data["over_hours"]
        if commit:
            rule.save()
        return rule


class _BreakRuleFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            minutes = form.cleaned_data.get("over_hours")
            if minutes is None:
                continue
            if minutes in seen:
                # Not merely untidy. `required_break` takes the maximum over the
                # rules, so two rows at the same threshold means the smaller
                # break is unreachable — a row on the page that does nothing,
                # which is worse than an error because it looks like it works.
                form.add_error("over_hours", _("There is already a rule at this length."))
            seen.add(minutes)


BreakRuleFormSet = inlineformset_factory(
    OrgSettings, BreakRule, form=BreakRuleForm, formset=_BreakRuleFormSet,
    # extra=0, deliberately: a spare blank row is a row somebody has to delete,
    # and a formset that mints another one when they do is a formset they cannot
    # get rid of. Rows are added by the "+" button instead.
    extra=0, can_delete=True,
)


class SpecialLeaveTypeForm(forms.ModelForm):
    class Meta:
        model = SpecialLeaveType
        fields = ["name", "mode", "days", "is_active"]

    def clean(self):
        data = super().clean()
        mode = data.get("mode")
        if mode == AssignmentMode.THRESHOLD:
            # The table answers instead, and a number here would be a field on
            # the page that changes nothing — see SpecialLeaveType.days_for.
            data["days"] = Decimal("0.0")
        return data


class SpecialLeaveThresholdForm(forms.ModelForm):
    class Meta:
        model = SpecialLeaveThreshold
        fields = ["min_days_per_week", "days"]


class _ThresholdFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        rows = [
            form.cleaned_data for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        if self.instance.mode == AssignmentMode.THRESHOLD and not rows:
            raise forms.ValidationError(
                _("A leave type worked out from a table needs at least one row in it, "
                  "or nobody gets any of it.")
            )
        seen = set()
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            days = form.cleaned_data.get("min_days_per_week")
            if days in seen:
                form.add_error("min_days_per_week", _("There is already a row for this many days."))
            seen.add(days)


ThresholdFormSet = inlineformset_factory(
    SpecialLeaveType, SpecialLeaveThreshold, form=SpecialLeaveThresholdForm,
    formset=_ThresholdFormSet, extra=0, can_delete=True,
)
