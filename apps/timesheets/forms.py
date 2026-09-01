"""Entering a day's hours by hand.

The day form is a ``DayRecord`` plus a formset of its segments, and the break is
the interesting field. It is offered as a number of minutes with a checkbox
beside it reading "work it out for me" — checked by default, and unchecking it
is what sets ``break_is_override``. That inversion is deliberate: the common
case is the rules being right, and a form whose default was "I will type it"
would make everybody type the number the app already knows.
"""

import datetime as dt

from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from apps.timesheets.fields import (
    BreakMinutesField, SignedMinutesField, TimeOfDayField,
)
from apps.timesheets.models import DayRecord, WorkSegment
from apps.timesheets.timeparse import clock
from apps.timesheets.zones import nonexistent, zone_for


class WorkSegmentForm(forms.ModelForm):
    # Text boxes read by apps/timesheets/timeparse.py, not `type="time"`. That
    # widget rejects "830" by *emptying itself*, so the page cannot even say
    # what was typed — see apps/timesheets/fields.py.
    start = TimeOfDayField(label=_("From"))
    # Optional, because a stretch that is still running has no end yet — that is
    # what the Stop button fills in. Left empty on a day nobody is standing in,
    # it simply means the same thing: started, not finished.
    end = TimeOfDayField(label=_("To"), required=False)

    class Meta:
        model = WorkSegment
        fields = ["start", "end"]

    def clean(self):
        data = super().clean()
        start, end = data.get("start"), data.get("end")
        if start and end and start == end:
            self.add_error("end", _("This stretch has no length."))
        return data


def _span_label(start, end):
    """``"08:30–17:30"`` for a pair of minute offsets, ``end`` possibly ``None``.

    Named in the error rather than left to "two of those stretches", because on
    a day with four rows on it "two of those" is the start of a hunt. A stretch
    still running is written with its end left open, which is what it looks like
    on the page it is being described from.
    """
    if end is None:
        return _("%(from)s – still running") % {"from": clock(start)}
    return f"{clock(start)}–{clock(end)}"


