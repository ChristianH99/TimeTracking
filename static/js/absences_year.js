/* The Time off year: the calendar's day pop-up, and the extra-off-days one.
 *
 * **The squares are the only representation of the year.** There is no array of
 * days here and no JSON payload beside the grid — every square already carries
 * what it is on data attributes the server wrote, and the pop-up is filled from
 * the square that was clicked. Two representations of one year is the bug where
 * the picture and the booking disagree, and the first one to disagree looks
 * like a save that did not take.
 *
 * **This file writes no text.** Every sentence the dialogs say is rendered by
 * the template, in the page's own catalogue, and shown or hidden from here —
 * which is the same choice monthpicker.js makes about month names. A script
 * that assembles prose out of fragments is a script whose German nobody can
 * read in one piece.
 */
(function () {
  const grid = document.querySelector("[data-year-calendar]");
  const modal = document.querySelector("[data-book-modal]");
  if (!grid || !modal) return;

  const controller = window.modalController(modal);

  const title = modal.querySelector("[data-book-title]");
  const existing = modal.querySelector("[data-book-existing]");
  const fresh = modal.querySelector("[data-book-new]");

  const what = modal.querySelector("[data-book-what]");
  const when = modal.querySelector("[data-book-when]");
  const state = modal.querySelector("[data-book-state]");
  const halfPill = modal.querySelector("[data-book-half]");
  const groupNote = modal.querySelector("[data-book-group]");

  const cancelForm = modal.querySelector("[data-book-cancel-form]");
  const withdraw = modal.querySelector("[data-book-withdraw]");
  const ask = modal.querySelector("[data-book-ask]");
  const notes = {
    withdraw: modal.querySelector("[data-book-note-withdraw]"),
    ask: modal.querySelector("[data-book-note-ask]"),
    "": modal.querySelector("[data-book-note-waiting]"),
  };

  const start = modal.querySelector("[data-book-start]");
  const end = modal.querySelector("[data-book-end]");
  const halfDay = modal.querySelector("[data-book-halfday]");
  const note = modal.querySelector("[data-book-note]");
  const noteField = modal.querySelector("[data-book-note-field]");
  const hints = {
    holiday: modal.querySelector("[data-book-hint-holiday]"),
    overtime: modal.querySelector("[data-book-hint-overtime]"),
    sick: modal.querySelector("[data-book-hint-sick]"),
  };

  /* A half day is one date and only one date, refused on a range by the model
   * and by both forms. Offering the box and then refusing it is a worse answer
   * than not offering it: the message would arrive after a reload, about a
   * checkbox that is no longer on screen. Unticked as well as disabled — a
   * ticked-and-disabled box still looks answered. */
  function syncHalf(from, to, box) {
    const single = Boolean(from.value) && from.value === to.value;
    if (!single) box.checked = false;
    box.disabled = !single;
  }

  /* Sickness records dates and nothing else. The note is not merely optional
   * here — it is the box a diagnosis would end up in, and this app holds no
   * health data at all. Cleared as well as hidden, so a note typed against a
   * holiday and then switched to sick is not posted anyway. */
  function syncKind() {
    const chosen = modal.querySelector("[data-book-kind]:checked");
    const kind = chosen ? chosen.value : "holiday";
    Object.keys(hints).forEach((name) => {
      if (hints[name]) hints[name].hidden = name !== kind;
    });
    const sick = kind === "sick";
    if (sick) note.value = "";
    noteField.hidden = sick;
  }

  function openExisting(day) {
    what.textContent = day.dataset.what || "";
    when.textContent = day.dataset.when || "";
    state.textContent = day.dataset.state || "";
    halfPill.hidden = day.dataset.half !== "1";
    // A booking of several days is one row and one thing to take back, so the
    // dialog says so before the button that does it.
    groupNote.hidden = day.dataset.group !== "1";

    const action = day.dataset.action || "";
    withdraw.hidden = action !== "withdraw";
    ask.hidden = action !== "ask";
    Object.keys(notes).forEach((name) => {
      if (notes[name]) notes[name].hidden = name !== action;
    });
    // Nothing to press on a cancellation already with the manager, so the form
    // is not a form at that point — leaving it submittable would post an empty
    // action to a view that would answer "you have already asked for that".
    cancelForm.action = action
      ? grid.dataset.cancelUrl.replace("/0/", "/" + day.dataset.absence + "/")
      : "";

    existing.hidden = false;
    fresh.hidden = true;
  }

  function openFresh(day) {
    start.value = day.dataset.date;
    end.value = day.dataset.date;
    note.value = "";
    const first = modal.querySelector("[data-book-kind]");
    if (first) first.checked = true;
    syncKind();
    syncHalf(start, end, halfDay);

    existing.hidden = true;
    fresh.hidden = false;
  }

  grid.addEventListener("click", (event) => {
    const day = event.target.closest("button[data-date]");
    if (!day) return;
    title.textContent = day.dataset.label || "";
    if (day.dataset.absence) openExisting(day);
    else openFresh(day);
    // After the halves are set, never before: modalController focuses the first
    // control it can see, and a control inside a hidden half is not one.
    controller.open();
  });

  [start, end].forEach((input) => {
    input.addEventListener("change", () => {
      // The end follows the start while it would otherwise be behind it. The
      // server refuses that pair, but a dialog that lets somebody type it and
      // then loses the whole request to a reload has spent their time to say
      // something it could have said by moving one box.
      if (end.value && start.value && end.value < start.value) end.value = start.value;
      syncHalf(start, end, halfDay);
    });
  });
  modal.querySelectorAll("[data-book-kind]").forEach((radio) => {
    radio.addEventListener("change", syncKind);
  });
  modal.addEventListener("click", (event) => {
    if (event.target.closest("[data-book-cancel], [data-book-close]")) controller.close();
  });

  /* Extra off days. Its own dialog because it asks a question none of the three
   * on the calendar does — which entitlement the days come out of — and special
   * leave cannot be saved without the answer. */
  const specialModal = document.querySelector("[data-special-modal]");
  if (!specialModal) return;
  const specialController = window.modalController(specialModal);
  const specialStart = specialModal.querySelector("[data-special-start]");
  const specialEnd = specialModal.querySelector("[data-special-end]");
  const specialHalf = specialModal.querySelector("[data-special-halfday]");

  document.querySelectorAll("[data-special-open]").forEach((button) => {
    button.addEventListener("click", () => {
      // Today at both ends. A funeral is nearly always one date and usually a
      // near one, and an empty pair of boxes is two more things to fill in
      // before the dialog will accept anything at all.
      const today = grid.dataset.today;
      if (today && !specialStart.value) {
        specialStart.value = today;
        specialEnd.value = today;
      }
      syncHalf(specialStart, specialEnd, specialHalf);
      specialController.open();
    });
  });
  [specialStart, specialEnd].forEach((input) => {
    input.addEventListener("change", () => {
      if (specialEnd.value && specialStart.value && specialEnd.value < specialStart.value) {
        specialEnd.value = specialStart.value;
      }
      syncHalf(specialStart, specialEnd, specialHalf);
    });
  });
  specialModal.addEventListener("click", (event) => {
    if (event.target.closest("[data-special-cancel]")) specialController.close();
  });
})();
