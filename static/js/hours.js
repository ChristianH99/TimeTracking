/* window.ttHours — reading and writing durations in the browser.
 *
 * Four small functions, shared by the day form and anything else that has to
 * answer while somebody is typing. They exist so that no page divides by 60 in
 * its own event handler: a page that does gets 7.5 where the server says 7:30,
 * and the two figures on one screen disagreeing is the report that costs a day
 * to chase.
 *
 * ---- the one rule repeated from Python ----
 *
 * `requiredBreak` is the same formula as OrgSettings.required_break in
 * apps/organisation/models.py, and it is the only piece of logic in this app
 * written twice in two languages. It is here because the alternative — asking
 * the server on every keystroke — is a request per character on a form whose
 * whole point is that it answers immediately.
 *
 * What bounds the cost is that only the *rule* is repeated, and it is one line:
 *
 *     required = max over rules of  min(break, max(0, gross - over))
 *
 * The docstring on the Python side explains why it is that and not the obvious
 * "worked more than six hours, so take thirty minutes" — which gives a day of
 * 6h05 a full thirty-minute break and is wrong in the direction that underpays
 * one. apps/timesheets/tests.py holds both implementations to the same answers
 * for the same days. If they ever drift it will be about that one line.
 */
(function () {
  /* A unit typed after the number — "8:30 h", "17 Uhr". Stripped rather than
     refused, because it is what a person writes. */
  const UNIT = /\s*(?:h|hrs?|std\.?|stunden?|uhr|min\.?|minuten?)\s*$/i;
  const CLOCK = /^(\d{1,2})\s*:\s*(\d{1,2})(?::\d{1,2})?$/;
  const DECIMAL = /^(\d{1,3})\s*[.,]\s*(\d{1,3})$/;
  const DIGITS = /^(\d{1,4})$/;

  /* Every way somebody types a time, as minutes. The twin of
     apps/timesheets/timeparse.py, and the module docstring there is the long
     version of why this is what it is.

         8:30   08:30   8.30      a colon, or the German "8.30 Uhr"
         8,5    8.5     8,50      decimal hours
         0830   830     8         digits alone: HHMM, HMM, or whole hours

     `preferClock` is the context that settles the one real ambiguity: two
     digits after a separator are decimal hours to a payroll clerk and a clock
     time to everybody else, so a time-of-day box reads "8.30" as half past
     eight and a duration box reads it as 8 h 18. One digit is decimal either
     way, and the two readings converge for the common cases — 8.5 and 8.30 are
     both 08:30 on a clock.

     Anything unreadable is null, which every caller treats as "not answered
     yet" rather than as zero: a half-typed time must not make the running total
     jump to a confident wrong number. */
  function parse(value, preferClock) {
    const text = String(value || "").trim().replace(/ /g, " ").replace(UNIT, "").trim();
    if (!text) return null;

    let hours = null;
    let minutes = 0;
    let match = CLOCK.exec(text);

    if (match) {
      hours = parseInt(match[1], 10);
      minutes = parseInt(match[2], 10);
    } else if ((match = DECIMAL.exec(text))) {
      const whole = parseInt(match[1], 10);
      const fraction = match[2];
      if (preferClock && fraction.length === 2 && parseInt(fraction, 10) < 60) {
        hours = whole;
        minutes = parseInt(fraction, 10);
      } else {
        // Rounded, not truncated: 8.1 hours is 486 minutes and the float gets
        // there via 485.99999999999994, which floors to 485 and loses a minute
        // of somebody's day every single time, in one direction.
        return Math.round((whole + parseFloat("0." + fraction)) * 60);
      }
    } else if ((match = DIGITS.exec(text))) {
      const digits = match[1];
      if (digits.length <= 2) {
        hours = parseInt(digits, 10);
      } else {
        hours = parseInt(digits.slice(0, -2), 10);
        minutes = parseInt(digits.slice(-2), 10);
      }
    } else {
      return null;
    }

    if (minutes >= 60) return null;
    return hours * 60 + minutes;
  }

  /* Length of a start-end pair, treating an end at or before the start as
     crossing midnight. The same rule as minutes_between() in
     apps/roster/models.py: a shift from 22:00 to 06:00 is eight hours, not
     minus sixteen. */
  function span(start, end) {
    const from = parse(start, true);
    const to = parse(end, true);
    if (from === null || to === null) return null;
    return to <= from ? to + 24 * 60 - from : to - from;
  }

  /* 455 -> "7:35". Negative durations keep the sign outside the colon, because
     a naive divmod gives "-1:-15" for a small shortfall. */
  function clock(minutes) {
    const total = Math.round(minutes);
    const sign = total < 0 ? "-" : "";
    const absolute = Math.abs(total);
    const hours = Math.floor(absolute / 60);
    const rest = absolute % 60;
    return sign + hours + ":" + String(rest).padStart(2, "0");
  }

  /* 510 -> "08:30". A *time of day*, which is a different thing from a duration
     and is written differently: the hour is padded to two digits and there is
     no sign, because there is no such clock time as minus half past eight.

     Kept apart from `clock` above rather than folded into it with a flag,
     because the two are wrong for each other in opposite directions. Padding a
     duration gives "07:35 h" for seven and a half hours worked, which reads as
     a time of day; not padding a clock time gives "8:30", which is not how a
     German clock is written and is not what apps/timesheets/timeparse.py
     normalises to on the server. The two implementations have to agree, and
     they only agree if each has one job. */
  function clockOfDay(minutes) {
    const total = ((Math.round(minutes) % (24 * 60)) + 24 * 60) % (24 * 60);
    const hours = Math.floor(total / 60);
    const rest = total % 60;
    return String(hours).padStart(2, "0") + ":" + String(rest).padStart(2, "0");
  }

  /* See the header. `rules` is [{over, break}, …] as the page's json_script
     supplied it; an empty list means no break is required, which is what an
     organisation that deleted every rule has asked for. */
  function requiredBreak(grossMinutes, rules) {
    const gross = Math.max(0, grossMinutes || 0);
    let required = 0;
    (rules || []).forEach((rule) => {
      const needed = Math.min(rule.break, Math.max(0, gross - rule.over));
      if (needed > required) required = needed;
    });
    return required;
  }

  window.ttHours = {
    parse: parse,
    span: span,
    clock: clock,
    clockOfDay: clockOfDay,
    requiredBreak: requiredBreak,
  };
})();
