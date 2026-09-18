/* The month picker: a year above a grid of twelve months.
 *
 * The markup in templates/_month_picker.html is complete without this file —
 * every cell is a link, the panel is a <details>, and the year arrows point at
 * the same month in the adjacent year. That is deliberate: the whole control
 * works with no script at all, and what follows is enhancement rather than
 * implementation.
 *
 * Two things are added here:
 *
 *   - The year arrows stop navigating and redraw the grid in place. Without
 *     this, looking for March 2024 from September 2026 costs two page loads
 *     and lands on September twice on the way.
 *   - The panel closes when it should — a click outside it, or Escape — which
 *     <details> does not do for itself and which is the one thing that makes a
 *     disclosure feel like a menu rather than like a stuck panel.
 *
 * The month names never change, so nothing in here writes text into a cell: it
 * rewrites the twelve hrefs and moves one class. That is what keeps this file
 * out of the JavaScript catalogue entirely — no gettext, no month names in two
 * languages, no way for the grid to disagree with the page around it.
 */
(function () {
  const picker = document.querySelector("[data-month-picker]");
  if (!picker) return;

  const grid = picker.querySelector("[data-month-grid]");
  const yearLabel = picker.querySelector("[data-year-label]");
  const cells = Array.from(picker.querySelectorAll("[data-month-cell]"));
  /* The month the page is actually showing, as "2026-09". It never changes —
     choosing a month is a navigation — so the highlight always means "this is
     the month you are looking at" and never "this is the one you last hovered
     over in a year you are only browsing". */
  const showing = picker.dataset.current || "";

  let year = Number(yearLabel.textContent.trim());

  function draw() {
    yearLabel.textContent = String(year);
    cells.forEach((cell) => {
      const value = year + "-" + cell.dataset.monthCell;
      cell.setAttribute("href", "?month=" + value);
      const current = value === showing;
      cell.classList.toggle("is-current", current);
      cell.setAttribute("aria-current", current ? "true" : "false");
    });
    /* The arrows go on pointing at the same month in the year either side of
       whichever year is drawn, so that they still mean what their labels say
       after the grid has been moved — and so that somebody who lands here with
       script off and somebody who has browsed three years back both get an
       arrow that does the obvious thing. */
    picker.querySelectorAll("[data-year-step]").forEach((arrow) => {
      const step = Number(arrow.dataset.yearStep);
      const month = showing.slice(5) || "01";
      arrow.setAttribute("href", "?month=" + (year + step) + "-" + month);
    });
  }

  grid.addEventListener("click", (event) => {
    /* A month cell is a link and is allowed to be one — nothing is intercepted
       here. Closing the panel first only stops it sitting open over the page
       while the next one loads. */
    if (event.target.closest("[data-month-cell]")) picker.open = false;
  });

  picker.addEventListener("click", (event) => {
    const arrow = event.target.closest("[data-year-step]");
    if (!arrow) return;
    event.preventDefault();
    year += Number(arrow.dataset.yearStep);
    draw();
  });

  /* Opening it again always starts from the year on the page, whatever year was
     last browsed to and abandoned. */
  picker.addEventListener("toggle", () => {
    if (!picker.open) return;
    const onPage = Number(showing.slice(0, 4));
    if (onPage && year !== onPage) {
      year = onPage;
      draw();
    }
  });
})();

/* Closing a disclosure that is being used as a menu.
 *
 * Split out from the picker above and written over *both* of the toolbar's
 * disclosures — the month, and the manager's list of people — because this half
 * has nothing to do with either one's contents. `<details>` opens and closes on
 * its own, which is why the markup needs no script to work at all; what it does
 * not do is close when somebody clicks past it or presses Escape, and a panel
 * that stays open over the page after the attention has moved reads as stuck
 * rather than as open.
 *
 * Two disclosures now sit side by side on the timesheet, which is what made
 * this general: the version scoped to one of them left the other hanging open
 * over the month it had just been used to leave.
 */
(function () {
  const pickers = Array.from(
    document.querySelectorAll("[data-month-picker], [data-person-picker]")
  );
  if (!pickers.length) return;

  /* A click *on* the summary is what closes an open panel the ordinary way, so
     it has to be left alone here — swallowing it would close and reopen the
     panel in one press. Only a click outside the whole disclosure counts. */
  document.addEventListener("click", (event) => {
    pickers.forEach((picker) => {
      if (picker.open && !picker.contains(event.target)) picker.open = false;
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    pickers.forEach((picker) => {
      if (!picker.open) return;
      picker.open = false;
      /* Back to the control that opened it. A panel that closes and leaves the
         focus where the panel used to be is one the keyboard has lost. */
      const summary = picker.querySelector("summary");
      if (summary) summary.focus();
    });
  });
})();
