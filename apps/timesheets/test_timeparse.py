"""Reading a time however it was typed.

The cases here are the ones somebody actually types, plus the ones that would be
*confidently wrong*. That second group is the point: a parser that refuses a
string is a nuisance, and one that accepts it and means something else writes a
wrong hour into a record that is a legal document.
"""

import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import pytest

from apps.timesheets.timeparse import (
    TimeFormatError, as_time, clock, hours_text, parse_duration, parse_time_of_day,
)


class TestEveryWayHalfPastEightIsWritten:
    """The five forms named in the brief, and the ones beside them.

    All of these are 08:30, and the app has no setting that says which notation
    is in use — asking somebody that is asking them to do the computer's job,
    and the answer is wrong the first time a colleague borrows the terminal.
    """

    @pytest.mark.parametrize("raw", [
        "8:30", "08:30", "8.30", "8,30", "8,5", "8.5", "0830", "830",
        "8:30 h", "8:30h", " 8:30 ",
    ])
    def test_they_all_mean_half_past_eight(self, raw):
        assert parse_time_of_day(raw) == 8 * 60 + 30

    @pytest.mark.parametrize("raw, expected", [
        ("8", 8 * 60), ("08", 8 * 60), ("17", 17 * 60), ("17 Uhr", 17 * 60),
        ("1730", 17 * 60 + 30), ("17:30", 17 * 60 + 30), ("17,5", 17 * 60 + 30),
        ("0", 0), ("00:00", 0), ("000", 0),
        ("2359", 23 * 60 + 59), ("23:59", 23 * 60 + 59),
    ])
    def test_the_rest_of_the_clock(self, raw, expected):
        assert parse_time_of_day(raw) == expected

    @pytest.mark.parametrize("raw", ["24:00", "2400", "24"])
    def test_midnight_at_the_end_of_a_day_is_accepted(self, raw):
        """Refusing it would make somebody write 23:59 and lose a minute a day.

        It comes back as 00:00, which is what the rest of the app already means
        by the end of a day — ``roster.minutes_between`` reads an end at or
        before the start as crossing midnight.
        """
        assert parse_time_of_day(raw) == 0


class TestTheOneRealAmbiguity:
    """Two digits after a separator, which is genuinely undecidable in German.

    ``8,30`` is "acht Komma drei null Stunden" to a payroll clerk and "acht Uhr
    dreißig" to everybody else. The context decides, because the context is the
    thing that actually disambiguates it — and the two readings *converge* for
    the common cases, which is what makes the rule safe rather than merely
    defensible.
    """

    def test_a_time_of_day_prefers_the_clock(self):
        assert parse_time_of_day("8.30") == 8 * 60 + 30
        assert parse_time_of_day("8,30") == 8 * 60 + 30

    def test_a_duration_prefers_decimal_hours(self):
        assert parse_duration("8,30") == 498      # 8.3 h = 8 h 18
        assert parse_duration("8.30") == 498

    def test_one_digit_is_decimal_in_both_and_they_agree(self):
        """Nobody writes ``8.5`` for five past eight, so there is nothing to
        settle — and both readings land on the same answer."""
        assert parse_time_of_day("8.5") == 8 * 60 + 30
        assert parse_duration("8.5") == 8 * 60 + 30

    def test_the_case_where_the_two_readings_really_do_differ(self):
        """``8,50`` is the one that does not converge, and it is worth pinning.

        As a *time of day* it is 08:50 — "8.50 Uhr" is ordinary German and the
        50 is a valid minute. As a *duration* it is eight and a half hours. Both
        are right for their context and there is no third answer that would be
        better; what makes it safe is that the box normalises itself on blur, so
        whichever reading was applied is on the screen before anything is saved.
        """
        assert parse_time_of_day("8,50") == 8 * 60 + 50
        assert parse_duration("8,50") == 8 * 60 + 30

    def test_a_fraction_that_cannot_be_minutes_falls_back_to_decimal(self):
        """``8,75`` has no reading as a clock time, so both contexts give
        8 h 45 — which is exactly what somebody writing three quarters meant."""
        assert parse_time_of_day("8,75") == 8 * 60 + 45
        assert parse_duration("8,75") == 8 * 60 + 45

    def test_the_decimal_conversion_does_not_lose_a_minute(self):
        """8.1 hours is 486 minutes and a float reaches it via
        485.99999999999994 — which truncates to 485 and loses a minute of
        somebody's day, every time, in one direction. Decimal, not float."""
        assert parse_duration("8,1") == 486
        assert parse_duration("0,1") == 6
        assert parse_duration("7,35") == 441


class TestWhatIsRefused:
    """Refused *loudly*. Every one of these has a plausible wrong reading, and
    the wrong reading writes an hour nobody worked into a legal record."""

    @pytest.mark.parametrize("raw", [
        "", "   ", "abc", "8:75", "25:00", "24:01", "12345", "8:", ":30",
        "--", "8-30", "8:3:4:5", "acht", "8,,5", "1.2.3", None,
    ])
    def test_it_raises_rather_than_guessing(self, raw):
        with pytest.raises(TimeFormatError):
            parse_time_of_day(raw)

    def test_the_message_names_what_was_typed(self):
        """"Fix your input" and "fix *this*" are the same sentence on a form
        with one box and completely different ones on a form with seven."""
        with pytest.raises(TimeFormatError) as raised:
            parse_time_of_day("830o")
        assert "830o" in str(raised.value)


