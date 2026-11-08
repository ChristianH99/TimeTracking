"""Handing the records over: the figures, the file, and who may ask for one.

**The figures are what these tests are for.** A printed timesheet that disagrees
with the screen it was printed from is worse than no export at all — it is the
document somebody takes to a lawyer, and the two would be produced weeks apart by
people who never see them side by side. So ``rows_for`` is held to exactly what
``build_month`` puts on the page, and the rendering is tested for being a file
rather than for its layout.

The PDF is deliberately checked lightly. Asserting on reportlab's byte stream
would be testing reportlab, and asserting on a rendered image would be a golden
file that fails on a font update — neither of which is the thing that could go
wrong here. What could go wrong is the arithmetic, and the arithmetic is in
``rows_for`` where a test can reach it.
"""

import datetime as dt

import pytest
from django.urls import reverse

from apps.absences.models import Absence, AbsenceKind, RequestStatus
from apps.timesheets import export
from apps.timesheets.models import DayLock, DayRecord, WorkSegment
from apps.timesheets.views import build_month


def _record(employee, date, spans, **kwargs):
    record = DayRecord.objects.create(employee=employee, date=date, **kwargs)
    for index, (start, end) in enumerate(spans):
        WorkSegment.objects.create(
            day=record, position=index,
            start=dt.time(*start), end=dt.time(*end) if end else None,
        )
    record.refresh_from_db()
    record.apply_break_rules()
    record.save()
    return record


@pytest.fixture
def september(anna, org):
    """A month with a day worked, a day off and a day corrected by hand."""
    _record(anna, dt.date(2025, 9, 1), [((8, 0), (16, 30))])
    _record(
        anna, dt.date(2025, 9, 2), [((8, 0), (14, 0))],
        correction_minutes=30, correction_reason="drove to the second site",
    )
    Absence.objects.create(
        employee=anna, kind=AbsenceKind.HOLIDAY,
        start_date=dt.date(2025, 9, 3), end_date=dt.date(2025, 9, 3),
        status=RequestStatus.APPROVED,
    )
    return dt.date(2025, 9, 1), dt.date(2025, 9, 30)


# --------------------------------------------------------------------------
# The figures
# --------------------------------------------------------------------------

