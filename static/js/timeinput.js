/* Every box that holds a time, normalised the moment you leave it.
 *
 * This is the half that makes the flexible parsing safe to do at all. Two
 * digits after a separator are genuinely ambiguous in German — "8,30" is
 * decimal hours to a payroll clerk and half past eight to everybody else — and
 * no rule settles that for certain. So the app does not settle it silently: it
 * shows what it read, in the box, before the form is ever submitted. A parser
 * that guesses is a problem; one that guesses and shows its guess is just a
 * parser.
 *
 * The parsing itself is window.ttHours.parse (static/js/hours.js), which must
 * therefore load first — config/tests.py walks every template to check that it
 * does. Deliberately *not* a second implementation: this file decides when to
 * normalise and what to say when it cannot, and nothing else.
 */
(function () {
  const MINUTES_PER_DAY = 24 * 60;
  if (!window.ttHours) return;
  const parse = window.ttHours.parse;
  const asClock = window.ttHours.clockOfDay;

  /* A duration written back as hours, in the page's decimal separator. A
     contract is written in hours, and normalising 7.75 to "07:45" would make
     somebody think they had typed a time of day. */
  function asHours(minutes) {
    const value = Math.round((minutes / 60) * 100) / 100;
    const text = String(value);
    return document.documentElement.lang === "en" ? text : text.replace(".", ",");
  }

  /* Minutes are minutes here and nothing else — the box says so. This is the
     one field where bare digits are not hours, and apps/timesheets/fields.py
     makes the same exception for the same reason: nobody has ever meant
     forty-five hours by typing 45 into a box marked "break". */
  function parseMinutes(raw) {
    const text = String(raw || "").trim();
    if (/^\d{1,4}$/.test(text)) return parseInt(text, 10);
    return parse(text, false);
  }

  function normalise(input) {
    const kind = input.dataset.timeInput;
    const raw = input.value;
    if (!raw.trim()) {
      input.setCustomValidity("");
      input.classList.remove("is-unreadable");
      return;
    }

    const minutes =
      kind === "minutes" ? parseMinutes(raw) : parse(raw, kind === "clock");
    const valid =
      minutes !== null &&
      minutes >= 0 &&
      (kind !== "clock" || minutes <= MINUTES_PER_DAY);

    if (!valid) {
      // Left exactly as typed. Blanking it, or "correcting" it to something,
      // would leave the message above the box talking about a value the box no
      // longer contains — which is the one thing a validation message must
      // never do. setCustomValidity also stops the form submitting, so the
      // server never has to be the first to notice.
      input.classList.add("is-unreadable");
      input.setCustomValidity(
        gettext("That is not a time this app can read. Try 8:30, 8,5 or 830.")
      );
      return;
    }

    input.classList.remove("is-unreadable");
    input.setCustomValidity("");
    if (kind === "clock") {
      input.value = asClock(minutes % MINUTES_PER_DAY);
    } else if (kind === "minutes") {
      input.value = String(minutes);
    } else {
      input.value = asHours(minutes);
    }
  }

  // Delegated from the document, so a row added a moment ago by simple_rows.js
  // or the roster planner answers exactly like one the server rendered.
  document.addEventListener("focusout", (event) => {
    const input = event.target.closest("[data-time-input]");
    if (input) normalise(input);
  });

  // Clear the complaint as soon as somebody starts fixing it. Leaving it until
  // the next blur means the box stays red while they type the correction, which
  // reads as the app not noticing.
  document.addEventListener("input", (event) => {
    const input = event.target.closest("[data-time-input]");
    if (!input) return;
    input.setCustomValidity("");
    input.classList.remove("is-unreadable");
  });

  // Exposed so the day form and the roster can read what a box means without
  // parsing it a second time.
  window.ttTimeInput = { hours: asHours, minutes: parseMinutes };
})();
