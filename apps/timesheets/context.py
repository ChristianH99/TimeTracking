"""Start and Stop, on every page.

The clock used to be a block on the timesheet, and moving it into the topbar is
what makes this file necessary: a control that is on every page cannot be
supplied by one view.

It is here rather than folded into ``apps.employees.context.who`` for a layering
reason and not a cost one. ``employees`` is the lower app and ``timesheets``
imports *it*; a processor in ``employees`` that reached into clocking would turn
that into a cycle. The employee row itself is not fetched twice — the reverse
one-to-one is cached on the account by whichever of the two processors touches
it first.

**One query per page, and only when there is somebody to ask.** ``open_stretch``
is a single indexed lookup over two dates of one employee's segments, which is
what a control on every page costs. An account with no employee row behind it —
a fresh administrator, an SSO identity that has not been linked yet — has nobody
to clock in, so nothing is fetched and the topbar simply renders no button.
"""


def clock(request):
    """``clock`` — whatever ``_clock.html`` needs, or ``None``.

    ``None`` rather than a dictionary of falsy values, so the template's single
    ``{% if clock %}`` covers both "not signed in" and "no employee row" without
    the markup having to know the difference between them.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"clock": None}

    # Late, and deliberately: this module is named in the settings' context
    # processor list, so importing at module scope would drag the timesheet app
    # into the settings import and through it every model in the project.
    from apps.employees.models import Employee
    from apps.timesheets import clocking
    from apps.timesheets.zones import local_today, zone_for

    employee = Employee.for_user(user)
    if employee is None:
        return {"clock": None}

    state = clocking.state_for(employee)
    # The wall clock as a number, so `shell.js` can tick it forward by real
    # elapsed time rather than by asking the browser what time it is — the
    # browser's answer is a different clock for anybody whose `time_zone` is
    # filled in, which is the one case that field exists for.
    state["now_minutes"] = state["now"].hour * 60 + state["now"].minute
    # Today on *their* clock, not the server's. A stretch started at 23:40 in
    # Lisbon is still today for them and yesterday for a Berlin server, and the
    # bar prints the date only when the two differ — getting that from the wrong
    # clock puts a date on every running shift for half the day.
    state["today"] = local_today(zone_for(employee))
    return {"clock": state}
