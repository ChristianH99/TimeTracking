"""Asking for time off, and saying you were ill."""

import datetime as dt

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.absences.models import Absence, AbsenceKind, BankHoliday, RequestStatus
from apps.organisation.models import SpecialLeaveType


class AbsenceRequestForm(forms.ModelForm):
    """Holiday, time off in lieu or special leave, asked for by the person themselves.

    ``kind`` is limited to the three an employee may *ask* for. Sickness is not a
    request and has its own form; a closure is the employer's to declare. A
    single form offering all five would let somebody submit "the workplace was
    closed" for approval, which is not a sentence anybody can act on.
    """

    class Meta:
        model = Absence
        fields = ["kind", "special_type", "start_date", "end_date", "is_half_day", "reason"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.TextInput(attrs={"maxlength": 200}),
        }

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        # The three an employee may *ask* for. Sickness is not a request and has
        # its own form; a closure is the employer's to declare.
        self.fields["kind"].choices = [
            (AbsenceKind.HOLIDAY, AbsenceKind.HOLIDAY.label),
            (AbsenceKind.OVERTIME, AbsenceKind.OVERTIME.label),
            (AbsenceKind.SPECIAL, AbsenceKind.SPECIAL.label),
        ]
        self.fields["reason"].required = False
        self.fields["is_half_day"].required = False
        # Only the types this person has actually been granted. Offering every
        # type in the organisation would let somebody request leave against a
        # balance of zero and have it look like an ordinary request all the way
        # to the manager, who then has to explain why they are declining it.
        granted = SpecialLeaveType.objects.filter(
            grants__employee=employee, is_active=True,
        ) if employee else SpecialLeaveType.objects.none()
        self.fields["special_type"].queryset = granted
        self.fields["special_type"].required = False
        self.fields["special_type"].empty_label = _("—")

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date")
        kind = data.get("kind")

        if start and end and end < start:
            self.add_error("end_date", _("The end is before the start."))
            return data

        if kind == AbsenceKind.SPECIAL and not data.get("special_type"):
            self.add_error("special_type", _("Say which special leave this is."))
        if kind != AbsenceKind.SPECIAL:
            data["special_type"] = None

        if data.get("is_half_day") and start and end and start != end:
            self.add_error("is_half_day", _(
                "A half day is one date. Ask for the whole days as one request and the "
                "half day as another."
            ))
            return data

        if start and end and self.employee:
            if self._days(start, end) == 0:
                # Not a formality: a request worth nothing is one a manager has
                # to read, decide and explain. Refusing it here says the useful
                # thing instead — those are days you were not due in anyway.
                self.add_error(None, _(
                    "You are not due to work on any of those days, so there is nothing "
                    "to book off. Public holidays and days your contract gives no hours "
                    "are not counted."
                ))
            if self._overlaps(start, end):
                self.add_error(None, _(
                    "You already have time off recorded that overlaps these dates."
                ))
        return data

    def _days(self, start, end):
        """Working days in the range — the count, not the entitlement cost.

        A half day is still one working day here. What this answers is "is there
        anything to book off at all", and half of a day somebody works is
        something; half of a day they do not is still nothing.
        """
        holidays = BankHoliday.dates_between(start, end)
        span = (end - start).days
        return sum(
            1 for offset in range(span + 1)
            if (day := start + dt.timedelta(days=offset)) not in holidays
            and self.employee.works_on(day)
        )

    def _overlaps(self, start, end):
        """Whether this person already has something recorded across these dates.

        Excludes declined and withdrawn rows — those are history, not a claim on
        the calendar — and excludes this row when editing, or every save of an
        unchanged request would report it as overlapping itself.
        """
        existing = self.employee.absences.exclude(
            status__in=(RequestStatus.REJECTED, RequestStatus.WITHDRAWN),
        ).filter(start_date__lte=end, end_date__gte=start)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        return existing.exists()


class SickForm(forms.ModelForm):
    """Reporting illness, and handing it to a manager to acknowledge.

    **The acknowledgement is a receipt, not a permission**, and the whole shape
    of this form turns on the difference. An employer does not grant sickness —
    it is a fact being reported — so the row is saved as ``REQUESTED`` for the
    manager to see and confirm, and it counts as sickness *immediately*: the
    hours are credited, the roster stops expecting the person, and the balance
    shows the days. Nothing waits on the button.

    What the button does is put a name and a timestamp against "yes, this was
    reported to me", which is the thing an employer actually needs a record of
    and the thing a paper sick note in a drawer does not have. The manager can
    also refuse to accept it — no Krankmeldung arrived, the dates are wrong —
    and that is the one act that stops the credit. It requires a written reason.

    ``end_date`` is optional, because on the morning somebody rings in nobody
    knows. Left blank it means today, and it is extended later from the same
    page.

    **There is still no diagnosis field and there must never be one.** A sick
    absence records that somebody was ill and never why; adding a note here
    would turn an ordinary attendance record into a health record with no lawful
    basis for holding it.
    """

    class Meta:
        model = Absence
        fields = ["start_date", "end_date", "is_half_day"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, employee=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee = employee
        self.fields["end_date"].required = False
        self.fields["is_half_day"].required = False
        self.fields["end_date"].help_text = _(
            "Leave empty if you do not know yet — you can say when it ended later."
        )

    def clean(self):
        data = super().clean()
        start = data.get("start_date")
        end = data.get("end_date") or start
        if start and end and end < start:
            self.add_error("end_date", _("The end is before the start."))
            return data
        if data.get("is_half_day") and start and end and start != end:
            self.add_error("is_half_day", _("A half day is one date."))
            return data
        data["end_date"] = end
        return data

    def save(self, commit=True):
        absence = super().save(commit=False)
        absence.employee = self.employee
        absence.kind = AbsenceKind.SICK
        absence.special_type = None
        # Waiting to be acknowledged, not waiting to be allowed. `credits_hours`
        # already treats a reported sick day as a sick day; this status only
        # decides whether it is still on the manager's list.
        absence.status = RequestStatus.REQUESTED
        absence.end_date = self.cleaned_data["end_date"]
        if commit:
            absence.save()
        return absence


class DecisionForm(forms.Form):
    """A manager's answer, with room for a sentence.

    The note is optional for an approval and not for a refusal. Somebody whose
    holiday is declined with no reason has to go and ask, and the answer exists
    already in the head of the person who pressed the button.
    """

    approve = forms.BooleanField(required=False)
    note = forms.CharField(
        label=_("reply"), max_length=200, required=False,
        widget=forms.TextInput(attrs={"maxlength": 200}),
    )

    def clean(self):
        data = super().clean()
        if not data.get("approve") and not (data.get("note") or "").strip():
            self.add_error("note", _(
                "Say why. Somebody whose time off is declined without a reason has "
                "to come and ask for one."
            ))
        return data
