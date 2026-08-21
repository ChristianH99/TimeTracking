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

Two ways of writing the same number, chosen per person in ``accounts.Preferences``:

* **decimal** — ``7,5 h``. What a payroll export and a contract speak.
* **clock** — ``7:30 h``. What somebody who read a clock wrote on paper.

Neither is a rounding of the other and both come from the same integer, so the
figures reconcile whichever a reader has chosen.
"""

from decimal import Decimal

from django.utils.formats import number_format

from apps.accounts.models import HoursFormat


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


def decimal_hours(minutes):
    """``455`` → ``Decimal("7.58")``. Two places, which is what payroll wants."""
    return (Decimal(int(minutes)) / 60).quantize(Decimal("0.01"))


def format_minutes(minutes, style=HoursFormat.DECIMAL):
    """One duration, written the way this reader asked for.

    The decimal form goes through Django's ``number_format`` so that a German
    page says ``7,58`` and an English one ``7.58``. The clock form does not and
    must not: a colon is not a decimal separator and localising it would produce
    ``7,35`` for seven hours thirty-five, which reads as seven and a bit.
    """
    if style == HoursFormat.CLOCK:
        return clock(minutes)
    return number_format(decimal_hours(minutes), decimal_pos=2)


def contracted_minutes(hours):
    """A contract's ``Decimal`` hours as whole minutes.

    Rounded rather than truncated, and to the nearest minute rather than kept
    exact, because the rest of the app compares this against measured times.
    A contract of 7.75 hours is 465 minutes; one of 7.333 is 440, and the third
    of a minute it drops is not a quantity anybody rosters in.
    """
    return int((Decimal(hours) * 60).quantize(Decimal("1")))


def style_for(user):
    """Which format this account reads in. Falls back to the default for an
    anonymous or preference-less user rather than querying for a row that is
    usually not there — see ``Preferences.for_user``."""
    from apps.accounts.models import Preferences

    return Preferences.for_user(user).hours_format
