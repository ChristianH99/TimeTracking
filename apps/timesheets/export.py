"""Handing the records over: a spreadsheet, and something to print.

**This reverses the "no in-app export" standing decision, and the reversal is
not a preference.** That decision said the database is one SQLite file Hyper
Backup already covers and a payroll format is a question nobody has asked. Both
halves are still true. What changed is that five separate duties turn out to be
the same feature, and four of them are not about payroll at all:

* **GoBD Datenzugriff Z3** — a tax auditor may demand the data on a medium in an
  evaluable format, and Z3 is the form they most often choose. A screen is not
  one.
* **§9 BVV** — the *Entgeltunterlagen* a DRV auditor reconciles the payroll
  against must be *maschinell auswertbar*. A stack of screenshots is not.
* **§17 MiLoG** — the FKS turns up unannounced and asks for the records of four
  named people for last year, on the premises, in German. Reading them a month
  at a time off a laptop is not a good afternoon.
* **DSGVO Art. 15(3)** — a copy of the data, on request.
* **The June 2026 ArbZG draft** — employees may request information about their
  recorded hours *and obtain copies*. A right to a copy is not a feature request.

``docs/AUDIT.md`` argues it at length.

----

**Two formats, because they answer two different questions and neither
substitutes.** The CSV is for a machine: an auditor sorts and filters it, and a
PDF cannot be sorted. The PDF is for a person: it is the employee's copy and the
sheet handed across a desk, and a CSV is not something anybody signs.

**Split in two here as well.** ``rows_for`` is the data and is what the tests
hold to the figures; ``to_csv`` and ``to_pdf`` are rendering. The alternative —
one function per format, each walking the month itself — is two implementations
of the same arithmetic, which is the bug this codebase spends most of its
docstrings avoiding.

**Every figure comes from ``build_month``**, not from a second pass over the
records. A printed timesheet that disagreed with the screen it was printed from
would be worse than no export at all: it is the document somebody takes to a
lawyer.

**Durations are written ``hh:mm``, the same as everywhere else** — including in
the CSV, where a decimal would be friendlier to a spreadsheet. It is the wrong
trade: a figure that reads 7:30 on the screen and 7.5 in the file is one number
written two ways in two places somebody compares side by side, and reconciling
them is exactly what the auditor is doing. The decimal is offered as its own
extra column instead, so nobody has to choose.
"""

import csv
import datetime as dt
import io
from decimal import Decimal

from django.utils import timezone
# **Lazy, and it has to be.** ``COLUMNS`` below is built at import time, and
# ``gettext`` would freeze whichever language happened to be active when the
# module was first imported — which on a server is the language of the first
# request after a restart, so the whole house would get somebody else's headers
# until it was restarted again. The bug is invisible in a test suite that pins
# one language.
from django.utils.translation import gettext_lazy as _

from django.utils.formats import date_format

from apps.timesheets.hours import hhmm


def _weekday(date):
    """The short weekday name **in the reader's language**.

    ``strftime("%a")`` would be the obvious call and it is wrong: it reads the C
    locale, not Django's, so a sheet whose every heading is German came out with
    "Tue" and "Wed" down the day column. Invisible in a test that pins one
    language, and the first thing a German reader notices on a printed document.
    """
    return date_format(date, "D")


# **Semicolon, and a byte order mark.** Both are concessions to the program the
# file is actually opened in, which in a German office is Excel: it splits on
# the list separator of the system locale (`;` on a German Windows) and it reads
# a file without a BOM as the legacy code page, which turns every umlaut in
# every name into mojibake. A comma and no BOM is the more standard CSV and is
# the one that arrives looking broken.
DELIMITER = ";"
BOM = "﻿"


def _bookings_text(row):
    """A day's punches as ``08:00-12:00, 13:00-17:00``.

    Pairs rather than the punch list, because a spreadsheet column is read
    across and "coming 08:00, going 12:00" is twice the width for the same
    fact. A stretch still running is written with its end left open, which is
    what it is.
    """
    parts = []
    pending = None
    for booking in row["bookings"]:
        if booking["kind"] == "in":
            pending = booking["time"].strftime("%H:%M")
        elif pending is not None:
            parts.append(f"{pending}-{booking['time']:%H:%M}")
            pending = None
    if pending is not None:
        parts.append(f"{pending}-")
    return ", ".join(parts)