class TestTheRowsAreTheScreen:

    def test_a_row_exists_for_every_date_in_the_range(self, anna, september):
        first, last = september
        rows = export.rows_for(anna, first, last)
        assert len(rows) == 30

    def test_the_actual_column_is_what_the_month_says(self, anna, september):
        """The assertion the whole feature rests on. Read from ``build_month``
        rather than written out, so this cannot pass by both being wrong in the
        same way — and cannot drift when a credited-hours branch changes."""
        first, last = september
        rows = export.rows_for(anna, first, last)
        month = build_month(anna, first)

        from apps.timesheets.hours import hhmm

        for row, built in zip(rows, month["rows"]):
            expected = (
                hhmm(built["counted_minutes"])
                if (built["worked_minutes"] is not None or built["credited_minutes"])
                else ""
            )
            assert row["counted"] == expected

    def test_the_running_column_carries_into_a_partial_range(self, anna, september):
        """A range starting mid-month still shows the balance carried *into* its
        first row.

        The month is built whole and clipped afterwards, precisely so that this
        is true. Building only from the 15th would restart the running total at
        nought and print a balance nobody has.
        """
        _first, last = september
        whole = export.rows_for(anna, dt.date(2025, 9, 1), last)
        partial = export.rows_for(anna, dt.date(2025, 9, 15), last)
        assert partial[0]["running"] == whole[14]["running"]

    def test_a_range_across_two_months_is_continuous(self, anna, org, september):
        rows = export.rows_for(anna, dt.date(2025, 9, 25), dt.date(2025, 10, 5))
        assert rows[0]["date"] == "25.09.2025"
        assert rows[-1]["date"] == "05.10.2025"
        assert len(rows) == 11

    def test_the_bookings_are_pairs_and_not_a_punch_list(self, anna, september):
        first, last = september
        rows = export.rows_for(anna, first, last)
        assert rows[0]["bookings"] == "08:00-16:30"

    def test_a_running_shift_keeps_its_end_open(self, anna, org):
        _record(anna, dt.date(2025, 9, 1), [((8, 0), None)])
        rows = export.rows_for(anna, dt.date(2025, 9, 1), dt.date(2025, 9, 1))
        assert rows[0]["bookings"] == "08:00-"

    def test_a_correction_carries_its_reason(self, anna, september):
        first, last = september
        rows = export.rows_for(anna, first, last)
        assert rows[1]["correction"] == "00:30"
        assert rows[1]["correction_reason"] == "drove to the second site"

    def test_a_typed_break_is_told_apart_from_a_computed_one(self, anna, org):
        """The distinction the screen carries in amber, kept in a column.

        A break of 30 the rules produced and a break of 30 somebody typed are the
        same number and mean entirely different things to whoever signs the sheet
        off — and a printout that lost that would lose the one thing the colour
        was saying.
        """
        record = _record(anna, dt.date(2025, 9, 1), [((8, 0), (16, 30))])
        record.break_minutes = 45
        record.break_is_override = True
        record.save()

        rows = export.rows_for(anna, dt.date(2025, 9, 1), dt.date(2025, 9, 1))
        assert rows[0]["break"] == "00:45"
        assert str(rows[0]["break_source"]) == "by hand"

    def test_an_absence_says_which_and_whether_it_was_decided(self, anna, september):
        """An approved day and one still waiting are worth different numbers of
        hours, so a status column that did not say which would make the
        arithmetic beside it unexplainable."""
        first, last = september
        rows = export.rows_for(anna, first, last)
        assert "Approved" in rows[2]["status"]

    def test_a_locked_day_says_so(self, anna, september):
        DayLock.lock(anna, [dt.date(2025, 9, 1)], by=None)
        first, last = september
        rows = export.rows_for(anna, first, last)
        assert rows[0]["locked"]

    def test_when_it_was_recorded_is_in_the_file(self, anna, september):
        """§17 MiLoG's seven days and the ArbZG draft's *am Tag der
        Arbeitsleistung* cannot be shown to have been met without this."""
        first, last = september
        rows = export.rows_for(anna, first, last)
        assert rows[0]["recorded_at"]
        assert rows[0]["days_to_record"] != ""

    def test_the_totals_add_up_the_columns(self, anna, september):
        first, last = september
        rows = export.rows_for(anna, first, last)
        totals = export.totals_for(rows)
        assert totals["difference"] == totals["counted"] - totals["contracted"]


# --------------------------------------------------------------------------
# The files
# --------------------------------------------------------------------------

class TestTheSpreadsheet:

    def test_it_carries_a_header_saying_whose_and_when(self, anna, september):
        """A file with no header is one nobody can identify once it has been
        renamed and mailed on — and "whose hours are these" is exactly what an
        auditor writes on a printout by hand."""
        first, last = september
        text = export.to_csv(anna, first, last)
        assert anna.full_name in text
        assert "01.09.2025" in text and "30.09.2025" in text

    def test_every_column_is_written_under_its_own_heading(self, anna, september):
        """One list drives the header and the body, so column nine cannot come
        out under column eight's name — which is a bug that looks like the data
        being wrong."""
        import csv
        import io as _io

        first, last = september
        text = export.to_csv(anna, first, last)
        table = list(csv.reader(_io.StringIO(text), delimiter=export.DELIMITER))
        header = next(row for row in table if row and row[0] == "Date")
        assert len(header) == len(export.COLUMNS)
        body = table[table.index(header) + 1]
        assert len(body) == len(export.COLUMNS)

    def test_it_is_semicolon_delimited(self, anna, september):
        first, last = september
        assert export.DELIMITER == ";"
        assert ";" in export.to_csv(anna, first, last)

    def test_the_decimal_column_uses_a_comma(self, anna, september):
        """German notation, because the file is opened by a German spreadsheet
        and `7.50` in a `;`-delimited file on a German locale is read as text —
        which defeats the point of offering a decimal at all."""
        first, last = september
        rows = export.rows_for(anna, first, last)
        assert rows[0]["counted_decimal"] == "8,00"

    def test_the_response_carries_the_mark_a_spreadsheet_needs(self, anna, september, client):
        response = client.get(reverse("timesheets:export", args=["csv"]),
                              {"month": "2025-09"})
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert response.content.startswith(export.BOM.encode("utf-8"))
        assert "attachment" in response["Content-Disposition"]


