/* The week planner: seven columns, and cards that move between them.
 *
 * ---- the one rule this file exists to keep ----
 *
 * **A card is a form row, and moving it moves the row.** The cards are rendered
 * once, into a holder off-screen, and this script *moves* each one into the
 * column its hidden `date` names. A drop moves the element into another column
 * and rewrites that one input. There is never a second representation of the
 * week — no array of shifts, no JSON payload — because two representations of
 * one thing is the bug where the picture and the saved roster disagree, and the
 * first edit to disagree looks like a save that did not take.
 *
 *
 * ---- the formset trap, in this shape ----
 *
 * Adding a card means minting a row at the next free index — every `name` and
 * `id` carrying that number — *and* bumping TOTAL_FORMS. Miss the second half
 * and the card is simply not read on POST: the page looks right and the shift
 * vanishes on save.
 *
 * Removing is the DELETE box, ticked, with the card left in the DOM. A form
 * missing from the POST is a hole in the index range, and Django reads the
 * absent fields against that form's own defaults, decides it changed, and
 * validates it — which is how a removed row comes back wearing "This field is
 * required".
 */
(function () {
  const form = document.querySelector("[data-roster]");
  if (!form) return;

  const holder = form.querySelector("[data-roster-holder]");
  const template = form.querySelector("[data-roster-template]");
  const columns = Array.from(form.querySelectorAll("[data-roster-day]"));
  if (!holder || !columns.length) return;

  const days = columns.map((column) => column.dataset.rosterDay);

  // Read out of the blank form rather than written as a literal: the prefix is
  // modelformset_factory's to choose, and a management form found with a "the
  // first TOTAL_FORMS on the page" selector belongs to whichever formset
  // rendered first.
  const sample = template && template.content.querySelector("[name*='__prefix__']");
  const parts = sample && sample.name.match(/^(.+)-__prefix__-/);
  const prefix = parts ? parts[1] : null;
  const totalForms = prefix
    ? form.querySelector("[name='" + prefix + "-TOTAL_FORMS']")
    : null;

  function cardsOf(column) {
    return column.querySelector("[data-roster-cards]");
  }

  function dateInput(card) {
    return card.querySelector("input[name$='-date']");
  }

  /* Send every card home to the column its own date names.
   *
   * Called once on load and after anything that changes a date. Cards whose
   * date is not one of this week's seven stay in the holder rather than being
   * dropped: that is a row the server sent and could not place, and losing it
   * from the document would take its error message with it.
   */
  function render() {
    form.querySelectorAll("[data-roster-card]").forEach((card) => {
      const input = dateInput(card);
      const index = input ? days.indexOf(input.value) : -1;
      if (index === -1) return;
      const target = cardsOf(columns[index]);
      if (target && card.parentElement !== target) target.appendChild(card);
    });
  }

  function moveTo(card, day) {
    const input = dateInput(card);
    if (!input || days.indexOf(day) === -1) return;
    input.value = day;
    const target = cardsOf(columns[days.indexOf(day)]);
    if (target) target.appendChild(card);
    document.dispatchEvent(new CustomEvent("unsaved-change"));
  }

  // ---- dragging ---------------------------------------------------------

  let dragged = null;

  form.addEventListener("dragstart", (event) => {
    const card = event.target.closest("[data-roster-card]");
    if (!card) return;
    dragged = card;
    card.classList.add("is-dragging");
    form.classList.add("is-dragging");
    // Some browsers refuse to start a drag at all without data on it, and the
    // effect has to be set here rather than in dragover or the cursor stays a
    // "no entry" sign the whole way across the page.
    event.dataTransfer.effectAllowed = "move";
    try {
      event.dataTransfer.setData("text/plain", card.dataset.cardIndex || "card");
    } catch (error) {
      /* Safari in some versions throws on setData outside a user gesture. The
         drag still works; there is nothing to recover from. */
    }
  });

  form.addEventListener("dragend", () => {
    if (dragged) dragged.classList.remove("is-dragging");
    form.classList.remove("is-dragging");
    columns.forEach((column) => column.classList.remove("is-over"));
    dragged = null;
  });

  columns.forEach((column) => {
    column.addEventListener("dragover", (event) => {
      if (!dragged) return;
      // preventDefault is what marks this a valid drop target. Without it the
      // drop event never fires and the card springs back, which reads as the
      // page having refused the move rather than as a missing line of script.
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      column.classList.add("is-over");
    });

    column.addEventListener("dragleave", (event) => {
      // Only when the pointer has really left: dragleave fires for every child
      // element crossed on the way in, so the naive version flickers the
      // highlight off the moment the cursor reaches a card inside the column.
      if (!column.contains(event.relatedTarget)) column.classList.remove("is-over");
    });

    column.addEventListener("drop", (event) => {
      if (!dragged) return;
      event.preventDefault();
      column.classList.remove("is-over");
      moveTo(dragged, column.dataset.rosterDay);
    });
  });

  // ---- the keyboard equivalent -----------------------------------------
  //
  // A drag has no keyboard version and cannot be offered to a screen reader at
  // all, so the arrows are not a courtesy — they are the only way half a team
  // can use this page.

  form.addEventListener("click", (event) => {
    const button = event.target.closest("[data-roster-move]");
    if (!button) return;
    const card = button.closest("[data-roster-card]");
    const input = card && dateInput(card);
    if (!input) return;
    const index = days.indexOf(input.value);
    const next = index + parseInt(button.dataset.rosterMove, 10);
    if (index === -1 || next < 0 || next >= days.length) return;
    moveTo(card, days[next]);
    button.focus();
  });

  // ---- adding ------------------------------------------------------------

  form.addEventListener("click", (event) => {
    const button = event.target.closest("[data-roster-add]");
    if (!button || !template || !totalForms) return;

    const index = parseInt(totalForms.value, 10);
    if (!Number.isFinite(index)) return;

    const wrapper = document.createElement("div");
    // split/join rather than replace(): a string argument to replace() swaps
    // the *first* occurrence only, and a card carries __prefix__ a dozen times
    // over — the ones left behind would post under a form that does not exist.
    wrapper.innerHTML = template.innerHTML.split("__prefix__").join(String(index));
    const card = wrapper.querySelector("[data-roster-card]");
    if (!card) return;

    const input = dateInput(card);
    if (input) input.value = button.dataset.rosterAdd;

    const target = cardsOf(button.closest("[data-roster-day]"));
    if (!target) return;
    target.appendChild(card);

    // Last, and only once the card is really in the document: TOTAL_FORMS is
    // the promise that every index below it is present, and a card that failed
    // to build would make that a lie.
    totalForms.value = String(index + 1);
    document.dispatchEvent(new CustomEvent("unsaved-change"));

    const first = card.querySelector("select, input[type='time']");
    if (first) first.focus();
  });

  // ---- removing ----------------------------------------------------------
  //
  // The DELETE box stays in the DOM and the card is dimmed rather than hidden.
  // Hiding it would make its inputs unfocusable, and a validation error inside
  // one then makes Save do nothing at all with an unfocusable-control warning
  // in the console as the only clue.

  form.addEventListener("change", (event) => {
    const box = event.target;
    if (!box.name || !box.name.endsWith("-DELETE")) return;
    const card = box.closest("[data-roster-card]");
    if (card) card.classList.toggle("is-removed", box.checked);
    document.dispatchEvent(new CustomEvent("unsaved-change"));
  });

  form.querySelectorAll("input[name$='-DELETE']").forEach((box) => {
    if (box.checked) {
      const card = box.closest("[data-roster-card]");
      if (card) card.classList.add("is-removed");
    }
  });

  // Any edit at all arms the unsaved-changes guard. A week of dragging lost to
  // a stray click on the sidebar is the failure this page most invites.
  form.addEventListener("input", () => {
    document.dispatchEvent(new CustomEvent("unsaved-change"));
  });

  render();
})();