def _status_text(row):
    """What the status cell says, in words rather than in colour."""
    absence = row["absence"]
    if row["holiday"]:
        return str(row["holiday"])
    if absence is None:
        return ""
    if absence.kind == "special" and absence.special_type_id:
        name = absence.special_type.name
    else:
        name = str(absence.get_kind_display())
    if absence.is_half_day:
        name = f"{name} ({_('half day')})"
    # The status alone is half the fact: an approved day and one still waiting
    # are worth different numbers of hours, and a column that did not say which
    # would make the arithmetic below unexplainable.
    return f"{name} – {absence.get_status_display()}"


def _decimal_hours(minutes):
    """Minutes as decimal hours, to two places, with a comma.

    The second of the two duration columns. German decimal notation, because the
    file is opened by a German spreadsheet and 7.50 in a `;`-delimited file on a
    German locale is read as text, not as a number — which defeats the whole
    point of offering a decimal at all.
    """
    if minutes is None:
        return ""
    return f"{Decimal(minutes) / 60:.2f}".replace(".", ",")


# The columns, in the order they are written, as ``(key, header)``. One list, so
# the header row and the body cannot disagree about what is in column nine —
# which is a bug that looks like the data being wrong.
COLUMNS = [
    ("date", _("Date")),
    ("weekday", _("Day")),
    ("status", _("Status")),
    ("bookings", _("Bookings")),
    ("gross", _("Time here")),
    ("break", _("Break")),
    ("break_source", _("Break from")),
    ("correction", _("Correction")),
    ("correction_reason", _("Why corrected")),
    ("worked", _("Worked")),
    ("credited", _("Credited")),
    ("counted", _("Actual")),
    ("counted_decimal", _("Actual (hours)")),
    ("contracted", _("Supposed")),
    ("saldo", _("Saldo")),
    ("running", _("Running")),
    ("limits", _("Working time note")),
    ("recorded_at", _("Recorded on")),
    ("days_to_record", _("Days to record")),
    ("confirmed_at", _("Confirmed on")),
    ("confirmed_by", _("Confirmed by")),
    ("locked", _("Locked")),
    ("note", _("Comment")),
]


def rows_for(employee, first, last):
    """One dictionary per date in the range, keyed by ``COLUMNS``.

    Whole months at a time, because ``build_month`` is where every figure in
    this app comes from and the running balance is only correct when the month
    is built from its own start. A range that begins mid-month is clipped
    *after* building, so the running column still carries the right figure into
    the first row shown.
    """
    # Imported here rather than at the top: the export *views* live in
    # `views.py` and import this module, so a top-level import back would be a
    # cycle. One import inside a function that is called once per file is a
    # cheaper answer than a third module holding two functions.
    from apps.timesheets.views import build_month, month_end, month_start

    rows = []
    month = month_start(first)
    while month <= last:
        built = build_month(employee, month)
        for row in built["rows"]:
            if not (first <= row["date"] <= last):
                continue
            record = row["record"]
            rows.append({
                "date": row["date"].strftime("%d.%m.%Y"),
                "weekday": _weekday(row["date"]),
                "status": _status_text(row),
                "bookings": _bookings_text(row),
                "gross": hhmm(row["gross_minutes"]) if row["gross_minutes"] is not None else "",
                "break": hhmm(row["break_minutes"]) if row["break_minutes"] is not None else "",
                # **Which of the two thirty-minute breaks this is.** A break the
                # rules produced and one somebody typed are the same number and
                # mean entirely different things to whoever signs the sheet off,
                # which is why the screen draws the second in amber — and a
                # printout that lost the distinction would lose the one thing
                # the colour was carrying.
                "break_source": (
                    str(_("by hand")) if row["break_is_override"]
                    else (str(_("rules")) if record else "")
                ),
                "correction": hhmm(row["correction_minutes"]) if row["correction_minutes"] else "",
                "correction_reason": row["correction_reason"],
                "worked": hhmm(row["worked_minutes"]) if row["worked_minutes"] is not None else "",
                "credited": hhmm(row["credited_minutes"]) if row["credited_minutes"] else "",
                "counted": hhmm(row["counted_minutes"]) if (
                    row["worked_minutes"] is not None or row["credited_minutes"]
                ) else "",
                "counted_decimal": _decimal_hours(row["counted_minutes"]) if (
                    row["worked_minutes"] is not None or row["credited_minutes"]
                ) else "",
                "contracted": hhmm(row["contracted_minutes"]),
                "saldo": hhmm(row["saldo"]) if row["saldo"] is not None else "",
                "running": hhmm(row["running_saldo"]) if row["running_saldo"] is not None else "",
                "limits": row["limit_note"],
                "recorded_at": (
                    timezone.localtime(record.hours_entered_at).strftime("%d.%m.%Y %H:%M")
                    if record and record.hours_entered_at else ""
                ),
                "days_to_record": (
                    str(record.days_to_record)
                    if record and record.days_to_record is not None else ""
                ),
                "confirmed_at": (
                    timezone.localtime(record.confirmed_at).strftime("%d.%m.%Y %H:%M")
                    if record and record.confirmed_at else ""
                ),
                "confirmed_by": (
                    (record.confirmed_by.get_full_name() or record.confirmed_by.get_username())
                    if record and record.confirmed_by else ""
                ),
                "locked": str(_("yes")) if row["is_locked"] else "",
                "note": row["note"],
            })
        month = month_start(month_end(month) + dt.timedelta(days=1))
    return rows


