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

  /* Outside the panel, and outside the summary that opens it — a click on the
     summary is what closes it the ordinary way, and swallowing that here would
     make the toggle close and reopen in one press. */
  document.addEventListener("click", (event) => {
    if (!picker.open) return;
    if (!picker.contains(event.target)) picker.open = false;
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || !picker.open) return;
    picker.open = false;
    /* Back to the control that opened it. A panel that closes and leaves the
       focus where the panel used to be is one the keyboard has lost. */
    const summary = picker.querySelector("summary");
    if (summary) summary.focus();
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