class TestWritingItBackOut:
    @pytest.mark.parametrize("minutes, expected", [
        (510, "08:30"), (0, "00:00"), (1439, "23:59"), (1440, "00:00"),
    ])
    def test_the_clock_form(self, minutes, expected):
        assert clock(minutes) == expected

    def test_a_duration_comes_back_as_hours(self):
        """A contract is written in hours, and normalising 7.75 to "07:45"
        would make somebody think they had typed a time of day.

        The separator follows the active language, which is why this asserts
        the English form — ``conftest.english`` pins the suite to English so a
        test does not fail the day somebody improves a translation.
        """
        assert hours_text(465) == "7.75"
        assert hours_text(480) == "8"

    def test_a_german_page_writes_a_comma(self):
        """And it must, because that is the separator the same page will accept
        back: a German box that displayed 7.75 and then refused it would be
        rejecting its own output."""
        from django.utils import translation

        with translation.override("de"):
            assert hours_text(465) == "7,75"
            assert parse_duration(hours_text(465)) == 465

    def test_round_tripping_leaves_the_value_alone(self):
        """Every accepted string, parsed and written back, parses to itself.

        The property that matters for the normalise-on-blur: a box that
        rewrites what somebody typed must not change its meaning while doing it.
        """
        for raw in ["8:30", "8,5", "830", "0830", "17,5", "7,75", "0:45", "8"]:
            once = parse_duration(raw)
            assert parse_duration(hours_text(once)) == once
            assert parse_duration(clock(once)) == once

    def test_as_time_gives_something_a_model_can_store(self):
        assert as_time(510) == dt.time(8, 30)
        assert as_time(1440) == dt.time(0, 0)


class TestTheFieldsBuiltOnIt:
    def test_a_contract_box_reads_hours_and_gives_a_decimal(self):
        from apps.timesheets.fields import ContractHoursField

        field = ContractHoursField()
        assert field.clean("8:30") == Decimal("8.50")
        assert field.clean("8,5") == Decimal("8.50")
        assert field.clean("830") == Decimal("8.50")

    def test_an_empty_contract_box_is_zero_not_missing(self):
        """A weekday with nothing in it is a day the person does not work,
        which is a real answer and the one every leave calculation reads.
        Requiring seven boxes to be filled with 0 would be asking somebody to
        type the default five times."""
        from apps.timesheets.fields import ContractHoursField

        assert ContractHoursField().clean("") == Decimal("0")

    def test_a_contract_box_refuses_more_than_a_day(self):
        from django.core.exceptions import ValidationError

        from apps.timesheets.fields import ContractHoursField

        with pytest.raises(ValidationError):
            ContractHoursField().clean("25")

    def test_a_break_box_reads_bare_digits_as_minutes(self):
        """The one field where bare digits are not hours, because the label says
        minutes and nobody has ever meant forty-five hours by typing 45 into a
        box marked "break"."""
        from apps.timesheets.fields import BreakMinutesField

        field = BreakMinutesField()
        assert field.clean("45") == 45
        assert field.clean("30") == 30
        # Anything with a separator is still a duration, for the person who
        # thinks in those.
        assert field.clean("0:45") == 45
        assert field.clean("0,75") == 45

    def test_a_rejected_time_box_hands_back_exactly_what_was_typed(self):
        """Re-showing a parsed value would blank the box or quietly correct it,
        and the message above it would then be talking about something the box
        no longer contains."""
        from apps.timesheets.fields import TimeOfDayField

        assert TimeOfDayField().prepare_value("830o") == "830o"
        assert TimeOfDayField().prepare_value(dt.time(8, 30)) == "08:30"


def test_the_browser_reads_a_time_the_same_way_python_does():
    """The rule is written twice, in two languages, and held to one answer here.

    ``static/js/hours.js`` repeats ``parse_time_of_day`` so a box can normalise
    itself the moment somebody leaves it — a round trip per keystroke on the one
    form people fill in daily is not a trade worth making. This reads the four
    branches out of the JavaScript and checks they are still the four branches
    Python has, rather than trusting a comment that says they match.
    """
    source = (
        Path(__file__).resolve().parents[2] / "static" / "js" / "hours.js"
    ).read_text(encoding="utf-8")

    # The three notations, and the context switch that settles the ambiguity.
    for fragment in (
        r"const CLOCK = /^(\d{1,2})\s*:\s*(\d{1,2})(?::\d{1,2})?$/;",
        r"const DECIMAL = /^(\d{1,3})\s*[.,]\s*(\d{1,3})$/;",
        r"const DIGITS = /^(\d{1,4})$/;",
        "preferClock && fraction.length === 2 && parseInt(fraction, 10) < 60",
        "Math.round((whole + parseFloat(\"0.\" + fraction)) * 60)",
    ):
        assert fragment in source, (
            f"hours.js no longer contains {fragment!r} — the browser and the "
            "server have drifted apart about how a time is read"
        )

    # And the digit split, which is what makes "8" and "0830" both work.
    assert "digits.length <= 2" in source
    assert "digits.slice(0, -2)" in source and "digits.slice(-2)" in source


def test_no_form_still_uses_a_native_time_or_number_box_for_a_time():
    """``type="time"`` rejects "830" by *emptying itself*, so the page cannot
    even say what was typed — the same trap as ``type="number"``. This walks the
    form modules rather than naming them, so a field added next month is
    covered."""
    forms = sorted(
        (Path(__file__).resolve().parents[2] / "apps").rglob("forms.py")
    )
    assert forms, "no form modules found — this test has stopped checking anything"
    for path in forms:
        source = path.read_text(encoding="utf-8")
        assert 'attrs={"type": "time"}' not in source, (
            f"{path.parent.name}/forms.py renders a native time box; use "
            "apps.timesheets.fields.TimeOfDayField"
        )
        for match in re.finditer(r"NumberInput\(attrs=\{[^}]*\}", source):
            assert "step" not in match.group(0) or "0.25" not in match.group(0), (
                f"{path.parent.name}/forms.py still has an hours spinner; those "
                "are text boxes read by timeparse.py now"
            )