def totals_for(rows_source):
    """What the range comes to: worked, credited, contracted, and the difference.

    Summed from the same dictionaries the file is written from rather than asked
    of the month again, so the last line of a printed sheet cannot disagree with
    the column above it — which is the one arithmetic error nobody would spot
    and everybody would act on.
    """
    def minutes(text):
        if not text:
            return 0
        sign = -1 if text.startswith("-") else 1
        hours, _sep, rest = text.lstrip("-").partition(":")
        return sign * (int(hours) * 60 + int(rest or 0))

    worked = sum(minutes(row["worked"]) for row in rows_source)
    credited = sum(minutes(row["credited"]) for row in rows_source)
    contracted = sum(minutes(row["contracted"]) for row in rows_source)
    counted = sum(minutes(row["counted"]) for row in rows_source)
    return {
        "worked": worked,
        "credited": credited,
        "contracted": contracted,
        "counted": counted,
        "difference": counted - contracted,
    }


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------

def to_csv(employee, first, last, rows_source=None):
    """The range as a spreadsheet, returned as text.

    Text rather than bytes, and the caller encodes: the BOM belongs to the file
    and the encoding belongs to the response, and a function that decided both
    would be one nobody could test without decoding its output again.

    ``lineterminator`` is pinned because ``csv`` defaults to ``\\r\\n`` and
    Python then translates it again on Windows, which produces a blank line
    between every row — a file that opens with three hundred rows where there
    should be a hundred and fifty.
    """
    rows_source = rows_source if rows_source is not None else rows_for(employee, first, last)
    out = io.StringIO()
    writer = csv.writer(out, delimiter=DELIMITER, lineterminator="\n",
                        quoting=csv.QUOTE_MINIMAL)

    # Three lines of provenance before the table. A file with no header is one
    # that cannot be identified once it has been renamed and mailed on, and
    # "whose hours are these, for when, and who asked for them" is exactly what
    # an auditor writes on the top of a printout by hand.
    writer.writerow([str(_("Employee")), employee.full_name])
    writer.writerow([str(_("Period")), f"{first:%d.%m.%Y} – {last:%d.%m.%Y}"])
    writer.writerow([str(_("Exported")), timezone.localtime().strftime("%d.%m.%Y %H:%M")])
    writer.writerow([])

    writer.writerow([str(header) for _key, header in COLUMNS])
    for row in rows_source:
        writer.writerow([row[key] for key, _header in COLUMNS])

    totals = totals_for(rows_source)
    writer.writerow([])
    writer.writerow([str(_("Total")), "", "", "", "", "", "", "", "",
                     hhmm(totals["worked"]), hhmm(totals["credited"]),
                     hhmm(totals["counted"]), _decimal_hours(totals["counted"]),
                     hhmm(totals["contracted"]), hhmm(totals["difference"])])
    return out.getvalue()


