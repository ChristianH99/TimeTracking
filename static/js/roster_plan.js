/* The week planner: a grid of time slots × weekdays, and names placed in it.
 *
 * ---- the one rule this file exists to keep ----
 *
 * **A name in a cell is a form row, and moving it moves the row.** The server
 * renders every row once — slots, placements, cell texts — into a holder
 * off-screen, and this script builds the grid's body from the slot rows and
 * then *moves* each placement and text into the cell its hidden `cell` input
 * names. A drop moves the element and rewrites that one input. There is never
 * a second representation of the week — no array of placements, no JSON
 * payload — because two representations of one thing is the bug where the
 * picture and the saved roster disagree, and the first edit to disagree looks
 * like a save that did not take.
 *
 * The list of people "not placed yet" under the grid is the one thing here
 * that is not a form row, and it is not stored anywhere either: it is worked
 * out from the rows in the grid every time something moves.
 *
 *
 * ---- the formset trap, in this shape ----
 *
 * Adding a row means minting it at the next free index — every `name` and `id`
 * carrying that number — *and* bumping TOTAL_FORMS. Miss the second half and
 * the row is simply not read on POST: the page looks right and the placement
 * vanishes on save.
 *
 * Removing ticks DELETE and moves the row back to the holder. It never leaves
 * the document: a form missing from the POST is a hole in the index range, and
 * Django reads the absent fields against that form's own defaults, decides it
 * changed, and validates it.
 *
 *
 * ---- dragging ----
 *
 * Pointer events rather than the HTML drag-and-drop API, because the page has
 * to work on the tablet in the staff room: HTML drag-and-drop does not start
 * from a touch on most of them, and where it does, it starts from a long press
 * — which is the gesture this page needs for somebody's own times. With
 * pointer events a mouse and a finger behave the same: move to drag, hold
 * still to open the times.
 */
