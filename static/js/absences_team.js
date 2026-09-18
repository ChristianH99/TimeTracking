/* The people filter on the absence calendar.
 *
 * A tick box per person, hiding and showing that person's row. Nothing here
 * posts, saves or remembers anything: the page always arrives with everybody
 * showing, and the ticks are how a manager says which two people they are
 * looking at for the next half minute. A filter that persisted would be a
 * setting, and a setting that hid a colleague's holiday from the coverage grid
 * without saying so is the one failure this page cannot afford.
 *
 * With no script the boxes do nothing and the whole grid is on show, which is
 * the right way round: showing who is off is the page's job, and choosing whom
 * to look at is an aid to it.
 *
 * **This file writes no text.** The one thing it would have had to say — "3 of
 * 11 showing" — is not said at all, because the ticks themselves already say
 * it and a sentence repeating them would be a string in the JavaScript
 * catalogue earning nothing. Same rule as monthpicker.js.
 */
(function () {
  const filter = document.querySelector("[data-people-filter]");
  const table = document.querySelector("[data-coverage]");
  if (!filter || !table) return;

  const everybody = filter.querySelector("[data-filter-all]");
  const ticks = Array.from(filter.querySelectorAll("[data-filter-person]"));

  const counts = Array.from(table.querySelectorAll("[data-count]"));

  function rowFor(tick) {
    return table.querySelector(
      '[data-person-row="' + tick.dataset.filterPerson + '"]'
    );
  }

  /* The footer follows the filter.
   *
   * The server renders the whole team's figure, which is the right answer for
   * the page as it arrives. The moment somebody unticks two colleagues the
   * question changes — "how thin is Thursday *among these people*" — and a
   * footer still counting the hidden rows would be a total sitting under a grid
   * that disagrees with it, which is worse than no total at all.
   *
   * A zero is drawn as nothing, the same as the server draws it: a strip of
   * noughts across thirty-one columns is thirty-one figures saying nothing, and
   * it would bury the three that matter. Writing a number is not writing text,
   * so this stays out of the JavaScript catalogue. */
  function recount() {
    const showing = Array.from(table.querySelectorAll("[data-person-row]"))
      .filter((row) => !row.hidden)
      .map((row) => Array.from(row.querySelectorAll(".coverage-cell")));

    counts.forEach((cell, index) => {
      const away = showing.filter(
        (cells) => cells[index] && cells[index].classList.contains("is-away")
      ).length;
      cell.textContent = away ? String(away) : "";
      cell.classList.toggle("has-some", away > 0);
    });
  }

  /* The row is hidden with the `hidden` property rather than a class, and that
     is not arbitrary: a table row taken out with `display: none` and one taken
     out with `hidden` look the same, but `hidden` is the one that also takes it
     out of the accessibility tree — a screen reader announcing eleven rows on a
     grid showing two is a grid that disagrees with itself.

     Nothing in this row is focusable, so the trap that keeps the roster's cards
     on screen rather than hidden does not apply here. */
  function draw() {
    ticks.forEach((tick) => {
      const row = rowFor(tick);
      if (row) row.hidden = !tick.checked;
    });
    /* The "everybody" box reports rather than commands, whenever it is not the
       box that was pressed. Its third state — some on, some off — is what
       `indeterminate` is for; without it the box sits either ticked or clear
       and both are a lie about a half-filtered grid. */
    const on = ticks.filter((tick) => tick.checked).length;
    everybody.checked = on === ticks.length;
    everybody.indeterminate = on > 0 && on < ticks.length;
    recount();
  }

  everybody.addEventListener("change", () => {
    ticks.forEach((tick) => {
      tick.checked = everybody.checked;
    });
    draw();
  });

  ticks.forEach((tick) => tick.addEventListener("change", draw));

  draw();
})();