def csv_filename(employee, first, last):
    """A name that says whose and when, with nothing in it a filesystem dislikes."""
    stem = f"{employee.last_name}_{employee.first_name}".strip("_") or "timesheet"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem)
    return f"{safe}_{first:%Y-%m-%d}_{last:%Y-%m-%d}.csv"


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
#
# **A different document from the CSV, not the same one in another wrapper.**
# The spreadsheet is for a machine and carries twenty-three columns because an
# auditor filters on them. A sheet of A4 does not have twenty-three columns, and
# a table squeezed to fit is one nobody can read — so this prints the ten the
# timesheet itself prints, which are the ten somebody signs off. Anything
# dropped here is in the CSV, and the footer says so.
#
# Landscape, because ten columns of figures on portrait A4 leaves the comment
# column two centimetres wide.

PDF_COLUMNS = [
    ("date", _("Date"), 52),
    ("weekday", _("Day"), 30),
    ("status", _("Status"), 108),
    ("bookings", _("Bookings"), 132),
    ("break", _("Break"), 42),
    ("correction", _("Correction"), 50),
    ("counted", _("Actual"), 44),
    ("contracted", _("Supposed"), 48),
    ("saldo", _("Saldo"), 44),
    ("running", _("Running"), 48),
    ("note", _("Comment"), 92),
]