(function () {
  const form = document.querySelector("[data-roster]");
  if (!form || !window.ttHours) return;

  const data = window.pageData("roster-data");
  if (!data) return;

  const H = window.ttHours;
  const body = form.querySelector("[data-grid-body]");
  const holder = form.querySelector("[data-roster-holder]");
  const emptyNote = form.querySelector("[data-grid-empty]");
  const suggest = document.querySelector("[data-suggest]");
  if (!body || !holder) return;

  const days = data.days;
  const holidays = new Set(data.holidays || []);
  const areas = data.areas || {};
  const people = new Map((data.people || []).map((person) => [String(person.id), person]));
  const errors = data.placementErrors || {};
  const STATE_ORDER = { on: 0, off: 1, away: 2 };
  const dayNames = Array.from(form.querySelectorAll(".rgrid-day .rgrid-day-name"))
    .map((el) => el.textContent.trim());

  const changed = () => document.dispatchEvent(new CustomEvent("unsaved-change"));

  // ---- the formset machinery --------------------------------------------

  function total(prefix) {
    return form.querySelector("[name='" + prefix + "-TOTAL_FORMS']");
  }

  /* A new row of the given formset, at the next free index, in the holder. */
  function mint(prefix) {
    const template = form.querySelector('[data-template="' + prefix + '"]');
    const counter = total(prefix);
    if (!template || !counter) return null;
    const index = parseInt(counter.value, 10);
    if (!Number.isFinite(index)) return null;
    const wrapper = document.createElement("div");
    // split/join rather than replace(): a string argument to replace() swaps
    // the first occurrence only, and a row carries __prefix__ many times over.
    wrapper.innerHTML = template.innerHTML.split("__prefix__").join(String(index));
    const row = wrapper.firstElementChild;
    if (!row) return null;
    holder.appendChild(row);
    // Last, and only once the row is really in the document: TOTAL_FORMS is
    // the promise that every index below it is present.
    counter.value = String(index + 1);
    return row;
  }

  function field(row, name) {
    return row.querySelector("[name$='-" + name + "']");
  }

  function isDeleted(row) {
    const box = field(row, "DELETE");
    return Boolean(box && box.checked);
  }

  function markDeleted(row) {
    const box = field(row, "DELETE");
    if (box) box.checked = true;
    holder.appendChild(row);
  }

  // ---- cells --------------------------------------------------------------

  function cellKey(slotKey, day, areaId) {
    return slotKey + "|" + day + "|" + (areaId || "");
  }

  function parseCell(value) {
    const parts = String(value || "").split("|");
    if (parts.length !== 3) return null;
    return { slot: parts[0], day: parts[1], area: parts[2] };
  }

  // ---- slots ----------------------------------------------------------------

  function slotRows() {
    return Array.from(form.querySelectorAll("[data-slot]")).filter((row) => !isDeleted(row));
  }

  function slotKey(row) {
    const id = field(row, "id");
    if (id && id.value) return id.value;
    const key = field(row, "key");
    return key ? key.value : "";
  }

  function slotByKey(key) {
    return slotRows().find((row) => slotKey(row) === key) || null;
  }

  function slotTimes(row) {
    const start = field(row, "start");
    const end = field(row, "end");
    return {
      start: start ? H.parse(start.value, true) : null,
      end: end ? H.parse(end.value, true) : null,
    };
  }

  function slotAreas(row) {
    return Array.from(row.querySelectorAll("input[type='checkbox'][name$='-areas']"))
      .filter((box) => box.checked)
      .map((box) => box.value);
  }

  let newSlotCounter = Array.from(form.querySelectorAll("[data-slot]"))
    .map((row) => /^new-(\d+)$/.exec(field(row, "key") ? field(row, "key").value : ""))
    .filter(Boolean)
    .reduce((highest, match) => Math.max(highest, parseInt(match[1], 10)), 0);

  // ---- icons ----------------------------------------------------------------

  // Cloned from a <template> rather than built with createElementNS: the
  // template is parsed as SVG by the browser, and this file does not have to
  // spell out a namespace URL.
  const iconTemplate = form.querySelector('[data-template="icon"]');

  function icon(name) {
    const svg = iconTemplate
      ? iconTemplate.content.firstElementChild.cloneNode(true)
      : document.createElement("span");
    const use = svg.querySelector("use");
    if (use) use.setAttribute("href", data.sprite + "#" + name);
    return svg;
  }

  /* The area pickers: an icon beside each name, and an area that is no longer
     in use offered only to a slot that already has it. */
  function decorateAreaChoices(scope) {
    scope.querySelectorAll("[data-area-choice]").forEach((label) => {
      const area = areas[label.dataset.areaChoice];
      if (!area) return;
      if (!label.querySelector(".ricon")) {
        label.insertBefore(icon(area.icon), label.querySelector("span"));
      }
      const box = label.querySelector("input");
      label.hidden = !area.active && !(box && box.checked);
    });
  }

  // ---- building the grid ------------------------------------------------

  /* Rebuild the grid's body from the slot rows, and send every placement and
   * text home to the cell it names.
   *
   * Called on load and whenever a slot's times or areas change. Everything is
   * first gathered back into the holder, so a row whose cell has gone stays
   * in the document — with its DELETE untouched — rather than disappearing
   * with the table row it was in.
   */
  function render() {
    const focused = document.activeElement;
    closeSuggest();

    form.querySelectorAll("[data-slot], [data-placement], [data-note]").forEach((row) => {
      if (row.parentElement !== holder) holder.appendChild(row);
    });
    body.textContent = "";

    const order = slotRows().map((row, index) => ({ row, index, times: slotTimes(row) }));
    order.sort((a, b) => {
      const as = a.times.start === null ? Infinity : a.times.start;
      const bs = b.times.start === null ? Infinity : b.times.start;
      if (as !== bs) return as - bs;
      const ae = a.times.end === null ? Infinity : a.times.end;
      const be = b.times.end === null ? Infinity : b.times.end;
      return ae !== be ? ae - be : a.index - b.index;
    });

    const cells = new Map();
    const firstCell = new Map();      // slot|day -> the cell an orphan goes to

    order.forEach(({ row }) => {
      const key = slotKey(row);
      const split = slotAreas(row);
      const lines = split.length ? split : [""];
      lines.forEach((areaId, lineIndex) => {
        const tr = document.createElement("tr");
        tr.className = "rgrid-row" + (lineIndex === 0 ? " is-first" : "");
        if (lineIndex === 0) {
          const th = document.createElement("th");
          th.scope = "row";
          th.className = "rgrid-time";
          th.rowSpan = lines.length;
          if (!split.length) th.colSpan = 2;
          th.appendChild(row);
          tr.appendChild(th);
        }
        if (split.length) {
          const th = document.createElement("th");
          th.scope = "row";
          th.className = "rgrid-area";
          const area = areas[areaId];
          if (area) {
            th.appendChild(icon(area.icon));
            const name = document.createElement("span");
            name.textContent = area.name;
            th.appendChild(name);
          }
          tr.appendChild(th);
        }
        days.forEach((day) => {
          const td = document.createElement("td");
          td.className = "rgrid-cell" + (holidays.has(day) ? " is-holiday" : "");
          const keyHere = cellKey(key, day, areaId);
          td.dataset.cell = keyHere;
          const list = document.createElement("div");
          list.className = "rcell-people";
          list.dataset.cellPeople = "";
          td.appendChild(list);
          tr.appendChild(td);
          cells.set(keyHere, td);
          if (lineIndex === 0) firstCell.set(key + "|" + day, keyHere);
        });
        body.appendChild(tr);
      });
      decorateAreaChoices(row);
    });

    // Placements. One whose area has been taken off its slot moves to the
    // slot's first cell that day rather than being dropped: a visible name in
    // the wrong room takes one drag to fix, and a name that silently vanished
    // is not noticed until the morning nobody is in that room.
    form.querySelectorAll("[data-placement]").forEach((chip) => {
      if (isDeleted(chip)) return;
      const input = field(chip, "cell");
      let td = input ? cells.get(input.value) : null;
      if (!td && input) {
        const where = parseCell(input.value);
        const fallback = where && firstCell.get(where.slot + "|" + where.day);
        if (fallback) {
          input.value = fallback;
          td = cells.get(fallback);
        }
      }
      if (td) td.querySelector("[data-cell-people]").appendChild(chip);
    });

    // Texts: one per cell, and every cell gets one so there is always a box
    // to type into. A text whose cell has gone waits in the holder and the
    // server drops it — the browser has already taken it off the page.
    form.querySelectorAll("[data-note]").forEach((note) => {
      const input = field(note, "cell");
      const td = input ? cells.get(input.value) : null;
      if (td && !td.querySelector("[data-note]")) td.appendChild(note);
    });
    cells.forEach((td, key) => {
      if (td.querySelector("[data-note]")) return;
      const note = mint("note");
      if (!note) return;
      field(note, "cell").value = key;
      td.appendChild(note);
    });
    cells.forEach((td) => labelCellInput(td));

    if (emptyNote) emptyNote.hidden = order.length > 0;
    refresh();

    if (focused && focused !== document.body && document.contains(focused)) {
      focused.focus({ preventScroll: true });
    }
  }

  function labelCellInput(td) {
    const input = td.querySelector("[data-cell-input]");
    const where = parseCell(td.dataset.cell);
    if (!input || !where) return;
    const slot = slotByKey(where.slot);
    const times = slot ? slotTimes(slot) : { start: null, end: null };
    const parts = [dayNames[days.indexOf(where.day)] || where.day];
    if (times.start !== null && times.end !== null) {
      parts.push(H.clockOfDay(times.start) + "–" + H.clockOfDay(times.end));
    }
    if (where.area && areas[where.area]) parts.push(areas[where.area].name);
    input.setAttribute("aria-label", parts.join(", "));
    input.placeholder = "";
  }

  // ---- what a name says ---------------------------------------------------

  function chipCell(chip) {
    const input = field(chip, "cell");
    return input ? parseCell(input.value) : null;
  }

  /* The minutes a placement covers: its own times where it has them, the
     slot's otherwise. Null when anything is unreadable. */
  function chipSpan(chip) {
    const where = chipCell(chip);
    const slot = where && slotByKey(where.slot);
    if (!slot) return null;
    const times = slotTimes(slot);
    const ownStart = H.parse(field(chip, "custom_start").value, true);
    const ownEnd = H.parse(field(chip, "custom_end").value, true);
    const start = ownStart === null ? times.start : ownStart;
    const end = ownEnd === null ? times.end : ownEnd;
    if (start === null || end === null) return null;
    return { start: start, end: end <= start ? end + 24 * 60 : end };
  }

  /* "Anna", "Anna (07:30)", "Anna (–07:45)" or "Anna (07:30–07:45)".
   *
   * Only what differs from the slot is written, which is what keeps a cell
   * readable: a time on every name would bury the one that is unusual. A
   * start alone is written bare and an end alone after a dash, so the two can
   * never be confused for each other.
   */
  function chipText(chip) {
    const person = people.get(field(chip, "employee").value);
    const name = person ? person.name : "?";
    const where = chipCell(chip);
    const slot = where && slotByKey(where.slot);
    if (!slot) return name;
    const times = slotTimes(slot);
    const ownStart = H.parse(field(chip, "custom_start").value, true);
    const ownEnd = H.parse(field(chip, "custom_end").value, true);
    const startDiffers = ownStart !== null && ownStart !== times.start;
    const endDiffers = ownEnd !== null && ownEnd !== times.end;
    if (startDiffers && endDiffers) {
      return name + " (" + H.clockOfDay(ownStart) + "–" + H.clockOfDay(ownEnd) + ")";
    }
    if (startDiffers) return name + " (" + H.clockOfDay(ownStart) + ")";
    if (endDiffers) return name + " (–" + H.clockOfDay(ownEnd) + ")";
    return name;
  }

  function dayState(personId, day) {
    const person = people.get(String(personId));
    return person && person.days ? person.days[day] || null : null;
  }

  function placedChips() {
    return Array.from(body.querySelectorAll("[data-placement]"));
  }

  /* Labels, warnings and the list under the grid — everything that is a
     reading of the rows rather than a row. Cheap enough to run after every
     move. */
  function refresh() {
    const chips = placedChips();
    const spans = new Map();

    chips.forEach((chip) => {
      const label = chip.querySelector("[data-chip-label]");
      const employee = field(chip, "employee").value;
      const where = chipCell(chip);
      const state = where ? dayState(employee, where.day) : null;
      const person = people.get(employee);
      if (label) label.textContent = chipText(chip);

      chip.classList.toggle("is-away", Boolean(state && state.state === "away"));
      chip.classList.toggle("is-pending", Boolean(state && state.pending));
      chip.classList.remove("is-clash");

      const notes = [person ? person.full : ""];
      if (state && state.label) notes.push(state.label);
      const prefix = field(chip, "employee").name.replace(/-employee$/, "");
      (errors[prefix] || []).forEach((message) => notes.push(message));
      chip.classList.toggle("has-error", Boolean(errors[prefix]) || chip.classList.contains("has-error"));
      chip.title = notes.filter(Boolean).join(" · ");

      const span = chipSpan(chip);
      if (where && span) {
        const key = employee + "|" + where.day;
        if (!spans.has(key)) spans.set(key, []);
        spans.get(key).push({ chip: chip, span: span });
      }
    });

    // Somebody in two places at once. The server refuses it on Save; showing
    // it here, while the drag that caused it is still fresh, is what makes the
    // refusal unnecessary.
    spans.forEach((entries) => {
      entries.forEach((a, i) => {
        entries.slice(i + 1).forEach((b) => {
          if (a.span.start < b.span.end && b.span.start < a.span.end) {
            a.chip.classList.add("is-clash");
            b.chip.classList.add("is-clash");
          }
        });
      });
    });

    renderPool(chips);
  }

  function renderPool(chips) {
    const placed = new Set(chips.map((chip) => {
      const where = chipCell(chip);
      return field(chip, "employee").value + "|" + (where ? where.day : "");
    }));

    form.querySelectorAll("[data-pool]").forEach((cell) => {
      const day = cell.dataset.pool;
      cell.textContent = "";
      const free = [];
      people.forEach((person, id) => {
        const state = person.days ? person.days[day] : null;
        if (!state || placed.has(id + "|" + day)) return;
        free.push({ id: id, person: person, state: state });
      });
      // Who works that day first, then who has no hours, then who is away —
      // the order a manager reaches for them in.
      free.sort((a, b) =>
        (STATE_ORDER[a.state.state] - STATE_ORDER[b.state.state])
        || a.person.name.localeCompare(b.person.name));
      free.forEach(({ id, person, state }) => {
        const chip = document.createElement("span");
        chip.className = "rpool-chip"
          + (state.state === "off" ? " is-off" : "")
          + (state.state === "away" ? " is-away" : "")
          + (state.pending ? " is-pending" : "");
        chip.dataset.poolPerson = id;
        chip.dataset.poolDay = day;
        chip.tabIndex = 0;
        chip.textContent = person.name;
        chip.title = [person.full, state.label || ""].filter(Boolean).join(" · ");
        cell.appendChild(chip);
      });
    });
  }

  // ---- placing, moving, removing ----------------------------------------

  function cellElement(key) {
    return Array.from(body.querySelectorAll("[data-cell]")).find((td) => td.dataset.cell === key) || null;
  }

  function inCell(td, employee) {
    return Array.from(td.querySelectorAll("[data-placement]"))
      .some((chip) => field(chip, "employee").value === String(employee));
  }

  function place(td, employee, ownStart, ownEnd) {
    if (!td || inCell(td, employee)) return null;
    const chip = mint("place");
    if (!chip) return null;
    field(chip, "employee").value = String(employee);
    field(chip, "cell").value = td.dataset.cell;
    field(chip, "custom_start").value = ownStart || "";
    field(chip, "custom_end").value = ownEnd || "";
    td.querySelector("[data-cell-people]").appendChild(chip);
    return chip;
  }

  function move(chip, td) {
    if (!td || chip.closest("[data-cell]") === td) return;
    if (inCell(td, field(chip, "employee").value)) return;
    const before = chipCell(chip);
    const after = parseCell(td.dataset.cell);
    // Somebody's own times are times *within a slot*. Carried into another
    // slot they would be read against the wrong range — 07:30 in a 12:00–13:00
    // slot — so they go; moved to another day or room of the same slot, they
    // stay.
    if (!before || !after || before.slot !== after.slot) {
      field(chip, "custom_start").value = "";
      field(chip, "custom_end").value = "";
    }
    field(chip, "cell").value = td.dataset.cell;
    td.querySelector("[data-cell-people]").appendChild(chip);
  }

  function remove(chip) {
    markDeleted(chip);
  }

  // ---- slots: add, change, remove ---------------------------------------

  const addSlot = form.querySelector("[data-slot-add]");
  if (addSlot) {
    addSlot.addEventListener("click", () => {
      const rows = slotRows();
      let start = 7 * 60;
      rows.forEach((row) => {
        const times = slotTimes(row);
        if (times.end !== null && times.start !== null && times.end > times.start) {
          start = Math.max(start, times.end);
        }
      });
      start = Math.min(start, 23 * 60);
      const row = mint("slot");
      if (!row) return;
      newSlotCounter += 1;
      field(row, "key").value = "new-" + newSlotCounter;
      field(row, "start").value = H.clockOfDay(start);
      field(row, "end").value = H.clockOfDay(Math.min(start + 60, 24 * 60 - 1));
      render();
      changed();
      field(row, "start").focus();
    });
  }

  // A slot's times are re-read when somebody leaves the box, after
  // timeinput.js has normalised what they typed (its listener sits on the
  // document, so it runs after this one; hence the zero timeout).
  form.addEventListener("focusout", (event) => {
    const input = event.target;
    if (!input.closest || !input.closest("[data-slot]")) return;
    if (!/-(start|end)$/.test(input.name || "")) return;
    window.setTimeout(render, 0);
  });

  form.addEventListener("change", (event) => {
    const box = event.target;
    if (box.closest && box.closest("[data-slot-areas]")) {
      render();
      changed();
    }
  });

  form.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-slot-remove]");
    if (!button) return;
    const row = button.closest("[data-slot]");
    if (!row) return;
    const key = slotKey(row);
    const count = placedChips().filter((chip) => {
      const where = chipCell(chip);
      return where && where.slot === key;
    }).length;
    const times = slotTimes(row);
    const range = times.start !== null && times.end !== null
      ? H.clockOfDay(times.start) + "–" + H.clockOfDay(times.end) : "";
    if (count && window.appConfirm) {
      const ok = await window.appConfirm({
        title: interpolate(gettext("Remove %s?"), [range]),
        // Not ngettext: the browser's catalogue carries no plural forms
        // (tools/apply_translations.py writes singular entries only), and a
        // count written as a number reads the same either way.
        body: interpolate(gettext("People placed in it: %s. They are taken out with it."), [count]),
        accept: gettext("Remove"),
        danger: true,
      });
      if (!ok) return;
    }
    const box = field(row, "DELETE");
    if (box) box.checked = true;
    render();
    changed();
  });

  // ---- the chips: remove, keyboard, own times ---------------------------

  form.addEventListener("click", (event) => {
    const button = event.target.closest("[data-chip-remove]");
    if (!button) return;
    const chip = button.closest("[data-placement]");
    if (!chip) return;
    const next = chip.nextElementSibling || chip.parentElement.closest("[data-cell]");
    remove(chip);
    refresh();
    changed();
    const input = next && next.closest("[data-cell]") && next.closest("[data-cell]").querySelector("[data-cell-input]");
    if (input) input.focus();
  });

  form.addEventListener("keydown", (event) => {
    const chip = event.target.closest && event.target.closest("[data-placement]");
    if (!chip || event.target !== chip) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openTimes(chip);
    } else if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      const cell = chip.closest("[data-cell]");
      remove(chip);
      refresh();
      changed();
      const input = cell && cell.querySelector("[data-cell-input]");
      if (input) input.focus();
    }
  });

  form.addEventListener("contextmenu", (event) => {
    const chip = event.target.closest("[data-placement]");
    if (!chip || !chip.closest("[data-cell]")) return;
    event.preventDefault();
    openTimes(chip);
  });

  // ---- the times dialog ---------------------------------------------------

  const timesModal = document.querySelector("[data-times-modal]");
  const times = timesModal && window.modalController ? {
    controller: window.modalController(timesModal),
    title: timesModal.querySelector("[data-times-title]"),
    standard: timesModal.querySelector("[data-times-standard]"),
    start: timesModal.querySelector("[data-times-start]"),
    end: timesModal.querySelector("[data-times-end]"),
    error: timesModal.querySelector("[data-times-error]"),
    chip: null,
  } : null;

  function openTimes(chip) {
    if (!times || times.controller.isOpen()) return;
    const where = chipCell(chip);
    const slot = where && slotByKey(where.slot);
    if (!slot) return;
    const range = slotTimes(slot);
    if (range.start === null || range.end === null) return;
    const person = people.get(field(chip, "employee").value);
    const ownStart = H.parse(field(chip, "custom_start").value, true);
    const ownEnd = H.parse(field(chip, "custom_end").value, true);
    times.chip = chip;
    times.range = range;
    times.title.textContent = interpolate(gettext("Times for %s"), [person ? person.full : ""]);
    times.standard.textContent = interpolate(
      gettext("%(day)s, time range %(range)s. Enter the exact times this person works; the cell then shows only the time that differs."),
      { day: dayNames[days.indexOf(where.day)] || where.day,
        range: H.clockOfDay(range.start) + "–" + H.clockOfDay(range.end) }, true);
    times.start.value = H.clockOfDay(ownStart === null ? range.start : ownStart);
    times.end.value = H.clockOfDay(ownEnd === null ? range.end : ownEnd);
    times.error.hidden = true;
    times.controller.open();
    times.start.select();
  }

  function applyTimes(useRange) {
    const chip = times.chip;
    if (!chip) return;
    let start = times.range.start;
    let end = times.range.end;
    if (!useRange) {
      start = H.parse(times.start.value, true);
      end = H.parse(times.end.value, true);
      if (start === null || end === null || start >= 24 * 60 || end >= 24 * 60) {
        times.error.textContent = gettext("That is not a time this app can read. Try 8:30, 8,5 or 830.");
        times.error.hidden = false;
        return;
      }
      if (start === end) {
        times.error.textContent = gettext("The times need a length.");
        times.error.hidden = false;
        return;
      }
    }
    field(chip, "custom_start").value = start === times.range.start ? "" : H.clockOfDay(start);
    field(chip, "custom_end").value = end === times.range.end ? "" : H.clockOfDay(end);
    times.chip = null;
    times.controller.close();
    refresh();
    changed();
  }

  if (times) {
    // The dialog's own form: Enter in either box, or Apply, lands here. It
    // is never sent anywhere.
    timesModal.querySelector("[data-times-form]").addEventListener("submit", (event) => {
      event.preventDefault();
      // Normalise first, so "730" is read the way the box will show it.
      [times.start, times.end].forEach((input) =>
        input.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
      applyTimes(false);
    });
    timesModal.querySelector("[data-times-reset]").addEventListener("click", () => applyTimes(true));
    timesModal.querySelector("[data-times-cancel]").addEventListener("click", () => {
      times.chip = null;
      times.controller.close();
    });
  }

  // ---- dragging -------------------------------------------------------------

  const LONG_PRESS_MS = 550;
  const DRAG_THRESHOLD = 6;
  let drag = null;

  function dropTarget(x, y) {
    const under = document.elementFromPoint(x, y);
    if (!under) return null;
    return under.closest("[data-cell]") || under.closest("[data-pool]") || null;
  }

  function clearOver() {
    form.querySelectorAll(".is-drop-target").forEach((el) => el.classList.remove("is-drop-target"));
  }

  form.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || drag) return;
    if (event.target.closest("[data-chip-remove]")) return;
    const chip = event.target.closest("[data-placement], [data-pool-person]");
    if (!chip || !form.contains(chip) || chip.closest("[data-roster-holder]")) return;
    drag = {
      chip: chip, pointerId: event.pointerId, x: event.clientX, y: event.clientY,
      started: false, ghost: null, timer: null,
    };
    // Holding still opens somebody's own times — on a touch screen there is
    // no right click, and this is the gesture people already know for "more".
    if (event.pointerType !== "mouse" && chip.hasAttribute("data-placement")) {
      drag.timer = window.setTimeout(() => {
        const pending = drag;
        drag = null;
        if (pending && !pending.started) openTimes(pending.chip);
      }, LONG_PRESS_MS);
    }
  });

  function startDrag(event) {
    window.clearTimeout(drag.timer);
    drag.started = true;
    const ghost = drag.chip.cloneNode(true);
    ghost.classList.add("rdrag-ghost");
    ghost.removeAttribute("data-placement");
    ghost.removeAttribute("data-pool-person");
    ghost.querySelectorAll("input, button").forEach((el) => el.remove());
    ghost.setAttribute("aria-hidden", "true");
    document.body.appendChild(ghost);
    drag.ghost = ghost;
    drag.chip.classList.add("is-dragging");
    form.classList.add("is-dragging");
    try { drag.chip.setPointerCapture(event.pointerId); } catch (error) { /* already released */ }
  }

  function moveGhost(event) {
    // Positioned through the CSSOM, which the CSP allows; a style="" attribute
    // in the markup is what it forbids.
    drag.ghost.style.transform =
      "translate(" + (event.clientX + 8) + "px, " + (event.clientY + 8) + "px)";
  }

  document.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (!drag.started) {
      if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) < DRAG_THRESHOLD) return;
      startDrag(event);
    }
    event.preventDefault();
    moveGhost(event);
    clearOver();
    const target = dropTarget(event.clientX, event.clientY);
    if (target) target.classList.add("is-drop-target");
  });

  function endDrag() {
    if (!drag) return;
    window.clearTimeout(drag.timer);
    if (drag.ghost) drag.ghost.remove();
    drag.chip.classList.remove("is-dragging");
    form.classList.remove("is-dragging");
    clearOver();
    drag = null;
  }

  document.addEventListener("pointerup", (event) => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (!drag.started) { endDrag(); return; }
    const chip = drag.chip;
    const copy = event.ctrlKey || event.metaKey || event.altKey;
    const target = dropTarget(event.clientX, event.clientY);
    endDrag();
    if (!target) return;

    if (chip.hasAttribute("data-pool-person")) {
      if (target.hasAttribute("data-cell")) place(target, chip.dataset.poolPerson);
    } else if (target.hasAttribute("data-pool")) {
      remove(chip);
    } else if (copy) {
      place(target, field(chip, "employee").value,
        chipCell(chip) && parseCell(target.dataset.cell).slot === chipCell(chip).slot
          ? field(chip, "custom_start").value : "",
        chipCell(chip) && parseCell(target.dataset.cell).slot === chipCell(chip).slot
          ? field(chip, "custom_end").value : "");
    } else {
      move(chip, target);
    }
    refresh();
    changed();
  });

  document.addEventListener("pointercancel", endDrag);

  // ---- typing in a cell: text, and the people it might name -------------

  let active = { input: null, options: [], index: -1 };

  function closeSuggest() {
    if (!suggest) return;
    suggest.hidden = true;
    suggest.textContent = "";
    if (active.input) {
      active.input.removeAttribute("aria-activedescendant");
      active.input.setAttribute("aria-expanded", "false");
    }
    active = { input: null, options: [], index: -1 };
  }

  /* The word being typed: whatever follows the last space before the cursor.
     So "Garden with Chr" suggests Christian, and picking him leaves "Garden
     with" as the cell's text. */
  function currentWord(input) {
    const upto = input.value.slice(0, input.selectionStart === null ? input.value.length : input.selectionStart);
    const match = /(\S+)$/.exec(upto);
    return match ? { word: match[1], at: upto.length - match[1].length, end: upto.length } : null;
  }

  function fold(text) {
    return String(text).toLocaleLowerCase()
      .normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  function candidates(td, word) {
    const where = parseCell(td.dataset.cell);
    if (!where) return [];
    const needle = fold(word);
    const found = [];
    people.forEach((person, id) => {
      const state = person.days ? person.days[where.day] : null;
      if (!state || inCell(td, id)) return;
      const words = fold(person.full).split(/\s+/).concat([fold(person.name)]);
      if (!words.some((w) => w.startsWith(needle))) return;
      found.push({ id: id, person: person, state: state });
    });
    found.sort((a, b) =>
      (STATE_ORDER[a.state.state] - STATE_ORDER[b.state.state])
      || a.person.name.localeCompare(b.person.name));
    return found.slice(0, 8);
  }

  function showSuggest(input) {
    if (!suggest) return;
    const td = input.closest("[data-cell]");
    const typed = currentWord(input);
    if (!td || !typed) { closeSuggest(); return; }
    const found = candidates(td, typed.word);
    if (!found.length) { closeSuggest(); return; }

    suggest.textContent = "";
    found.forEach((entry, index) => {
      const li = document.createElement("li");
      li.id = "roster-suggest-" + index;
      li.setAttribute("role", "option");
      li.className = "rsuggest-option"
        + (entry.state.state === "off" ? " is-off" : "")
        + (entry.state.state === "away" ? " is-away" : "");
      li.dataset.person = entry.id;
      li.textContent = entry.person.full;
      if (entry.state.label) {
        const note = document.createElement("span");
        note.className = "rsuggest-note";
        note.textContent = entry.state.label;
        li.appendChild(note);
      }
      suggest.appendChild(li);
    });
    // Inside the cell, so it is positioned by the stylesheet against the cell
    // and scrolls with the grid, with no coordinates to work out.
    td.appendChild(suggest);
    suggest.hidden = false;
    input.setAttribute("aria-controls", suggest.id);
    input.setAttribute("aria-expanded", "true");
    active = { input: input, options: found, index: -1, typed: typed };
    highlight(0);
  }

  function highlight(index) {
    if (!suggest) return;
    const items = Array.from(suggest.children);
    if (!items.length) return;
    active.index = (index + items.length) % items.length;
    items.forEach((li, i) => li.setAttribute("aria-selected", i === active.index ? "true" : "false"));
    active.input.setAttribute("aria-activedescendant", items[active.index].id);
  }

  function pick(index) {
    const input = active.input;
    const entry = active.options[index];
    const typed = active.typed;
    if (!input || !entry) return;
    const td = input.closest("[data-cell]");
    place(td, entry.id);
    // The name was typed to find the person, not as text for the cell.
    const before = input.value.slice(0, typed.at).replace(/\s+$/, "");
    const after = input.value.slice(typed.end).replace(/^\s+/, "");
    input.value = (before && after) ? before + " " + after : before + after;
    closeSuggest();
    refresh();
    changed();
    input.focus();
  }

  form.addEventListener("input", (event) => {
    if (event.target.matches && event.target.matches("[data-cell-input]")) {
      showSuggest(event.target);
    }
  });

  form.addEventListener("keydown", (event) => {
    const input = event.target;
    if (!input.matches || !input.matches("[data-cell-input]")) return;
    const open = suggest && !suggest.hidden && active.input === input;
    if (event.key === "ArrowDown" && open) {
      event.preventDefault();
      highlight(active.index + 1);
    } else if (event.key === "ArrowUp" && open) {
      event.preventDefault();
      highlight(active.index - 1);
    } else if (event.key === "Enter") {
      // Enter in a cell never saves the whole week: it either picks the
      // highlighted person or does nothing, which is what somebody typing a
      // name expects of it.
      event.preventDefault();
      if (open && active.index >= 0) pick(active.index);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      event.stopPropagation();
      closeSuggest();
    }
  });

  if (suggest) {
    // mousedown, not click: a click lands after the box has lost focus, and
    // losing focus closes the list.
    suggest.addEventListener("mousedown", (event) => {
      const li = event.target.closest("[role='option']");
      if (!li) return;
      event.preventDefault();
      pick(Array.from(suggest.children).indexOf(li));
    });
  }

  form.addEventListener("focusout", (event) => {
    if (event.target.matches && event.target.matches("[data-cell-input]")) {
      window.setTimeout(() => {
        if (active.input === event.target && document.activeElement !== event.target) closeSuggest();
      }, 0);
    }
  });

  // ---- start --------------------------------------------------------------

  decorateAreaChoices(holder);
  render();

  // A week copied from the last one is a draft that has not been saved, and
  // walking away from it has to be a question.
  if (form.hasAttribute("data-roster-draft")) changed();
})();
