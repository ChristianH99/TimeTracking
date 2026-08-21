/* The contract form: the sign-in name, and what the seven hour boxes come to.
 *
 * Two jobs, both of them "answer while somebody types".
 *
 * The relationship between which days have hours in them and how many days of
 * leave a year is the one thing on this page that is not obvious, and it is the
 * question every part-time employee asks about their entitlement. Showing it
 * only after the save is showing it too late to be any use.
 *
 * Reads window.ttHours (static/js/hours.js), which must load first.
 */
(function () {
  const form = document.querySelector("[data-employee-form]");
  if (!form || !window.ttHours) return;

  // ---- the sign-in name -------------------------------------------------
  //
  // Filled from the two name boxes, and **only while it is still untouched**.
  // A directory is the authority on what an account is called: a house whose
  // convention is `aberger` has to be able to say so, and a suggestion that
  // overwrote a corrected value on the next keystroke would make that
  // impossible. Once somebody has typed in the box, or the server sent one
  // back, this stops for good.

  const usernameBox = form.querySelector("[data-username-target]");
  const firstBox = form.querySelector("[name='first_name']");
  const lastBox = form.querySelector("[name='last_name']");

  if (usernameBox && firstBox && lastBox) {
    let suggesting = !usernameBox.value.trim();
    usernameBox.addEventListener("input", () => {
      suggesting = false;
    });

    const suggest = () => {
      if (!suggesting) return;
      // The same transliteration as Employee.suggest_username: ä becomes ae
      // rather than being dropped, because `mller` is nobody's account name.
      const folded = (firstBox.value + "." + lastBox.value)
        .toLowerCase()
        .replace(/ä/g, "ae")
        .replace(/ö/g, "oe")
        .replace(/ü/g, "ue")
        .replace(/ß/g, "ss")
        .normalize("NFKD")
        .replace(/[̀-ͯ]/g, "")
        .replace(/[^a-z0-9._-]+/g, "");
      usernameBox.value = folded.replace(/^\.+|\.+$/g, "");
    };

    firstBox.addEventListener("input", suggest);
    lastBox.addEventListener("input", suggest);
  }

  // ---- what the contract comes to ---------------------------------------
  //
  // A **preview and never the stored value** — Employee.annual_leave_days on
  // the server is what is saved, and it applies an override this panel
  // deliberately ignores. The rule repeated here is three lines:
  //
  //     leave = round(full_time_leave * working_days / full_time_days)
  //
  // and the rounding mode comes from the page rather than being assumed,
  // because "always up" and "to the nearest half" give different answers for
  // exactly the fractions somebody is most likely to be looking at.

  const summary = form.querySelector("[data-contract-summary]");
  const rules = window.pageData ? window.pageData("leave-rules") : null;
  if (!summary || !rules) return;

  const hoursOut = summary.querySelector("[data-summary-hours]");
  const daysOut = summary.querySelector("[data-summary-days]");
  const leaveOut = summary.querySelector("[data-summary-leave]");

  // Text boxes, not number inputs: the hour fields accept "8", "8:30", "8,5"
  // and "830" alike (apps/timesheets/timeparse.py), which a number input would
  // refuse outright.
  const boxes = Array.from(
    form.querySelectorAll("[data-week-fields] [data-time-input]")
  );

  function round(value) {
    if (rules.rounding === "exact") return Math.round(value * 10) / 10;
    if (rules.rounding === "half") return Math.round(value * 2) / 2;
    return Math.ceil(value - 1e-9); // "up", with a nudge so 18.0 is not 19
  }

  function refresh() {
    let minutes = 0;
    let days = 0;
    boxes.forEach((box) => {
      const value = window.ttHours.parse(box.value, false);
      if (value === null || value <= 0) return;
      minutes += value;
      days += 1;
    });

    hoursOut.textContent = minutes ? window.ttHours.clock(minutes) : "—";
    daysOut.textContent = days ? String(days) : "—";

    if (!days || !rules.full_time_days) {
      leaveOut.textContent = "—";
      return;
    }
    leaveOut.textContent = String(
      round((rules.full_time_leave * days) / rules.full_time_days)
    );
  }

  form.addEventListener("input", refresh);
  refresh();
})();