def to_pdf(employee, first, last, rows_source=None, requested_by=""):
    """The range as a printable sheet. Returns bytes.

    Built with ``platypus`` rather than drawn on a canvas, because a month is
    between twenty-eight and thirty-one rows and a range can be a year: the
    flowable table paginates itself and repeats its header, and the canvas
    version would be a page-break calculation written by hand and wrong on
    exactly the ranges nobody tests.
    """
    from reportlab.lib import colors
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    rows_source = rows_source if rows_source is not None else rows_for(employee, first, last)
    totals = totals_for(rows_source)

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        # **The bottom margin has to clear the two-line footer**, which is drawn
        # on the canvas rather than flowed — so nothing reserves room for it and
        # too small a margin overprints the last row of the table. Paired with
        # the tighter cell padding below, a 31-day month still fits one page,
        # which is what a sheet handed across a desk should be.
        topMargin=12 * mm, bottomMargin=17 * mm,
        title=f"{employee.full_name} {first:%d.%m.%Y} - {last:%d.%m.%Y}",
        author="Time Tracking",
    )

    sheet = getSampleStyleSheet()
    heading = ParagraphStyle(
        "heading", parent=sheet["Title"], fontSize=15, leading=18,
        alignment=0, spaceAfter=2,
    )
    lead = ParagraphStyle("lead", parent=sheet["Normal"], fontSize=9, leading=12,
                          textColor=colors.HexColor("#5A6A6A"))
    cell = ParagraphStyle("cell", parent=sheet["Normal"], fontSize=7.4, leading=9)

    # **Bound to names before the f-strings.** `_("…")` written inside an
    # f-string is never extracted by `makemessages`, so the string ships
    # untranslated and the only symptom is one English phrase on an otherwise
    # German page — see CLAUDE.md.
    title = _("Working time record")
    story = [
        Paragraph(employee.full_name, heading),
        Paragraph(f"{title} · {first:%d.%m.%Y} – {last:%d.%m.%Y}", lead),
        Spacer(1, 6),
    ]

    header = [str(label) for _key, label, _width in PDF_COLUMNS]
    body = [header]
    for row in rows_source:
        body.append([
            Paragraph(str(row[key]), cell) if key in ("status", "bookings", "note")
            # **A nought is left blank on the printed sheet and written out in the
            # spreadsheet**, and the two are right for their own readers. A
            # machine sums a column and wants a number in every cell; a person
            # reads down one, and 00:00 on every Saturday and Sunday is nine
            # figures a month that say only "this is a weekend" — burying the
            # days that are genuinely level, which is the same argument the
            # saldo column makes on screen.
            else _blank_if_zero(row[key])
            for key, _label, _width in PDF_COLUMNS
        ])

    # The totals line, in the columns it belongs under. Written into the table
    # rather than as a paragraph below it so that the figures sit under their own
    # headings — a total in a different place from the column it totals is one
    # somebody reads against the wrong heading.
    body.append([
        str(_("Total")), "", "", "", "", "",
        hhmm(totals["counted"]), hhmm(totals["contracted"]),
        hhmm(totals["difference"]),
        rows_source[-1]["running"] if rows_source else "", "",
    ])

    table = Table(
        body, colWidths=[width for _key, _label, width in PDF_COLUMNS],
        repeatRows=1,
    )
    numeric = [index for index, (key, _label, _width) in enumerate(PDF_COLUMNS)
               if key in ("break", "correction", "counted", "contracted", "saldo",
                          "running")]
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.4),
        ("LEADING", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#123433")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF1F1")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#123433")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D6DEDE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.9),
        # The last row is the total and is the one figure anybody looks for.
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#123433")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F7F9F9")),
    ]
    for column in numeric:
        style.append(("ALIGN", (column, 0), (column, -1), "RIGHT"))
    # Weekends shaded, the same pair of rows the screen shades and for the same
    # reason: on a sheet of thirty-one lines read downwards they are what the eye
    # uses to find its place.
    for index, row in enumerate(rows_source, start=1):
        if row["weekday"] in _weekend_names():
            style.append(("BACKGROUND", (0, index), (-1, index),
                          colors.HexColor("#EFF3F3")))
    table.setStyle(TableStyle(style))
    story.append(table)

    # **The note and the provenance are a page footer, not the end of the story.**
    # As flowables they sat after the table, and a month that fills its page
    # pushed them onto a second one containing nothing else — a document that
    # ends on an almost blank page reads as having gone wrong. On every page is
    # also where they belong: a sheet handed over one page at a time should carry
    # the statute it was computed under and the name of whoever produced it, and
    # a page number saying whether it is all of it.
    note = str(_(
        "Every duration is hh:mm. “Actual” includes hours credited for an "
        "approved absence, which are paid as though worked (§3 EFZG, §11 BUrlG); "
        "time off in lieu credits nothing, and that shortfall is the overtime "
        "being taken back. Breaks are deducted under §4 ArbZG."
    ))
    exported, by_word = _("Exported"), _("by")
    counter = _("Page %(page)s of %(total)s")
    provenance = (
        f"{exported}: {timezone.localtime():%d.%m.%Y %H:%M}"
        + (f" · {by_word} {requested_by}" if requested_by else "")
    )

    # **"Page 1 of 2" needs the total, and the total is not known until the
    # document has been laid out.** So the pages are held back and stamped on the
    # way out — the standard reportlab two-pass shape, and worth the fifteen
    # lines: a sheet handed across a desk one page at a time is one where "is
    # this all of it" is a real question, and a bare "Page 1" does not answer it.
    class _Stamped(pdfcanvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._pages = []

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self._stamp(total)
                super().showPage()
            super().save()

        def _stamp(self, total):
            self.saveState()
            self.setFont("Helvetica", 6.6)
            self.setFillColor(colors.HexColor("#5A6A6A"))
            width, _height = landscape(A4)
            # **Wrapped rather than trusted to fit.** `drawString` does not wrap
            # and does not complain: the German note ran off the right edge and
            # simply stopped mid-word, which on a document handed to an inspector
            # is a sentence about the law that ends in the middle. `simpleSplit`
            # measures against the real font, so it stays right when the note is
            # translated into something longer.
            lines = simpleSplit(note, "Helvetica", 6.6, width - 24 * mm)
            for index, line in enumerate(reversed(lines)):
                self.drawString(12 * mm, (9.5 + index * 3.2) * mm, line)
            self.drawRightString(
                width - 12 * mm, 5 * mm,
                f"{provenance} · {counter % {'page': self._pageNumber, 'total': total}}",
            )
            self.restoreState()

    document.build(story, canvasmaker=_Stamped)
    return buffer.getvalue()


def _blank_if_zero(value):
    text = str(value)
    return "" if text in ("00:00", "0:00", "+00:00", "-00:00") else text


def _weekend_names():
    """Saturday and Sunday as ``%a`` renders them in the active language.

    Derived from two real dates rather than written out, because the rows carry
    ``%a`` and a hard-coded {"Sa", "So"} would shade nothing at all the moment
    somebody read the sheet in English — and shading that silently stops is worse
    than none, since the reader trusts it.
    """
    saturday = dt.date(2026, 1, 3)
    return {_weekday(saturday), _weekday(saturday + dt.timedelta(days=1))}


def pdf_filename(employee, first, last):
    return csv_filename(employee, first, last).replace(".csv", ".pdf")
