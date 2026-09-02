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
            self._refuse_locked_dates(start, end)
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

    def _refuse_locked_dates(self, start, end):
        """No absence may be written across a day somebody has closed.

        Here rather than in each view, because a status is an absence whichever
        door it came through — the timesheet's status cell, this page's own
        form, or a sick report — and a lock only one of them honoured would be a
        lock anybody could walk round by using another.

        The dates are named. "Part of that is locked" sends somebody hunting
        through a fortnight for the day that is.
        """
        from apps.timesheets.models import DayLock

        locked = sorted(DayLock.dates_between(self.employee, start, end))
        if locked:
            self.add_error(None, _(
                "%(dates)s is locked, so nothing can be booked across it. Ask a "
                "manager to unlock it."
            ) % {"dates": ", ".join(day.strftime("%d.%m.%Y") for day in locked[:5])})

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
    """Reporting illness — asked for, and decided, like every other absence.

    **This form used to be the odd one out and deliberately is not any more.**
    It saved a row that counted immediately, on the argument that an employer
    does not *grant* illness; the manager's button was a receipt rather than a
    permission, and only a positive refusal stopped the hours being credited.
    One absence type behaving unlike every other cost more than it bought: the
    timesheet had to say two different things about what a waiting day meant,
    and a report against the wrong dates credited hours until somebody noticed.

    So a sick day is now ``REQUESTED``, credits nothing until it is approved,
    and is refused with a written reason like anything else. What stays
    different is the only thing that is actually different about it: **it costs
    no leave**, ever.

    ``end_date`` is required, the same as on a request. It used to be optional
    — blank meant "today, and I will say later" — which is the honest state on
    the morning somebody rings in, and it is the state that made an open-ended
    absence possible. Somebody who does not yet know books the days they know
    about.

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
        self.fields["is_half_day"].required = False

    def clean(self):
        data = super().clean()
        start, end = data.get("start_date"), data.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("The end is before the start."))
            return data
        if data.get("is_half_day") and start and end and start != end:
            self.add_error("is_half_day", _("A half day is one date."))
            return data
        if start and end and self.employee:
            self._refuse_locked_dates(start, end)
        return data

    # The same rule as the request form's, and deliberately the same words: a
    # sick day written into a closed month changes the hours that month was
    # signed off on, whichever form it arrived through.
    _refuse_locked_dates = AbsenceRequestForm._refuse_locked_dates

    def save(self, commit=True):
        absence = super().save(commit=False)
        absence.employee = self.employee
        absence.kind = AbsenceKind.SICK
        absence.special_type = None
        # Waiting to be decided, the same as anything else. Nothing is credited
        # and nothing is counted until a manager answers.
        absence.status = RequestStatus.REQUESTED
        if commit:
            absence.save()
        return absence


class DecisionForm(forms.Form):
    """A manager's answer, with room for a sentence.

    Answers a request and a cancellation alike, because both are the same shape:
    yes or no, and a sentence that is compulsory when the answer is no. Somebody
    whose holiday is declined with no reason has to go and ask, and the answer
    exists already in the head of the person who pressed the button.
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