class TestThePrintableSheet:

    def test_it_is_a_pdf(self, anna, september):
        first, last = september
        body = export.to_pdf(anna, first, last)
        assert body.startswith(b"%PDF")
        # A month of rows is not a blank page. The figure is deliberately loose:
        # what is being caught is an empty document, not a layout change.
        assert len(body) > 3000

    def test_the_route_answers_with_one(self, anna, september, client):
        response = client.get(reverse("timesheets:export", args=["pdf"]),
                              {"month": "2025-09"})
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")

    def test_a_year_paginates_rather_than_falling_over(self, anna, org, september):
        """``platypus`` rather than a canvas, so the table breaks its own pages
        and repeats its header. The canvas version is a page-break calculation
        written by hand and wrong on exactly the ranges nobody tests."""
        body = export.to_pdf(anna, dt.date(2025, 1, 1), dt.date(2025, 12, 31))
        assert body.startswith(b"%PDF")


# --------------------------------------------------------------------------
# Who may ask for one
# --------------------------------------------------------------------------

class TestWhoMayAsk:

    def test_an_employee_cannot_export_somebody_elses(self, anna, org, client):
        other = anna.__class__.objects.create(first_name="Other", username="other.person")
        for kind in ("csv", "pdf"):
            url = reverse("timesheets:employee-export", args=[other.pk, kind])
            assert client.get(url).status_code == 404

    def test_a_manager_can(self, anna, org, manager, manager_client):
        url = reverse("timesheets:employee-export", args=[anna.pk, "csv"])
        assert manager_client.get(url).status_code == 200

    def test_the_export_page_is_manager_only(self, anna, org, client, manager_client):
        assert client.get(reverse("timesheets:export-page")).status_code == 404
        assert manager_client.get(reverse("timesheets:export-page")).status_code == 200

    def test_everybody_in_one_file_names_each_person(self, anna, org, manager, manager_client, september):
        response = manager_client.get(reverse("timesheets:export-everybody"),
                                      {"from": "2025-09-01", "to": "2025-09-30"})
        assert response.status_code == 200
        text = response.content.decode("utf-8")
        assert anna.full_name in text
        assert manager.full_name in text

    def test_a_printable_sheet_for_everybody_is_refused_with_a_sentence(
        self, anna, org, manager, manager_client,
    ):
        """Refused with a message and the form still filled in, rather than by a
        disabled button. A control that refuses without saying why is worse than
        one that explains."""
        response = manager_client.get(reverse("timesheets:export-run"), {
            "employee": "", "format": "pdf",
            "from": "2025-09-01", "to": "2025-09-30",
        }, follow=True)
        assert response.status_code == 200
        assert any("one person at a time" in str(m) for m in response.context["messages"])

    def test_the_form_sends_both_buttons_to_one_route(self, anna, org, manager, manager_client):
        """No script on the page, so it works before anything has loaded — which
        matters most on the page somebody opens with an inspector at the desk."""
        page = manager_client.get(reverse("timesheets:export-page"))
        body = page.content.decode("utf-8")
        assert reverse("timesheets:export-run") in body
        assert 'name="format" value="csv"' in body
        assert 'name="format" value="pdf"' in body


def test_a_bad_range_is_read_the_right_way_round(anna, org, client):
    """Dates the wrong way round are swapped rather than refused. A range with no
    days in it produces an empty file, which reads as the person having worked
    nothing — and that is the one wrong answer this must not give."""
    response = client.get(reverse("timesheets:export", args=["csv"]),
                          {"from": "2025-09-30", "to": "2025-09-01"})
    assert response.status_code == 200
    assert "01.09.2025" in response.content.decode("utf-8")
