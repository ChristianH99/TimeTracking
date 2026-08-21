"""The working time rules: breaks, entitlement, public holidays, closures.

Every page here is ``@staff_required``. That is the software-administration
right rather than the manager right, and the split is deliberate: a deputy head
plans the roster and decides holiday requests (``manager_required``) but must
not be able to change what a day of leave is worth to everybody at once.
"""

import datetime as dt

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.absences.models import BankHoliday, CompanyClosure
from apps.accounts.permissions import staff_required
from apps.organisation.forms import (
    BreakRuleFormSet, OrgSettingsForm, SpecialLeaveTypeForm, ThresholdFormSet,
)
from apps.organisation.models import (
    DEFAULT_BREAK_RULES, AssignmentMode, BreakRule, OrgSettings, SpecialLeaveType,
)


@staff_required
def settings_view(request):
    """The singleton and its break table, on one page.

    One form and one formset saved together, because they are one decision: a
    page where the thresholds could be saved without the rounding would let
    somebody leave halfway through changing a policy, and the half-applied state
    is what everybody's timesheet computes against until they come back.
    """
    current = OrgSettings.current()

    if request.method == "POST":
        form = OrgSettingsForm(request.POST, instance=current)
        # The formset needs a saved parent for its foreign key, and `current` is
        # unsaved on a database that has never had this page opened. So the
        # settings are saved first and the formset is bound to the result.
        if form.is_valid():
            saved = form.save()
            formset = BreakRuleFormSet(request.POST, instance=saved)
            if formset.is_valid():
                formset.save()
                messages.success(request, _("The working time rules were saved."))
                return redirect("organisation:settings")
        else:
            formset = BreakRuleFormSet(request.POST, instance=current if current.is_stored else None)
    else:
        form = OrgSettingsForm(instance=current)
        formset = BreakRuleFormSet(instance=current if current.is_stored else None)

    return render(request, "organisation/settings.html", {
        "form": form,
        "formset": formset,
        # Offered when the table is empty, so that a fresh installation is one
        # click from the rules it computes against by default anyway — rather
        # than a page of empty boxes that hides what the app is already doing.
        "offer_defaults": not current.is_stored or not current.break_rules.exists(),
        "default_rules": [(over // 60, length) for over, length in DEFAULT_BREAK_RULES],
        # Worked examples, rendered from the live rules. The resolution in
        # `required_break` is not the obvious one and a table of three days is
        # the only way to show that it is doing what somebody expects.
        "examples": _break_examples(current),
    })


def _break_examples(settings):
    """``[(gross label, break, net label), …]`` for four representative days.

    Chosen to show the three things the naive implementation gets wrong: a day
    just over the first threshold (which needs *part* of a break, not all of
    it), a day just over the second (which does not reach the second tier once
    its own break is taken off), and a long one that does.
    """
    from apps.timesheets.hours import clock

    rules = list(settings.break_rules.all()) if settings.is_stored else None
    rows = []
    for gross in (300, 365, 390, 485, 600):
        length = settings.required_break(gross, rules=rules)
        rows.append((clock(gross), length, clock(gross - length)))
    return rows


@staff_required
@require_POST
def install_default_break_rules(request):
    """Write the two default tiers. Only ever onto an empty table.

    Guarded rather than trusted to the button being hidden: a POST that arrived
    twice would otherwise double the rules, and two rows at one threshold make
    the smaller break unreachable.
    """
    current = OrgSettings.current()
    if not current.is_stored:
        current.save()
    if current.break_rules.exists():
        messages.info(request, _("There are already break rules; nothing was changed."))
        return redirect("organisation:settings")
    BreakRule.objects.bulk_create([
        BreakRule(settings=current, over_minutes=over, break_minutes=length)
        for over, length in DEFAULT_BREAK_RULES
    ])
    messages.success(request, _("The usual break rules were added."))
    return redirect("organisation:settings")


# --------------------------------------------------------------------------
# Special leave types
# --------------------------------------------------------------------------

@staff_required
def leave_types(request):
    types = SpecialLeaveType.objects.prefetch_related("thresholds", "grants")
    settings = OrgSettings.current()
    rows = []
    for leave_type in types:
        rows.append({
            "type": leave_type,
            "granted_to": leave_type.grants.count(),
            # What a full-week employee would get, so the list says what the
            # rule *means* rather than only what mode it is in.
            "full_time_days": leave_type.days_for(
                settings.full_time_days_per_week, settings=settings,
            ),
        })
    return render(request, "organisation/leave_types.html", {
        "rows": rows, "settings": settings,
    })


@staff_required
def leave_type_form(request, pk=None):
    """Add or edit a type, with its threshold table underneath.

    One view for both, because the two pages differ by a heading. The formset is
    only meaningful for the threshold mode and the page hides it otherwise —
    but it is always bound, since somebody switching a type *to* that mode in
    the same save has to be able to fill the table in at the same time.
    """
    instance = get_object_or_404(SpecialLeaveType, pk=pk) if pk else SpecialLeaveType()

    if request.method == "POST":
        form = SpecialLeaveTypeForm(request.POST, instance=instance)
        if form.is_valid():
            saved = form.save()
            formset = ThresholdFormSet(request.POST, instance=saved)
            if formset.is_valid():
                formset.save()
                messages.success(request, _("“%(name)s” was saved.") % {"name": saved.name})
                return redirect("organisation:leave-types")
            # The type is saved and the table is not, which is recoverable and
            # visible: the page comes back with the errors on the rows. Rolling
            # the type back would throw away the rest of what they typed.
        else:
            formset = ThresholdFormSet(request.POST, instance=instance if instance.pk else None)
    else:
        form = SpecialLeaveTypeForm(instance=instance)
        formset = ThresholdFormSet(instance=instance if instance.pk else None)

    return render(request, "organisation/leave_type_form.html", {
        "form": form, "formset": formset, "leave_type": instance if instance.pk else None,
        "threshold_mode": AssignmentMode.THRESHOLD,
    })


@staff_required
@require_POST
def leave_type_delete(request, pk):
    """Delete a type, or refuse when leave has been taken against it.

    ``Absence.special_type`` is ``PROTECT``, so the database would refuse this
    anyway — with a 500. Asking first turns that into a sentence explaining what
    to do instead, which is to switch the type off: that keeps the days already
    taken attributable and stops anybody being granted it.
    """
    leave_type = get_object_or_404(SpecialLeaveType, pk=pk)
    if leave_type.absences.exists():
        messages.error(request, _(
            "“%(name)s” cannot be deleted: leave has been taken against it and the "
            "record of it would lose its name. Switch it off instead — nobody new "
            "gets it and the days already taken keep their meaning."
        ) % {"name": leave_type.name})
        return redirect("organisation:leave-types")
    name = leave_type.name
    leave_type.delete()
    messages.success(request, _("“%(name)s” was deleted.") % {"name": name})
    return redirect("organisation:leave-types")


# --------------------------------------------------------------------------
# Public holidays
# --------------------------------------------------------------------------

@staff_required
def holidays(request):
    year = _year_from(request)
    first, last = dt.date(year, 1, 1), dt.date(year, 12, 31)
    settings = OrgSettings.current()
    return render(request, "organisation/holidays.html", {
        "year": year,
        "years": range(year - 2, year + 3),
        "settings": settings,
        "land_label": settings.get_land_display(),
        "holidays": BankHoliday.objects.filter(date__gte=first, date__lte=last),
    })


@staff_required
@require_POST
def holidays_generate(request):
    year = _year_from(request)
    settings = OrgSettings.current()
    added, removed = BankHoliday.generate(year, settings.land)
    messages.success(request, _(
        "%(added)s public holidays for %(year)s in %(land)s. "
        "%(removed)s previously generated ones were replaced; anything added by "
        "hand was left alone."
    ) % {"added": added, "year": year, "land": settings.get_land_display(),
         "removed": removed})
    return redirect(f"{reverse('organisation:holidays')}?year={year}")


def _year_from(request):
    """The year a page is showing, defaulting to this one.

    Anything unparseable falls back rather than raising: this arrives in a query
    string, and a 500 on ``?year=banana`` is a page somebody can break with a
    typo in the address bar.
    """
    raw = request.GET.get("year") or request.POST.get("year")
    try:
        year = int(raw)
    except (TypeError, ValueError):
        return dt.date.today().year
    return year if 1970 <= year <= 2200 else dt.date.today().year


# --------------------------------------------------------------------------
# Closures
# --------------------------------------------------------------------------

from django import forms as django_forms  # noqa: E402  (used only below)


class ClosureForm(django_forms.ModelForm):
    class Meta:
        model = CompanyClosure
        fields = ["name", "start_date", "end_date", "deducts_leave"]
        widgets = {
            "start_date": django_forms.DateInput(attrs={"type": "date"}),
            "end_date": django_forms.DateInput(attrs={"type": "date"}),
        }


@staff_required
def closures(request):
    rows = CompanyClosure.objects.prefetch_related("absences")
    return render(request, "organisation/closures.html", {"closures": rows})


@staff_required
def closure_form(request, pk=None):
    instance = get_object_or_404(CompanyClosure, pk=pk) if pk else None
    if request.method == "POST":
        form = ClosureForm(request.POST, instance=instance)
        if form.is_valid():
            closure = form.save()
            # Materialised now rather than consulted at read time — see the
            # model. Re-applying on every save is what makes moving the dates
            # move everybody's absence rather than leaving the old one behind.
            closure.apply()
            messages.success(request, _(
                "“%(name)s” was saved and applied to everybody currently employed."
            ) % {"name": closure.name})
            return redirect("organisation:closures")
    else:
        form = ClosureForm(instance=instance)
    return render(request, "organisation/closure_form.html", {
        "form": form, "closure": instance,
    })


@staff_required
@require_POST
def closure_delete(request, pk):
    closure = get_object_or_404(CompanyClosure, pk=pk)
    name = closure.name
    # CASCADE takes the absences with it, which is right: the closure is the
    # only reason those rows exist, and leaving them behind would charge
    # everybody leave for a shutdown that is not happening.
    closure.delete()
    messages.success(request, _(
        "“%(name)s” was deleted and the days it took off everybody were given back."
    ) % {"name": name})
    return redirect("organisation:closures")
