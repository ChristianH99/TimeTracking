"""The running hours balance: everything worked, against everything owed.

The week page has always been able to say "this week you are 1:15 short". What
it could not say is the sentence people actually ask for — **"and where does
that leave me overall?"** — and without that, an opening balance carried in from
a previous contract has nowhere to appear. A number that is stored and never
shown is a number nobody can check.

    balance = opening + Σ(worked + credited − contracted), from the opening
              date up to and including the date asked about

Three things about that formula are decisions rather than arithmetic.

**It starts at the opening date, not at the beginning of time.** Days before
somebody's contract began are not a shortfall — they were not employed. The
opening figure *is* the summary of everything before that date, agreed with
them, and re-deriving anything behind it would be second-guessing an agreement.

**It is derived, never stored.** The same argument as ``absences.Balance``: a
stored total has to be kept in step with every day entered, every day corrected,
every absence approved and every contract change that moves the contracted hours
underneath it. Each of those is a chance for the figure and the days to
disagree, and when they do, the number on the page is wrong with nothing on the
page to show it. The cost is a walk over the days, which for one person over two
years is two queries and about seven hundred iterations of pure arithmetic.

**A day still running counts as nothing.** Exactly as it does everywhere else —
``WorkSegment.minutes`` returns zero until Stop is pressed, so a balance
refreshed mid-shift does not creep upwards while somebody watches it.

The one invariant worth stating: **over any single week, the change in this
balance equals that week's ``difference`` in ``build_week``.** They are two
readings of one thing and a test holds them to it. If they ever drift, it will
be because one of them learned about a new kind of credited day and the other
did not.
"""

import datetime as dt

from apps.absences.models import BankHoliday, RequestStatus
from apps.timesheets.hours import contracted_minutes
from apps.timesheets.models import DayRecord


def hours_balance(employee, until=None, settings=None):
    """``{opening, worked, credited, contracted, movement, total, …}`` up to a date.

    ``until`` defaults to today. Days in the future are never counted: a
    contract that says eight hours next Tuesday is not a debt somebody has
    already failed to pay, and counting it would make everybody permanently
    behind by the rest of the week.
    """
    from apps.organisation.models import OrgSettings

    settings = settings or OrgSettings.current()
    today = dt.date.today()
    until = min(until or today, today)

    opening = int(employee.opening_balance_minutes or 0)
    first = employee.opening_date

    empty = {
        "employee": employee,
        "opening": opening,
        "opening_on": first,
        "worked": 0,
        "credited": 0,
        "contracted": 0,
        "movement": 0,
        "total": opening,
        "until": until,
        "counted_days": 0,
    }
    if first is None or first > until:
        return empty

    records = {
        record.date: record
        for record in DayRecord.objects
        .filter(employee=employee, date__gte=first, date__lte=until)
        .prefetch_related("segments")
    }
    absences = list(
        employee.absences
        .filter(start_date__lte=until, end_date__gte=first)
        .exclude(status__in=(RequestStatus.REJECTED, RequestStatus.WITHDRAWN))
        .select_related("closure")
    )
    holidays = BankHoliday.dates_between(first, until)

    worked = credited = contracted = counted = 0
    day = first
    step = dt.timedelta(days=1)
    while day <= until:
        due = (
            contracted_minutes(employee.hours_on_weekday(day.weekday(), on=day))
            if employee.works_on(day) else 0
        )
        record = records.get(day)
        absence = next((a for a in absences if a.start_date <= day <= a.end_date), None)

        # The same three branches as `build_week`, deliberately in the same
        # order: an absence credits what it credits, a public holiday credits
        # the whole day, and anything else credits nothing.
        given = 0
        if absence is not None and day not in holidays:
            given = absence.credited_minutes(day, due)
        elif day in holidays and due:
            given = due

        worked += record.worked_minutes if record else 0
        credited += given
        contracted += due
        if due or record or given:
            counted += 1
        day += step

    movement = worked + credited - contracted
    return {
        **empty,
        "worked": worked,
        "credited": credited,
        "contracted": contracted,
        "movement": movement,
        "total": opening + movement,
        "counted_days": counted,
    }
