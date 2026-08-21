/* The day form: the running total, and the break that follows from it.
 *
 * Everything here answers *while somebody types*. That is the whole reason the
 * file exists — the relationship between "when I was here" and "what counts as
 * worked" is the one thing on the page nobody can do in their head, and showing
 * it only after the save is showing it too late to be any use.
 *
 * Reads window.ttHours (static/js/hours.js), which must therefore be loaded
 * first. config/tests.py walks every template to check that it is.
 */
(function () {
  const form = document.querySelector("[data-day-form]");
  if (!form || !window.ttHours) return;

  const hours = window.ttHours;
  const rules = window.pageData ? window.pageData("break-rules") : null;

  const automatic = form.querySelector("[name='automatic_break']");
  const breakInput = form.querySelector("[name='break_minutes']");
  const manualBlock = form.querySelector("[data-break-manual]");
  const grossOut = form.querySelector("[data-summary-gross]");
  const requiredOut = form.querySelector("[data-summary-required]");
  const netOut = form.querySelector("[data-summary-net]");

  /* Total clock-in-to-clock-out across the live rows.
   *
   * A row marked for deletion is skipped — it is still in the DOM (it has to
   * be, or the formset gets a hole in its index range) and counting it would
   * make the total include time somebody has just removed. */
  function grossMinutes() {
    let total = 0;
    form.querySelectorAll("[data-row]").forEach((row) => {
      const deleted = row.querySelector("input[name$='-DELETE']");
      if (deleted && deleted.checked) return;
      const start = row.querySelector("input[name$='-start']");
      const end = row.querySelector("input[name$='-end']");
      if (!start || !end) return;
      const label = row.querySelector("[data-segment-length]");

      /* An empty end box is a stretch still running, not a broken one. It
         contributes nothing to the total — the same answer WorkSegment.minutes
         gives on the server, and for the same reason: a figure that changes
         every time the page is refreshed is not one anybody can sign off. */
      if (!end.value.trim() && start.value.trim()) {
        if (label) label.textContent = gettext("running");
        return;
      }

      const length = hours.span(start.value, end.value);
      if (label) label.textContent = length === null ? "" : hours.clock(length);
      if (length !== null) total += length;
    });
    return total;
  }

  /* Two stretches that cover the same minute.
   *
   * Checked here as well as on the server because "before saving" is the only
   * time it is cheap to fix: 08:30–17:30 beside 17:00–18:30 is a typo somebody
   * spots instantly when the box goes red, and an hour of hunting once it comes
   * back as a form error on a page they have already left.
   *
   * Compared as minutes on a timeline, not as clock strings — a stretch ending
   * before it starts crosses midnight and is one interval, and comparing the
   * raw values would report every night shift as an overlap while letting the
   * real one through. The same rule as _SegmentFormSet.clean in
   * apps/timesheets/forms.py.
   */
  function overlapping() {
    const spans = [];
    form.querySelectorAll("[data-row]").forEach((row) => {
      const deleted = row.querySelector("input[name$='-DELETE']");
      if (deleted && deleted.checked) return;
      const start = row.querySelector("input[name$='-start']");
      const end = row.querySelector("input[name$='-end']");
      if (!start || !end) return;
      const from = hours.parse(start.value);
      if (from === null) return;

      /* A running stretch runs to the end of time. Anything starting after it
         does overlap it, and will still overlap it once Stop is pressed — so
         saying so now is saying it while it can still be fixed in one keystroke.
         Infinity rather than a large number, because a night shift legitimately
         reaches past midnight and any finite sentinel is a value some real
         stretch can exceed. */
      if (!end.value.trim()) {
        spans.push({ from: from, to: Infinity, row: row, running: true });
        return;
      }

      let to = hours.parse(end.value);
      if (to === null) return;
      if (to <= from) to += 24 * 60;
      spans.push({ from: from, to: to, row: row, running: false });
    });

    spans.sort((a, b) => a.from - b.from);
    const clashing = new Set();
    const running = spans.filter((span) => span.running);
    for (let i = 1; i < spans.length; i += 1) {
      if (spans[i].from < spans[i - 1].to) {
        clashing.add(spans[i - 1].row);
        clashing.add(spans[i].row);
      }
    }

    /* Two open stretches is a state with no reading: Stop would have to guess
       which of them it ended. Flagged as a clash rather than as its own message,
       because the shape of the fix is the same one — give one of them an end. */
    if (running.length > 1) {
      running.forEach((span) => clashing.add(span.row));
    }

    form.querySelectorAll("[data-row]").forEach((row) => {
      row.classList.toggle("is-overlapping", clashing.has(row));
    });

    // On the end box of every clashing row, so the browser refuses the
    // submission and points at one of them rather than letting the server be
    // the first to notice.
    form.querySelectorAll("[data-row] input[name$='-end']").forEach((input) => {
      const row = input.closest("[data-row]");
      // Never clobber a complaint the time parser already made — that one is
      // about this very box and is more specific than this one.
      if (input.classList.contains("is-unreadable")) return;
      input.setCustomValidity(
        clashing.has(row)
          ? gettext("This overlaps another stretch on the same day.")
          : ""
      );
    });

    const notice = form.querySelector("[data-overlap-notice]");
    if (notice) notice.hidden = clashing.size === 0;
    return clashing.size > 0;
  }

  function refresh() {
    const gross = grossMinutes();
    const required = hours.requiredBreak(gross, rules);
    overlapping();

    // The box follows the rules only while the checkbox says it should. Writing
    // into it regardless is how somebody who deliberately typed 60 finds 30
    // there a keystroke later, with nothing on the page showing that it moved.
    if (automatic && automatic.checked && breakInput) {
      breakInput.value = String(required);
    }

    const taken = breakInput ? parseInt(breakInput.value, 10) || 0 : required;
    const net = Math.max(0, gross - taken);

    if (grossOut) grossOut.textContent = gross ? hours.clock(gross) : "—";
    if (requiredOut) requiredOut.textContent = gross ? required + " min" : "—";
    if (netOut) netOut.textContent = gross ? hours.clock(net) : "—";

    if (manualBlock && automatic) {
      // Not `hidden`: a hidden container makes its input unfocusable, and a
      // validation error inside one makes Save do nothing at all with an
      // unfocusable-control warning in the console as the only clue. Dimmed and
      // read-only instead, so the number the rules produced stays visible —
      // which is also the answer to "what would it be if I let it?".
      manualBlock.classList.toggle("is-automatic", automatic.checked);
      breakInput.readOnly = automatic.checked;
    }
  }

  // Delegated from the form rather than bound per row, so a row added a moment
  // ago answers exactly like one the server rendered.
  form.addEventListener("input", refresh);
  form.addEventListener("change", refresh);

  refresh();
})();