class _SegmentFormSet(forms.BaseInlineFormSet):
    """Every stretch of one day, checked against every other one.

    Three things are decided here rather than on a row, because each of them is
    a statement about the *set* and a per-row check has nothing to compare
    against: that there is at least one stretch, that at most one of them is
    still running, and that no two of them cover the same minute.
    """

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        live = [
            form.cleaned_data for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        if not live:
            raise forms.ValidationError(_(
                "A day needs at least one stretch of work. If you did not work at all, "
                "delete the day instead."
            ))

        self._check_one_running(live)
        self._check_clock_change(live)
        self._check_overlaps(live)

    def _check_one_running(self, live):
        """At most one stretch with no end.

        Two open stretches is a state with no reading: Stop would have to guess
        which of them it ended, and the day's total would be missing two
        unknowns instead of one. One is a shift in progress; two is a mistake,
        and saying so here is the only place it can be said before it is stored.
        """
        running = [row for row in live if row.get("start") and not row.get("end")]
        if len(running) > 1:
            raise forms.ValidationError(_(
                "Only one stretch can be left open at a time. Fill in the end of the "
                "earlier one — a day with two unfinished stretches cannot be added up."
            ))

    def _check_clock_change(self, live):
        """Refuse a clock time that the spring-forward skipped on that date.

        02:30 on the last Sunday in March is not a time that happened, and a
        shift claiming to have started then is a shift measuring an hour short.
        Python will not raise on it — ``ZoneInfo`` resolves it and carries on —
        so this is the only place anybody finds out. Once a year, for the one
        business that rosters that night, and it is the night they most need the
        figure to be right.
        """
        date = getattr(self.instance, "date", None)
        employee = getattr(self.instance, "employee", None)
        if date is None:
            return
        tz = zone_for(employee)
        for row in live:
            for field, value in (("start", row.get("start")), ("end", row.get("end"))):
                # The end of a stretch that runs past midnight is read on the
                # following date, so it is that date's clock change that could
                # have skipped it.
                on = date
                if field == "end" and row.get("start") and value and value <= row["start"]:
                    on = date + dt.timedelta(days=1)
                if value and nonexistent(on, value, tz):
                    raise forms.ValidationError(_(
                        "The clocks went forward on %(date)s, so %(time)s did not happen "
                        "that night. Use the time you actually looked at."
                    ) % {"date": on.strftime("%d.%m.%Y"), "time": value.strftime("%H:%M")})

    def _check_overlaps(self, live):
        """No two stretches may cover the same minute.

        It matters because two overlapping stretches double-count the overlap
        into the day's total, and the total is what the break rules and the
        balance are computed from — so the error is silent and arrives as an
        unexplained surplus at the end of the month.

        Compared as minutes on a timeline rather than as clock values, so that a
        stretch crossing midnight is one interval rather than two clock times in
        the wrong order. The naive version — comparing ``time`` objects directly
        — reports every night shift as an overlap and lets the one real overlap
        through whenever a night shift is on the day.

        **A running stretch has no end and is treated as running to the end of
        time**, because that is what it is: anything else somebody enters that
        starts after it does overlap it, and will still overlap it when Stop is
        finally pressed.
        """
        spans = []
        for row in live:
            start, end = row.get("start"), row.get("end")
            if not start:
                continue
            first = start.hour * 60 + start.minute
            if end is None:
                spans.append((first, None))
                continue
            last = end.hour * 60 + end.minute
            if last <= first:
                last += 24 * 60
            spans.append((first, last))

        # Sorted by start, so anything overlapping a given stretch starts at or
        # after it — which is what lets the inner loop stop at the first row
        # that clears it instead of comparing every pair.
        spans.sort(key=lambda pair: pair[0])
        for index, (first_start, first_end) in enumerate(spans):
            for second_start, second_end in spans[index + 1:]:
                if first_end is not None and second_start >= first_end:
                    break
                raise forms.ValidationError(_(
                    "Two of those stretches overlap — %(first)s and %(second)s. The "
                    "overlapping time would be counted twice."
                ) % {
                    "first": _span_label(first_start, first_end),
                    "second": _span_label(second_start, second_end),
                })


SegmentFormSet = inlineformset_factory(
    DayRecord, WorkSegment, form=WorkSegmentForm, formset=_SegmentFormSet,
    extra=0, can_delete=True, min_num=0,
)


class DayForm(forms.ModelForm):
    """The break and the note. The times live in the formset."""

    automatic_break = forms.BooleanField(
        label=_("work the break out from the rules"), required=False, initial=True,
        help_text=_("Uncheck to enter a different break. A break entered by hand is shown in amber."),
    )

    break_minutes = BreakMinutesField(label=_("Break"))

    # Time that belongs on the day and was never read off a clock. Offered here
    # as well as in the month's pop-up because there must not be a field that
    # can only be edited from one page — the day somebody opens the other one to
    # fix a typo is the day they silently cannot.
    correction_minutes = SignedMinutesField(
        label=_("Correction"),
        help_text=_("Minutes, or 0:30. A minus takes time off the day."),
    )

    class Meta:
        model = DayRecord
        fields = ["break_minutes", "correction_minutes", "correction_reason", "note"]
        widgets = {
            "note": forms.TextInput(attrs={"maxlength": 200}),
            "correction_reason": forms.TextInput(attrs={"maxlength": 200}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note"].required = False
        self.fields["break_minutes"].required = False
        self.fields["correction_reason"].required = False
        if self.instance and self.instance.pk:
            self.fields["automatic_break"].initial = not self.instance.break_is_override

    def clean(self):
        data = super().clean()
        if not data.get("automatic_break") and data.get("break_minutes") is None:
            self.add_error("break_minutes", _(
                "Enter the break, or tick the box to have it worked out."
            ))
        # The same rule as DayRecord.clean, said here so the message lands on
        # the box rather than at the top of the page. A correction nobody can
        # account for is the one entry on a timesheet that cannot be defended,
        # and the person who has to defend it is rarely the one who typed it.
        if data.get("correction_minutes") and not (data.get("correction_reason") or "").strip():
            self.add_error("correction_reason", _(
                "Say why the day was corrected."
            ))
        return data

    def save(self, commit=True, settings=None, rules=None):
        """Set the break from the box, or from the rules.

        **The computed branch only runs when there are segments to compute
        from.** ``apply_break_rules`` reads ``self.segments``, which on a record
        that has never been saved raises outright — a day being entered for the
        first time has no primary key for the relation to hang off. That is not
        a hypothetical: it is every first entry on every unrostered day, and it
        went unnoticed because the existing tests all edited a record that
        already existed.

        So this is safe to call twice and the view calls it twice: once with
        ``commit=False`` to mint the row, and again once the segments are in.
        The first call sets the override flag and the typed value; only the
        second reaches the rules.
        """
        record = super().save(commit=False)
        # An empty box is nought, not None: the column is NOT NULL and the field
        # hands back None for a box nobody filled in, which is most of them.
        record.correction_minutes = self.cleaned_data.get("correction_minutes") or 0
        if not record.correction_minutes:
            record.correction_reason = ""
        record.break_is_override = not self.cleaned_data["automatic_break"]
        if record.break_is_override:
            record.break_minutes = self.cleaned_data.get("break_minutes") or 0
        elif record.pk is not None:
            record.apply_break_rules(settings=settings, rules=rules)
        else:
            # Nought until the second call can work it out. The column is NOT
            # NULL, and the field hands back None for an empty box because the
            # box *is* empty whenever the rules are doing the work — so without
            # this the very first save of a new day fails on a constraint.
            record.break_minutes = 0
        if commit:
            record.save()
        return record
