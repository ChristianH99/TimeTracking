/* The monthly timesheet: two pop-ups, a comment box, and no Save button.
 *
 * **Every change is written the moment it is made.** A comment when the box is
 * left; bookings and a correction when the pop-up is accepted. There is nothing
 * unsaved on this page at any point, which is why there is no Save and no
 * unsaved-changes guard — a page that has one teaches people to look for it
 * before they navigate away, and this one no longer rewards that habit.
 *
 * **The server does the arithmetic and hands the whole month back.** Editing the
 * third of the month moves the running total on every row below it and all six
 * figures in the footer; a reply carrying only the edited row would leave the
 * rest of the column stale, and repeating the prefix sum, the break rules and
 * the credited-hours branches here is exactly the duplication `build_month`
 * exists to avoid. So `save` posts one day and repaints from what comes back.
 *
 * The one calculation that *is* repeated is the break, and only inside the
 * pop-up: it has to answer while somebody types, and asking the server per
 * keystroke is a request per character. apps/timesheets/tests.py holds the two
 * implementations to the same answers.
 *
 * Reads window.ttHours (static/js/hours.js), which must therefore be loaded
 * first. config/tests.py walks every template to check that it is.
 */
(function () {
  const table = document.querySelector("[data-month-table]");
  if (!table || !window.ttHours) return;

  const hours = window.ttHours;
  const rules = window.pageData ? window.pageData("break-rules") : null;
  const saveState = document.querySelector("[data-save-state]");

  const COMING = "in";
  const GOING = "out";
  /* Four, and never a fifth. The row's height is the whole point of the cell:
     this is a grid read down a column, and a day that gets taller pushes every
     figure below it out of the place the eye last found it. The server's
     `BOOKINGS_SHOWN` is the same four, and the two only ever disagree for as
     long as it takes a repaint. */
  const SHOWN = 4;

  /* The label a booking wears, and the key that enters it.
   *
   * The letters come from the translated words themselves rather than from a
   * hard-coded "c"/"g", because the whole point of the shortcut is that it is
   * the first letter of what the button says — and in German the buttons say
   * Kommen and Gehen. A pair that agreed in English and not in German would be
   * a shortcut that silently does nothing for everybody who actually uses this
   * app. */
  const LABEL = {};
  LABEL[COMING] = gettext("Coming");
  LABEL[GOING] = gettext("Going");
  const KEY = {};
  KEY[LABEL[COMING].charAt(0).toLowerCase()] = COMING;
  KEY[LABEL[GOING].charAt(0).toLowerCase()] = GOING;

  /* ---- what a row currently says --------------------------------------- */

  /* The day's bookings, off the cell that holds them.
   *
   * "in 08:30,out 12:00" — the whole day, whatever the four chips beside it had
   * room for. There is one representation of a day and this is it; the chips are
   * drawn from the same string, which is what stops the cell and the day
   * disagreeing about a punch nobody could see. */
  function readBookings(row) {
    const cell = row.querySelector("[data-bookings]");
    return (cell.dataset.bookings || "")
      .split(",")
      .filter((part) => part.trim())
      .map((part) => {
        const bits = part.trim().split(/\s+/);
        return { kind: bits[0], time: bits[1] };
      });
  }

  function correctionCellOf(row) {
    return row.querySelector("[data-correction]");
  }

  function suggested(row) {
    const suggestion = row.querySelector("[data-suggestion]");
    if (!suggestion) return [];
    return (suggestion.dataset.times || "")
      .split(";")
      .filter((pair) => pair.indexOf(",") > 0)
      .reduce((all, pair) => {
        const parts = pair.split(",");
        all.push({ kind: COMING, time: parts[0] });
        all.push({ kind: GOING, time: parts[1] });
        return all;
      }, []);
  }

  /* ---- writing one day ------------------------------------------------- */

  /* Everything the endpoint needs for one day, taken from the row as it stands.
   *
   * The whole day goes every time, not only the part that changed: the endpoint
   * writes a day, so a correction left out of the payload would read as one
   * somebody had cleared. Whichever caller has a new value passes it in. */
  function payload(row, changes) {
    const date = row.dataset.day;
    const cell = correctionCellOf(row);
    const bookings = changes.bookings || readBookings(row);
    const fields = {
      ["correction-" + date]: cell.dataset.correction || "",
      ["why-" + date]: cell.dataset.reason || "",
      ["note-" + date]: row.querySelector("[data-note]").value,
    };
    fields["time-" + date] = bookings.map((booking) => booking.time);
    fields["kind-" + date] = bookings.map((booking) => booking.kind);
    if (changes.correction !== undefined) {
      fields["correction-" + date] = changes.correction;
      fields["why-" + date] = changes.why;
    }
    if (changes.note !== undefined) fields["note-" + date] = changes.note;
    return fields;
  }

  /* Post one day; repaint the month from the answer.
   *
   * Resolves to `{error}` when the server refused, and the caller decides where
   * that goes — a pop-up keeps it inside itself and stays open, because the
   * times that caused it are still on the screen there; a comment box has
   * nowhere better than the bar above the table.
   *
   * The URL is the page's own with a placeholder date swapped out. Reversed by
   * the template rather than glued together here, because the two prefixes —
   * your own timesheet and a manager's view of somebody else's — are different
   * routes, and a string built in a script cannot know which one it is on. This
   * file is served as a static asset and is never rendered, so a template tag
   * in it would be a syntax error on a page that still loads. */
  function save(row, changes) {
    const date = row.dataset.day;
    const fields = payload(row, changes || {});
    const body = new URLSearchParams();
    body.set("month", date.slice(0, 7));
    Object.keys(fields).forEach((name) => {
      const value = fields[name];
      if (Array.isArray(value)) value.forEach((item) => body.append(name, item));
      else body.set(name, value);
    });

    return fetch(table.dataset.saveUrl.replace("0000-00-00", date), {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": window.csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: body.toString(),
      credentials: "same-origin",
    })
      .then((response) => response.json().then((data) => ({ response, data })))
      .then((answer) => {
        if (!answer.response.ok || !answer.data.ok) {
          return { error: answer.data.error || gettext("That could not be saved.") };
        }
        paint(answer.data.month);
        return { ok: true };
      })
      .catch(() => ({
        /* A network failure and a refusal are different things and have to read
           differently: one is "fix what you typed", the other is "nothing was
           written and it was not something you did". */
        error: gettext("The change did not reach the server, so nothing was saved."),
      }));
  }

  let announceTimer = null;

  /* The only thing on the page that says a save happened. With the button gone
   * there is nothing else, and a page that writes silently is one people press
   * twice. */
  function announce(text, isError) {
    if (!saveState) return;
    saveState.textContent = text;
    saveState.classList.toggle("is-error", Boolean(isError));
    window.clearTimeout(announceTimer);
    if (!isError && text) {
      // Long enough to be read, short enough not to sit there claiming a save
      // that has since been replaced by another one.
      announceTimer = window.setTimeout(() => { saveState.textContent = ""; }, 4000);
    }
  }

  /* ---- repainting ------------------------------------------------------ */

  function dash(node) {
    node.textContent = "";
    const empty = document.createElement("span");
    empty.className = "hint";
    empty.textContent = "—";
    node.appendChild(empty);
  }

  function saldoInto(node, text, minutes) {
    node.textContent = "";
    const span = document.createElement("span");
    span.className = "saldo";
    span.classList.toggle("saldo--short", minutes < 0);
    span.classList.toggle("saldo--over", minutes > 0);
    span.textContent = text;
    node.appendChild(span);
  }

  function pill(text) {
    const span = document.createElement("span");
    span.className = "pill pill--attention pill--small";
    span.textContent = text;
    return span;
  }

  function paintBookings(row, bookings) {
    const cell = row.querySelector("[data-bookings]");
    cell.dataset.bookings = bookings
      .map((booking) => booking.kind + " " + booking.time)
      .join(",");

    const display = row.querySelector("[data-bookings-display]");
    display.textContent = "";
    if (!bookings.length) {
      const empty = document.createElement("span");
      empty.className = "hint";
      empty.textContent = gettext("add");
      display.appendChild(empty);
    } else {
      bookings.slice(0, SHOWN).forEach((booking) => {
        const chip = document.createElement("span");
        chip.className = "booking booking--" + booking.kind;
        chip.textContent = booking.time;
        display.appendChild(chip);
      });
      if (bookings.length > SHOWN) {
        const more = document.createElement("span");
        more.className = "booking-more";
        more.textContent = "+" + (bookings.length - SHOWN);
        display.appendChild(more);
      }
    }

    /* The roster's offer goes the moment there is something to compare it
       against. Leaving it beside real bookings would be the page suggesting
       times somebody has already answered. */
    const suggestion = row.querySelector("[data-suggestion]");
    if (suggestion) suggestion.hidden = bookings.length > 0;
  }

  function paintRow(row, data) {
    paintBookings(row, data.bookings);

    const breakOut = row.querySelector("[data-break-display]");
    if (data.break_display === null) dash(breakOut);
    else breakOut.textContent = data.break_display;
    breakOut.classList.toggle("is-override", data.break_is_override);

    const cell = correctionCellOf(row);
    cell.dataset.correction = data.correction_minutes ? String(data.correction_minutes) : "";
    cell.dataset.reason = data.correction_reason || "";
    const correctionOut = row.querySelector("[data-correction-display]");
    if (data.correction_minutes) {
      correctionOut.textContent = data.correction;
      correctionOut.title = data.correction_reason;
    } else {
      dash(correctionOut);
      correctionOut.removeAttribute("title");
    }

    const actual = row.querySelector("[data-actual]");
    if (data.counted === null) {
      dash(actual);
    } else {
      actual.textContent = data.counted;
      if (data.credited) {
        const star = document.createElement("span");
        star.className = "hint";
        star.title = gettext("Credited, not worked — an absence the hours are paid for.");
        star.textContent = "*";
        actual.appendChild(star);
      }
    }

    const saldo = row.querySelector("[data-saldo-cell]");
    if (data.saldo === null) dash(saldo);
    else saldoInto(saldo, data.saldo, data.saldo_minutes);

    const running = row.querySelector("[data-running-cell]");
    if (data.running === null) dash(running);
    else saldoInto(running, data.running, data.running_minutes);

    /* Never over what somebody is typing. A repaint set off by a *different*
       row must not reach into the box the cursor is in and replace it with what
       the server last stored. */
    const note = row.querySelector("[data-note]");
    if (note && document.activeElement !== note) {
      note.value = data.note;
      note.dataset.saved = data.note;
    }

    const live = row.querySelector("[data-status-live]");
    live.textContent = "";
    if (data.is_running) live.appendChild(pill(gettext("still running")));
    if (data.differs_from_roster) {
      const flag = pill(gettext("differs"));
      flag.title = gettext("The hours entered are not the hours rostered.");
      live.appendChild(flag);
    }
  }

  function paint(month) {
    month.rows.forEach((data) => {
      const row = table.querySelector('[data-day="' + data.date + '"]');
      if (row) paintRow(row, data);
    });

    const totals = month.totals;
    const set = (selector, text) => {
      const node = document.querySelector(selector);
      if (node) node.textContent = text;
    };
    set("[data-total-break]", totals.break_display);
    set("[data-total-correction]", totals.correction);
    set("[data-total-counted]", totals.counted);
    set("[data-total-due]", totals.contracted);

    const saldoTotal = document.querySelector("[data-total-saldo]");
    saldoTotal.textContent = totals.difference;
    saldoTotal.classList.toggle("saldo--short", totals.difference_minutes < 0);
    saldoTotal.classList.toggle("saldo--over", totals.difference_minutes > 0);

    const runningTotal = document.querySelector("[data-total-running]");
    runningTotal.textContent = totals.balance;
    runningTotal.classList.toggle("saldo--short", totals.balance_minutes < 0);
    runningTotal.classList.toggle("saldo--over", totals.balance_minutes > 0);
  }

  /* ---- the bookings pop-up --------------------------------------------- */

  const bookingsModal = document.querySelector("[data-bookings-modal]");
  const correctionModal = document.querySelector("[data-correction-modal]");
  if (!bookingsModal || !correctionModal) return;

  const rowsHolder = bookingsModal.querySelector("[data-booking-rows]");
  const bookingsError = bookingsModal.querySelector("[data-bookings-error]");
  const bookingsTitle = bookingsModal.querySelector("[data-bookings-title]");
  const rosterButton = bookingsModal.querySelector("[data-booking-roster]");
  const grossOut = bookingsModal.querySelector("[data-summary-gross]");
  const requiredOut = bookingsModal.querySelector("[data-summary-required]");
  const netOut = bookingsModal.querySelector("[data-summary-net]");

  let editing = null;

  const bookingsController = window.modalController(bookingsModal, {
    onClose: () => { editing = null; },
  });

  /* One line of the pop-up: a time, and which of the two it is.
   *
   * A pair of buttons rather than a select, because the whole gesture is meant
   * to take one keystroke and a select costs two. They are labelled in words —
   * "Coming"/"Going" — and not by an arrow: an arrow is a picture whose meaning
   * has to be learnt, and this is a page somebody uses on their first morning. */
  function addLine(booking) {
    const line = document.createElement("div");
    line.className = "booking-row";
    line.setAttribute("data-booking-row", "");

    const time = document.createElement("input");
    time.type = "text";
    time.className = "booking-time";
    time.autocomplete = "off";
    time.spellcheck = false;
    time.placeholder = "08:30";
    time.setAttribute("data-time-input", "clock");
    time.setAttribute("data-booking-time", "");
    time.setAttribute("aria-label", gettext("Time"));
    time.value = booking ? booking.time : "";
    line.appendChild(time);

    const group = document.createElement("div");
    group.className = "booking-kinds";
    group.setAttribute("role", "group");
    [COMING, GOING].forEach((kind) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "booking-kind";
      button.setAttribute("data-booking-kind", kind);
      button.textContent = LABEL[kind];
      button.setAttribute("aria-pressed", String(booking ? booking.kind === kind : false));
      group.appendChild(button);
    });
    line.appendChild(group);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "booking-remove";
    remove.setAttribute("data-booking-remove", "");
    remove.textContent = "×";
    remove.setAttribute("aria-label", gettext("Remove this booking"));
    line.appendChild(remove);

    rowsHolder.appendChild(line);
    return line;
  }

  function lineKind(line) {
    const pressed = line.querySelector("[data-booking-kind][aria-pressed='true']");
    return pressed ? pressed.dataset.bookingKind : "";
  }

  function setKind(line, kind) {
    line.querySelectorAll("[data-booking-kind]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.bookingKind === kind));
    });
  }

  /* What the pop-up currently says, blank lines dropped.
   *
   * A line with a time and no direction is *not* dropped: it is the one thing
   * somebody can leave half-done, and silently discarding it would lose a
   * booking they can see on the screen. It comes back with an empty kind and is
   * refused by name below. */
  function readModal() {
    const rows = [];
    rowsHolder.querySelectorAll("[data-booking-row]").forEach((line) => {
      const time = line.querySelector("[data-booking-time]").value.trim();
      const kind = lineKind(line);
      if (!time && !kind) return;
      rows.push({ time: time, kind: kind });
    });
    return rows;
  }

  /* Fold a booking list into `{gross, taken}`, or null when it does not pair.
   *
   * `gross` is the time at work — the stretches, with the gaps between them
   * excluded. `taken` is those gaps: the break the person demonstrably took by
   * clocking out and back in, which is what stops the rules deducting the
   * statutory thirty on top of a thirty they had already taken.
   *
   * Null when the list does not pair. A day that cannot be read has no total,
   * and showing 0:00 for one would be a confident wrong answer where a blank is
   * the honest one.
   *
   * A trailing coming with no going contributes nothing, which is the answer
   * WorkSegment.minutes gives on the server and for the same reason: a figure
   * that changes on every refresh is not one anybody can sign off. */
  function totalsOf(bookings) {
    const blocks = [];
    const gaps = [];
    let openAt = null;
    let lastEnd = null;
    for (let i = 0; i < bookings.length; i += 1) {
      const minutes = hours.parse(bookings[i].time, true);
      if (minutes === null) return null;
      if (bookings[i].kind === COMING) {
        if (openAt !== null) return null;
        if (lastEnd !== null) {
          // A gap that comes out negative crossed midnight, the same rule the
          // stretches themselves follow.
          let gap = minutes - lastEnd;
          if (gap < 0) gap += 24 * 60;
          gaps.push(gap);
        }
        openAt = minutes;
        continue;
      }
      if (openAt === null) return null;
      blocks.push(
        minutes <= openAt ? minutes + 24 * 60 - openAt : minutes - openAt,
      );
      lastEnd = minutes;
      openAt = null;
    }
    return {
      blocks: blocks,
      gaps: gaps,
      gross: blocks.reduce((sum, block) => sum + block, 0),
    };
  }

  /* The same refusals as apps/timesheets/bookings.py, said here first.
   *
   * Not instead of the server's — the server's is the one that binds, and this
   * one exists because "before saving" is the only time a fix is cheap. */
  function problem(rows) {
    let openAt = null;
    for (let i = 0; i < rows.length; i += 1) {
      const row = rows[i];
      if (!row.kind) {
        return gettext("Every booking has to say whether it is a coming or a going.");
      }
      if (!row.time) {
        return gettext("There is a booking with no time on it.");
      }
      const minutes = hours.parse(row.time, true);
      if (minutes === null) {
        return gettext("That is not a time this app can read. Try 8:30, 8,5 or 830.");
      }
      if (row.kind === COMING) {
        if (openAt !== null) {
          return gettext("There are two comings in a row with no going between them.");
        }
        openAt = minutes;
        continue;
      }
      if (openAt === null) {
        return gettext("There is a going with no coming before it. A day starts with a coming.");
      }
      if (minutes === openAt) {
        return gettext("A coming and a going at the same moment is a stretch with no length.");
      }
      openAt = null;
    }
    return "";
  }

  /* Redraw the summary. **It does not complain.**
   *
   * A half-typed day is not a wrong day: entering 09:30 as a coming means
   * passing through a moment where the line has a time and no direction, and
   * telling somebody off for that while their finger is still on the keyboard
   * is the app shouting at them for typing. The refusals live in `problem` and
   * are shown when somebody tries to *leave* with them — see the accept
   * handler, which is also where the server would refuse.
   *
   * The complaint is still computed here, because a day that does not pair has
   * no total either, and "—" is the honest answer where a confident 0:00 is
   * not. */
  function refreshModal() {
    const rows = readModal();
    const complaint = problem(rows);

    const totals = complaint ? null : totalsOf(rows);
    if (totals === null) {
      grossOut.textContent = "—";
      requiredOut.textContent = "—";
      netOut.textContent = "—";
      return;
    }
    const required = hours.requiredBreak(totals.blocks, totals.gaps, rules);
    grossOut.textContent = totals.gross ? hours.hhmm(totals.gross) : "—";
    requiredOut.textContent = totals.gross ? hours.hhmm(required) : "—";
    netOut.textContent = totals.gross
      ? hours.hhmm(Math.max(0, totals.gross - required)) : "—";
  }

  function openBookings(row) {
    editing = row;
    bookingsTitle.textContent = row.dataset.label || "";
    rowsHolder.textContent = "";
    const existing = readBookings(row);
    existing.forEach(addLine);
    /* An empty day opens with one line already there and the cursor in it. A
       pop-up that opens empty asks somebody to press "Another booking" before
       they can do the thing they opened it for. */
    if (!existing.length) addLine(null);

    rosterButton.hidden = suggested(row).length === 0;
    bookingsError.hidden = true;
    refreshModal();
    bookingsController.open();
    const first = rowsHolder.querySelector("[data-booking-time]");
    if (first) first.focus();
  }

  rowsHolder.addEventListener("click", (event) => {
    const kindButton = event.target.closest("[data-booking-kind]");
    if (kindButton) {
      setKind(kindButton.closest("[data-booking-row]"), kindButton.dataset.bookingKind);
      bookingsError.hidden = true;
      refreshModal();
      return;
    }
    const removeButton = event.target.closest("[data-booking-remove]");
    if (removeButton) {
      removeButton.closest("[data-booking-row]").remove();
      bookingsError.hidden = true;
      refreshModal();
    }
  });

  /* The keyboard half of the gesture: type a time, press the first letter of
   * either word, and the line is entered and the next one is waiting.
   *
   * Enter does the same without choosing a direction — it takes whichever one
   * the line does not have yet, which for an empty list is a coming and after a
   * coming is a going. That is the ordinary rhythm of a day, so the common case
   * needs no letter at all. */
  rowsHolder.addEventListener("keydown", (event) => {
    const input = event.target.closest("[data-booking-time]");
    if (!input) return;
    const line = input.closest("[data-booking-row]");

    const letter = KEY[event.key.toLowerCase()];
    if (letter && input.value.trim()) {
      event.preventDefault();
      setKind(line, letter);
      advance(line);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (!input.value.trim()) return;
      if (!lineKind(line)) setKind(line, nextKind(line));
      advance(line);
    }
  });

  function nextKind(line) {
    let kind = COMING;
    const all = Array.from(rowsHolder.querySelectorAll("[data-booking-row]"));
    for (let i = 0; i < all.length && all[i] !== line; i += 1) {
      if (lineKind(all[i]) === COMING) kind = GOING;
      else if (lineKind(all[i]) === GOING) kind = COMING;
    }
    return kind;
  }

  function advance(line) {
    refreshModal();
    let next = line.nextElementSibling;
    if (!next) next = addLine(null);
    const box = next.querySelector("[data-booking-time]");
    if (box) box.focus();
  }

  bookingsModal.querySelector("[data-booking-add]").addEventListener("click", () => {
    const line = addLine(null);
    line.querySelector("[data-booking-time]").focus();
  });

  rosterButton.addEventListener("click", () => {
    if (!editing) return;
    rowsHolder.textContent = "";
    suggested(editing).forEach(addLine);
    refreshModal();
  });

  bookingsModal.addEventListener("input", () => {
    // A complaint goes as soon as somebody starts fixing it. One left on the
    // screen while the correction is being typed reads as the app not noticing.
    bookingsError.hidden = true;
    refreshModal();
  });
  bookingsModal.addEventListener("focusout", () => window.setTimeout(refreshModal, 0));

  function takeBookings(row, bookings) {
    return save(row, { bookings: bookings });
  }

  function finish(controller, errorBox) {
    return (result) => {
      if (result.error) {
        // Kept inside the pop-up, which stays open: the values that caused the
        // refusal are still on the screen there, and that is the only place the
        // message is any use.
        errorBox.textContent = result.error;
        errorBox.hidden = false;
        return;
      }
      announce(gettext("Saved."));
      controller.close();
    };
  }

  bookingsModal.querySelector("[data-bookings-accept]").addEventListener("click", () => {
    const rows = readModal();
    const complaint = problem(rows);
    if (complaint) {
      bookingsError.textContent = complaint;
      bookingsError.hidden = false;
      return;
    }
    /* Normalised on the way out, so what is stored is what the cell will show —
       "830" becomes 08:30 here rather than being interpreted somewhere nobody
       can see the interpretation. */
    const bookings = rows.map((row) => ({
      kind: row.kind,
      time: hours.clockOfDay(hours.parse(row.time, true)),
    }));
    takeBookings(editing, bookings).then(finish(bookingsController, bookingsError));
  });

  bookingsModal.querySelector("[data-bookings-clear]").addEventListener("click", () => {
    takeBookings(editing, []).then(finish(bookingsController, bookingsError));
  });

  bookingsModal.querySelector("[data-bookings-cancel]").addEventListener("click", () =>
    bookingsController.close());

  /* ---- the correction pop-up ------------------------------------------- */

  const correctionController = window.modalController(correctionModal);
  const correctionTitle = correctionModal.querySelector("[data-correction-title]");
  const amountBox = correctionModal.querySelector("[data-correction-amount]");
  const whyBox = correctionModal.querySelector("[data-correction-why]");
  const correctionError = correctionModal.querySelector("[data-correction-error]");
  let correcting = null;

  /* Bare digits are minutes here, which is the one place besides the break box
   * where they are not hours — the label says minutes and nobody has ever meant
   * thirty hours by typing 30 into a box marked "correction". Anything with a
   * separator is read as a duration, so 0:30 works too. The sign is kept,
   * because taking time off a day is the correction that matters most and the
   * alternative is a doctored booking. SignedMinutesField reads it the same way
   * on the server. */
  function parseCorrection(raw) {
    let text = String(raw || "").trim();
    if (!text) return 0;
    let sign = 1;
    if (text.charAt(0) === "-" || text.charAt(0) === "−" || text.charAt(0) === "–") {
      sign = -1;
      text = text.slice(1).trim();
    } else if (text.charAt(0) === "+") {
      text = text.slice(1).trim();
    }
    if (!text) return null;
    const minutes = /^\d{1,4}$/.test(text) ? parseInt(text, 10) : hours.parse(text, false);
    if (minutes === null) return null;
    return sign * minutes;
  }

  function openCorrection(row) {
    correcting = row;
    correctionTitle.textContent = row.dataset.label || "";
    const cell = correctionCellOf(row);
    amountBox.value = cell.dataset.correction || "";
    whyBox.value = cell.dataset.reason || "";
    correctionError.hidden = true;
    correctionController.open();
    amountBox.focus();
  }

  function takeCorrection(row, minutes, why) {
    return save(row, {
      correction: minutes ? String(minutes) : "",
      why: minutes ? why : "",
    });
  }

  correctionModal.querySelector("[data-correction-accept]").addEventListener("click", () => {
    const minutes = parseCorrection(amountBox.value);
    if (minutes === null) {
      correctionError.textContent = gettext(
        "That is not a length this app can read. Try 30, 0:30 or -15."
      );
      correctionError.hidden = false;
      return;
    }
    if (minutes && !whyBox.value.trim()) {
      correctionError.textContent = gettext(
        "Say why the day was corrected. A correction nobody can account for is the one entry on a timesheet that cannot be defended."
      );
      correctionError.hidden = false;
      whyBox.focus();
      return;
    }
    takeCorrection(correcting, minutes, whyBox.value.trim())
      .then(finish(correctionController, correctionError));
  });

  correctionModal.querySelector("[data-correction-clear]").addEventListener("click", () => {
    takeCorrection(correcting, 0, "").then(finish(correctionController, correctionError));
  });

  correctionModal.querySelector("[data-correction-cancel]").addEventListener("click", () =>
    correctionController.close());

  /* ---- the status pop-up ----------------------------------------------- */

  /* The one pop-up on this page that is a real form. It posts and the page
   * reloads, where the other two save through fetch and repaint — a status
   * changes what the whole month is worth, and a reload is both simpler and
   * certainly right. Everything below is only *opening* it on the row that was
   * clicked; the writing is Django's. */
  const statusModal = document.querySelector("[data-status-modal]");
  if (statusModal) {
    const statusForm = statusModal.querySelector("[data-status-form]");
    const statusTitle = statusModal.querySelector("[data-status-title]");
    const kindBox = statusModal.querySelector("[data-status-kind]");
    const specialBox = statusModal.querySelector("[data-status-special]");
    const specialField = statusModal.querySelector("[data-status-special-field]");
    const halfBox = statusModal.querySelector("[data-status-half]");
    const noteBox = statusModal.querySelector("[data-status-note]");
    const noteField = statusModal.querySelector("[data-status-note-field]");
    const halfField = statusModal.querySelector("[data-status-half-field]");
    const lockedNote = statusModal.querySelector("[data-status-locked]");
    const fields = statusModal.querySelector("[data-status-fields]");
    const accept = statusModal.querySelector("[data-status-accept]");

    const statusController = window.modalController(statusModal);

    /* Which boxes make sense for the chosen status.
     *
     * "Which" only for special leave, because it is the one that has to say
     * which entitlement it comes out of. No note at all for sickness: a sick
     * absence records that somebody was ill and never why, and a free-text box
     * beside it is where a diagnosis ends up. Nothing at all for "no status",
     * which is a removal and has nothing to describe. */
    function syncFields() {
      const kind = kindBox.value;
      specialField.hidden = kind !== "special";
      noteField.hidden = kind === "sick" || kind === "";
      halfField.hidden = kind === "";
      if (noteField.hidden) noteBox.value = "";
      if (specialField.hidden) specialBox.value = "";
      if (halfField.hidden) halfBox.checked = false;
    }

    function openStatus(row) {
      const cell = row.querySelector("[data-status-kind]");
      const editable = cell.dataset.statusEditable === "1";

      statusTitle.textContent = row.dataset.label || "";
      statusForm.action = table.dataset.statusUrl.replace("0000-00-00", row.dataset.day);
      kindBox.value = cell.dataset.statusKind || "";
      specialBox.value = cell.dataset.statusSpecial || "";
      halfBox.checked = cell.dataset.statusHalf === "1";
      noteBox.value = cell.dataset.statusNote || "";
      syncFields();

      /* A closure and a multi-day absence are read-only here, and the pop-up
         says which rather than offering controls that would refuse. `hidden`
         is safe on these: there is nothing inside them to validate, so the
         unfocusable-control trap that the roster's card holder avoids does not
         apply — the submit is gone with them. */
      lockedNote.hidden = editable;
      fields.hidden = !editable;
      specialField.hidden = !editable || specialField.hidden;
      halfField.hidden = !editable || halfField.hidden;
      noteField.hidden = !editable || noteField.hidden;
      accept.hidden = !editable;

      statusController.open();
      if (editable) kindBox.focus();
    }

    kindBox.addEventListener("change", syncFields);
    statusModal.querySelector("[data-status-cancel]").addEventListener("click", () =>
      statusController.close());

    table.addEventListener("click", (event) => {
      const opener = event.target.closest("[data-status-open]");
      if (opener) openStatus(opener.closest("[data-day]"));
    });
  }

  /* ---- the table ------------------------------------------------------- */

  table.addEventListener("click", (event) => {
    /* Two states in which a row holds no hours: locked, and not yet happened.
       Their buttons are `disabled` so this never fires for one, and the guard is
       here all the same — the server decides, and this file must not be the
       thing that does. It is checked per *action* rather than per row, because a
       future row still opens its status pop-up: booking leave in advance is
       exactly what a future row is for. */
    const row = event.target.closest("[data-day]");
    const noHours = row && row.classList.contains("no-hours");

    const take = event.target.closest("[data-suggestion-take]");
    if (noHours && (take
        || event.target.closest("[data-bookings-open]")
        || event.target.closest("[data-correction-open]"))) {
      return;
    }

    if (take) {
      /* The checkmark: the rostered times, taken and written in one press. It is
         the one gesture on the page that needs no pop-up at all, which is the
         whole reason it is a checkmark and not a menu. */
      const row = take.closest("[data-day]");
      takeBookings(row, suggested(row)).then((result) => {
        announce(result.error || gettext("Saved."), Boolean(result.error));
      });
      return;
    }
    const bookings = event.target.closest("[data-bookings-open]");
    if (bookings) {
      openBookings(bookings.closest("[data-day]"));
      return;
    }
    const correction = event.target.closest("[data-correction-open]");
    if (correction) {
      openCorrection(correction.closest("[data-day]"));
    }
  });

  /* The comment: written when the box is left, and only if it changed.
   *
   * `focusout` rather than `change`, so a box somebody typed in and then clicked
   * out of is caught either way; and the comparison against what is stored is
   * what stops a save on every tab through the column. */
  table.addEventListener("focusout", (event) => {
    const note = event.target.closest("[data-note]");
    if (!note || note.readOnly) return;
    const stored = note.dataset.saved !== undefined ? note.dataset.saved : note.defaultValue;
    if (note.value === stored) return;

    const row = note.closest("[data-day]");
    save(row, { note: note.value }).then((result) => {
      if (result.error) {
        announce(result.error, true);
        return;
      }
      note.dataset.saved = note.value;
      announce(gettext("Saved."));
    });
  });

  /* Enter in the comment box means "I am done with this one", not "submit
   * something" — there is nothing to submit. Blurring writes it through the
   * handler above and hands the keyboard back to the page. */
  table.addEventListener("keydown", (event) => {
    const note = event.target.closest("[data-note]");
    if (note && event.key === "Enter") {
      event.preventDefault();
      note.blur();
    }
  });

  /* ---- the month picker ------------------------------------------------ */

  /* Submits itself, and the button beside it goes away. Left as it is, choosing
   * a month does nothing until somebody notices the second control — and a
   * select that appears to do nothing is a select people press twice. The button
   * is removed rather than never rendered, because without script it is the only
   * way the picker works at all. */
  const picker = document.querySelector("[data-month-picker]");
  if (picker) {
    const go = document.querySelector("[data-month-go]");
    if (go) go.hidden = true;
    picker.addEventListener("change", () => {
      if (picker.form.requestSubmit) picker.form.requestSubmit();
      else picker.form.submit();
    });
  }
})();
