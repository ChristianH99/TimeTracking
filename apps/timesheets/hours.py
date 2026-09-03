"""Writing a duration down.

Everything in this app measures time in **whole minutes, as an integer**, from
the roster to the balance page. That is one decision and it is worth stating
plainly: minutes are exact, they add up without surprises, and 7 hours 20 is not
representable as a float without a fraction that eventually prints as 7.333333.
A ``Decimal`` of hours would also be exact, but every arithmetic site would then
have to remember to quantise, and the one that forgets is the one that shows a
week's total as 37.499999999.

The contracted hours on ``Employee`` are the single exception — they are a
``Decimal`` of hours, because that is how a contract is written ("20 Stunden")
and how somebody types it. ``contracted_minutes`` below is the one door between
the two worlds, and nothing else should be doing that conversion inline.

**One notation, everywhere: ``hh:mm``.** There used to be a per-person choice
between ``7,5 h`` and ``7:30 h``, and it was removed rather than kept dormant.
The timesheet is a grid of ten columns read *down*, and a column only lines up
when every figure in it is the same width — so the month ignored the preference,
and a Stop message saying "10,20 recorded" beside a timesheet saying 10:12 is one
number written two ways within a second of each other. Once every page wrote
``hh:mm`` the setting changed nothing anywhere, and a control that does nothing
is one people press, see no effect from, and report as broken.
"""

from decimal import Decimal




def clock(minutes):
    """``455`` → ``"7:35"``. Negative durations keep the sign outside the colon.

    A negative total is a real answer here, not a bug to clamp: the balance
    column on a timesheet is worked minus contracted, and somebody who left
    early is legitimately at ``-1:15``. Formatting that as ``-1:-15`` — which is
    what a naive ``divmod`` gives — is how a small shortfall becomes an
    unreadable one.
    """
    minutes = int(minutes)
    sign = "-" if minutes < 0 else ""
    hours, rest = divmod(abs(minutes), 60)
    return f"{sign}{hours}:{rest:02d}"


def hhmm(minutes):
    """``455`` → ``"07:35"``; ``-45`` → ``"-00:45"``; ``0`` → ``"00:00"``.

    **The app's only way of writing a duration.** It began as the timesheet's,
    against a per-person decimal/clock preference everywhere else; the month is a
    grid of ten columns read down rather than across, and a column only lines up
    if every figure in it is the same width. Two digits of hours does that and
    7,5 beside 12,25 does not — and once the messages beside the grid disagreed
    with it, keeping two notations was keeping a bug.

    Padded, which ``duration_clock`` is not, and signed, which ``clock`` is not
    — the two existing formatters are each wrong for this in one direction. It
    does *not* wrap at 24: this is a length, so twenty-five hours is ``25:00``
    and not ``01:00``.
    """
    minutes = int(minutes)
    sign = "-" if minutes < 0 else ""
    hours, rest = divmod(abs(minutes), 60)
    return f"{sign}{hours:02d}:{rest:02d}"


def contracted_minutes(hours):
    """A contract's ``Decimal`` hours as whole minutes.

    Rounded rather than truncated, and to the nearest minute rather than kept
    exact, because the rest of the app compares this against measured times.
    A contract of 7.75 hours is 465 minutes; one of 7.333 is 440, and the third
    of a minute it drops is not a quantity anybody rosters in.
    """
    return int((Decimal(hours) * 60).quantize(Decimal("1")))
