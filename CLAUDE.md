# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project

Roster and time tracking for a small business that schedules its staff — a
kindergarten, a school, a practice. A manager plans the week, the people who
worked it confirm what they actually did, and the app keeps the leave and
sickness accounting behind that. Django 6 (Python 3.13, `uv`), server-rendered,
running as one container on a Synology NAS behind that NAS's reverse proxy and
authenticating over OIDC.

**The shell is a house style, not this app's invention.** The sidebar and topbar
markup, the closed design-token scales in `static/css/main.css`, the `nav.py`
registry, the shape of `apps/accounts` and the whole deployment pipeline are a
pattern reused deliberately, so that anything built to it is recognisable as the
same product. Treat them as settled: a change to any of them is a change to the
house style rather than a change to this app, and it wants a reason of that size.

**The topbar is the app's; the page's head is the page's.** The bar carries only
what is true wherever somebody is standing — the app's name, Start and Stop, the
language menu. The two figures up there tick on their own, from a timer in
`shell.js` that adds real elapsed time to what the server rendered. It ticks
*forward from that figure* rather than reading `new Date()`, because the
browser's clock is the wrong one for anybody whose `Employee.time_zone` is
filled in — which is the only case that field exists for. A page's title, subtitle and buttons are `{% block page_title %}`,
`page_subtitle` and `page_actions`, rendered by `base.html` in `.page-head` at
the top of `<main>`. That is what made room for the clock: it is a fact about the
person and not about the page, and it used to be buried on the timesheet, so
answering "am I at work?" needed a navigation first.

German is the default language and the only one the staff are expected to read;
English is offered from the topbar globe.

**Read `docs/COMPLIANCE.md` before changing anything about breaks, leave or the
recording of hours.** It lists the German statutes this app runs into, what it
does about each, and — the useful column — what it does not. Several rules below
are load-bearing for a legal reason rather than a design one, and that file is
where the reason is written down.

## Stack

- Django 6.1, Python 3.13, `uv` (`pyproject.toml` / `uv.lock`)
- SQLite in WAL mode, one file under `DATA_DIR`
- `mozilla-django-oidc` for the Synology SSO handshake
- WhiteNoise (manifest storage), gunicorn
- No JS framework — vanilla JS, one file per page under `static/js/`
- **No dependency ships the German public holidays.** `apps/absences/bankholidays.py`
  computes them. See "Standing decisions".

## Getting a working checkout

```
uv sync
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput   # prerequisite of pytest, see below
uv run python manage.py seed_demo                 # DEBUG only
uv run python manage.py runserver
```

`seed_demo` creates **`anna` / `ben` / `admin`, password `timetracking-dev-pass`**
and five contracts chosen to cover the cases that *differ* rather than to look
plausible. Read the docstring before replacing them: a seed where everybody
works Monday to Friday hides every rule this app has. In particular Dilan works
half of Anna's hours across the same five days and is entitled to **exactly the
same leave** — that is the pro-rata-by-days rule, and it is the thing that looks
like a bug until you know why.

To see the app working: open the roster, drag a card to another day, press Save,
then open that person's timesheet — the month — and press the ✓ beside the
rostered times on that row. There is no Save on the timesheet: the ✓ writes the
day and the break appears by itself.

Since the contract became a history, a fixture or a seeder creates an employee
and then calls `employee.set_hours([...], valid_from=...)`. A period dated today
gives every past date no hours at all, which fails a whole suite for a reason
that has nothing to do with what it tests — `conftest.py` dates them well back.

**Never delete `db.sqlite3`.** It is gitignored, which means it is not a build
artefact — it is the only copy of whatever hours somebody has entered. To verify
a seeder or a migration, point `TIMETRACK_DATA_DIR` at a temporary directory or
let `pytest` build its own database.

## Commands

```
uv run pytest                                     # ~610 tests, ~220 s

uv run python manage.py close_leave_year 2025 --notice 2025-11-15
uv run python manage.py close_leave_year 2025 --expire

uv run python manage.py makemessages -l de --no-obsolete --no-wrap
uv run python manage.py makemessages -d djangojs -l de --no-obsolete --no-wrap
uv run python tools/apply_translations.py
uv run python manage.py compilemessages -l de --ignore=.venv
```

There are **two** catalogues and the second is easy to forget: `djangojs.po`
holds the strings the browser says for itself, which are the ones people see
most often because they are what a typo produces. `apply_translations.py` writes
both, and `config/tests.py` checks they have not been written over each other —
which is not hypothetical, it happened.

**The German catalogue is generated from a table, not hand-edited.**
`tools/translations_de.py` and `tools/translations_de_pages.py` hold
`msgid -> msgstr`; `tools/apply_translations.py` writes the `.po`. It exists
because of two failures that hand-editing a `.po` on Windows reliably produces:
gettext emits a wrapped `#:` reference line that makes
`msgfmt` refuse the whole file and write **no `.mo` at all** — so the app carries
on serving the previous catalogue and a session's translations look compiled and
simply are not there — and a long `msgstr` broken across continuation lines is
valid `.po` that the completeness check reads as *empty*. Writing the file
programmatically means neither has anywhere to occur. A new string is added to
one of the two tables, not to the `.po`.

GNU gettext is not on PATH on the development machine; it ships with Git:
`$env:PATH = "C:\Program Files\Git\usr\bin;$env:PATH"`.

`collectstatic` is a **prerequisite of the test suite**, not only of a
deployment: `STORAGES` uses WhiteNoise's manifest storage in every mode, so
`{% static %}` resolves through the gitignored `staticfiles/staticfiles.json`
and a checkout that has never run it fails most of the suite with "Missing
staticfiles manifest entry".

## Verifying a change

```
uv run python manage.py runserver 8100 --noreload
```

**`--noreload` means templates are cached for the life of the process.** A
template edit changes nothing until the server is restarted, and the symptom is
a page rendering the old markup while the file on disk is plainly correct —
which reads as a browser cache problem and is not one. Restart after every
template edit, or drop `--noreload` when catalogues are not what you are working
on (translations are loaded once per process, which is what `--noreload` is for).

Static files are served through the *manifest* storage even in development, so
`main.css` and every `.js` file must be re-`collectstatic`ed after an edit.

## The rules that are load-bearing

Each of these is here because breaking it produces a page that still renders.

### Inherited from the family, and still true here

- **Nothing on a page may be inline.** No inline `<script>`, no `style="…"`, no
  `onclick=`. The CSP is `script-src 'self'` with no nonce (`config/csp.py`),
  because a nonce fails *open* the moment somebody forgets one. Page data
  crosses over through `json_script` (`window.pageData(id)`).
- **Everything visual comes from the token block** at the top of
  `static/css/main.css`. No raw colour, spacing, font size, transition duration
  or z-index outside it; the scales are closed sets. A component needing a step
  that is not there means the *scale* is missing a step. The subnav's rule line
  is an inset shadow rather than a border for exactly this reason — the obvious
  implementation needs `margin-bottom: -1px`, which is not a step on any scale
  because it is cancelling a border width.
- **A focus ring is never removed, only quietened.** Scope any suppression with
  `:focus:not(:focus-visible)`.
- **Every dialog is the app's own** and goes through `modalController`. Nothing
  calls `window.confirm`/`alert`/`prompt`.
- **`form.submit()` is never what you want** — it skips HTML5 validation *and*
  every submit listener. Use `requestSubmit()`.
- **A formset row is never taken out of the DOM.** A formset is an index range,
  not a list. Removal ticks `DELETE` and hides (or dims) the row; a form missing
  from the POST is a hole in the range, and Django reads the absent fields
  against that form's own defaults, decides it changed, and validates it — which
  is how a removed row comes back wearing "This field is required".
- **A hidden container makes its inputs unfocusable**, and a validation error
  inside one makes Save do nothing at all with an unfocusable-control warning in
  the console as the only clue. The roster's card holder is moved off-screen by
  CSS rather than given `hidden`, and a removed roster card is dimmed rather than
  hidden, for this reason.
- **Django's `{# #}` is single-line only** — its lexer matches without DOTALL,
  so a comment that wraps is rendered onto the page. Use `{% comment %}`.
- **`_("…")` inside an f-string is never extracted.** Bind it to a name first.
- **A `gettext()` string in JavaScript goes on one line, however long.**
- **A grid or flex column that can hold something wide says `min-width: 0`.**
  The default is `min-width: auto`, "never shrink below my content" — a column
  holding the roster then keeps its full width and *the page* scrolls sideways,
  taking the topbar and sidebar with it.
- **Everything written at runtime goes under `DATA_DIR`**, never `BASE_DIR`.

### This app's own

- **Hours cannot be entered in advance; a status can.** A booking is a record of
  when somebody was demonstrably at work (§16 ArbZG) and nobody has been at work
  tomorrow, so `save_day`, the day form and `confirm_day` all refuse a date
  after today — the correction and the comment with them, because they sit on
  the row and go through the same door. `_day_row.can_edit_hours` is that and
  the lock together, and it is what the three cells key off; the status cell
  keys off the lock alone, because booking leave in advance is exactly what a
  future row is for. `confirm_week` already skipped the future.
- **The future rule is *not* on `DayRecord.save`, where the lock's backstop is.**
  A lock is a promise that a signed-off month cannot be altered, so it is worth
  catching a forgotten view from the model. This is a rule about what a *person
  may type*: `seed_demo` writes the current week — including tomorrow, when
  today is a Monday — and a fixture dated relative to today is not somebody
  entering hours in advance. Guarding the model would make the seeder fail one
  day in seven.
- **A month is locked, and a day is unlocked.** `DayLock` is one row per closed
  date — not one per month, although a month is what a manager closes. Every
  question the app asks is *"may this day be changed"* and never *"is this month
  locked"*, so a month row with a table of per-day exceptions beside it would be
  two representations of one answer, and the day they disagree is the day
  somebody edits a day they should not have. A month is thirty-one rows written
  at once; unlocking is deleting one.
- **The lock is enforced at the model as well as at every door.**
  `assert_unlocked` is called by `save_day`, `set_status`, the day form, both
  confirm routes, Start/Stop and both absence forms — and `DayRecord.save`/
  `delete` call it again, because a view that forgot would otherwise save in
  silence and a lock one forgotten line can be walked past is not a lock.
  `apps/timesheets/test_locks.py` sweeps the doors rather than naming three of
  them.
- **A month with an undecided request in it cannot be locked.** Approving one
  afterwards would change the credited hours of a month that had already been
  signed off without them, which is the one thing a lock is for. Unlocking
  carries no such condition — a condition on an escape hatch is how somebody
  ends up with a month they cannot correct.
- **A status is set from the status cell.** Sick, a day off, time in lieu —
  without opening the Time off page. `views.set_status` fills in the one date
  and hands the rest to `AbsenceRequestForm` / `SickForm`: every rule about who
  may ask for what, which special types are theirs and whether the dates are
  working days at all stays in the absences app, because a second answer to "may
  this person book this day" would disagree with the first the day either
  changed. It is a form POST and a reload where the rest of the page saves
  through fetch — a status changes what the whole month is worth, and it is
  something somebody does a few times a month rather than a few times an hour.
  A closure and a multi-day absence are read-only from a cell and say so: one
  belongs to everybody at once, and the other would have to be split.
- **The timesheet is a month, and it has no Save button.** Ten columns — day,
  status, bookings, break, correction, actual, supposed, saldo, running saldo,
  comment — and a row per date. A comment is written when the box is left; the
  bookings and the correction when their pop-up is accepted. Each is one POST to
  `save_day`, which **answers with the whole month recomputed** — editing the
  third moves the running total on every row below it and all six figures in the
  footer, so a reply carrying only the edited row would leave the column stale,
  and the alternative is repeating the prefix sum, the break rules and the
  credited-hours branches in JavaScript. `build_month` and `build_week` are two
  windows onto one `_day_row`, so the timesheet, the start page and the team
  overview cannot say different things about one Tuesday.
- **The grid never changes shape.** `table-layout: fixed` with a width on every
  column, a height on every cell, and **four bookings shown per day** with the
  rest behind a `+n` that opens the pop-up (`BOOKINGS_SHOWN`, and the template
  reads it from the context so the two cannot disagree about how many four is).
  A day that gained a fifth chip would be a taller row, and this is a grid read
  *down* a column — a row that grows pushes every figure below it out of the
  place the eye last found it.
- **Every duration in the app is `hh:mm`, and there is no setting.**
  `hours.hhmm`, the `hhmm` / `hhmm_signed` filters, and `window.ttHours.hhmm`
  for the pop-up's running summary — `test_month.py` runs the two against each
  other. Ten columns read down only line up when every figure is the same width,
  and 7,5 above 12,25 above 0,25 is a column somebody has to read twice.
  **This removed a per-person preference** (decimal `7,5 h` versus clock
  `7:30 h`) rather than leaving it dormant: once the grid ignored it, a Stop
  message reading "10,20 recorded" sat beside a timesheet reading 10:12, and a
  control that changes nothing is one people press, see no effect from, and
  report as broken. `Preferences` was its only field and "My settings" its only
  section, so the model, the page and its sidebar entry went with it — and the
  Settings disclosure is staff-only now, because that entry was the one reason
  anybody else opened it.
- **A day is entered as a column of comings and goings; the database keeps
  pairs.** `apps/timesheets/bookings.py` is the one door between the two and
  `DayRecord.bookings` is the other direction. The punch list is what somebody
  standing at a terminal does; the pairs are what every rule in this app is
  built on — the break thresholds, the overlap check, the comparison against the
  roster, `elapsed_minutes` across a clock change. A flat punch table would make
  each of those re-derive the pairing first. Two comings in a row is refused
  rather than guessed at, and a *trailing* coming is not a special case at all:
  it is the segment with a null `end`, which is what a running shift always was.
- **The saldo is actual minus supposed, and the running column carries
  forward.** Positive is green, negative red, nought black. The other sign would
  disagree with `build_week`'s `difference`, with `hours_balance`, and with every
  figure on the start page — one page saying +0:30 while another says −0:30 about
  the same Tuesday is not a presentation choice. The running column starts from
  what the person carried *into* the month, so its last row is their balance to
  date and the same number `hours_balance` gives.
- **The month's totals cover the days that have happened, and the whole month's
  contracted hours are reported separately.** Summing the future's contracted
  hours in is what made an ordinary employee read as 176 hours short on the
  first of the month; it also stops the table adding up, because the saldo column
  would total one number while the running column reached another. A day in the
  future therefore has no saldo either — the same clamp `hours_balance` makes.
- **A correction is not a booking and is stored apart from one.**
  `DayRecord.correction_minutes` is signed and `correction_reason` is required
  for any non-zero value, in `clean` and in both forms. The bookings are a record
  of when somebody was demonstrably here (§16 ArbZG) and a stretch nobody stood
  through is not that; a correction that could only add would leave a doctored
  booking as the only way to take time off a day. **It is applied after the
  break**, never before: a day of 5h50 plus a ten-minute correction is not a
  six-hour day, and adding it first deducts a break the person never took.
- **A record carrying only a comment is not an answer about hours.** The month
  lets a note be written against any date, so `_day_row` reports `None` rather
  than nought for such a row. "They worked none of it" and "nobody has answered
  yet" are different statements and the page has always drawn them differently.
- **The roster and the timesheet are separate tables, and the roster is copied
  *from*, never *into*.** A `Shift` is what the manager arranged; a `DayRecord`
  is what happened. The tempting version makes them one row — the roster writes
  it, the employee ticks it, done — and it is wrong in a way that only shows up
  in an argument: confirming would *overwrite the plan*, a manager editing a
  shift afterwards would silently rewrite what somebody agreed to, and the
  question "what were you actually asked to work?" would have no answer. Keeping
  them apart is what lets the timesheet print *"you were rostered 08:00–14:00 and
  you have entered 08:00–15:30"*, which is the sentence the whole app exists for.
- **The break is not resolved the obvious way, and the obvious way underpays it.**
  Reading the tiers as "worked over six hours, so take thirty minutes" against
  the clock-in-to-clock-out span gives a day of 6h05 a full thirty-minute break —
  but the rule is about *working* time, and 6h05 minus thirty is 5h35, which is
  not over six hours at all. Applying them to the net time instead is circular.
  Read each tier as the constraint it is — *either the working time is inside
  the tier, or the total break reaches it* — and take the largest answer.
- **The break needs the *shape* of the day, not its totals.** §4 ArbZG has two
  sentences: a day over six hours needs thirty minutes altogether, **and** nobody
  may work "länger als sechs Stunden hintereinander ohne Ruhepause". So
  `OrgSettings.required_break` takes `(blocks, gaps)` — each unbroken stretch and
  the time between them, from `DayRecord.shape` — and answers

      inside  = Σ over stretches of max over rules of min(break, max(0, stretch - over))
      overall = max over rules of  min(max(0, gross - over), max(0, break - taken))
      D       = max(inside, overall)

  Both are "D must be at least this", so the larger is the least that satisfies
  both. It is repeated in `static/js/hours.js` so the pop-up can answer while
  somebody types, and `apps/timesheets/tests.py` runs the two against each other
  over a table of shapes.
- **A break only counts if it broke the work up, and only if it is long enough.**
  09:30–15:30 and 16:00–18:00 is eight hours with thirty minutes off in the
  middle and owes nothing further. 08:30–15:00 and then 16:00–17:00 has the same
  hour off and still owes thirty, because the first stretch is six and a half
  hours worked straight through and a break taken *afterwards* cannot pay for one
  that was never taken — that was a real bug, and it made the deduction vanish
  the moment an evening hour was added. And a gap under `MIN_BREAK_CHUNK` (15
  minutes, §4 s.2) is not a Ruhepause at all: it counts towards nothing and the
  stretches either side of it are one stretch.
- **The gaps are walked in `position` order, not clock order.** A night shift's
  second stretch starts earlier on the clock than its first, and sorting by time
  reads the gap as nineteen hours.
- **`apps/organisation/tests.py` pins the deduction from three sides.** The
  working time left is never over a tier whose break was not granted; no stretch
  is worked through without the break its own length owes; and one minute less
  would always have broken one of those. The first alone is satisfied by "always
  deduct 30", and the first two together were satisfied by the version that let
  a late break pay for an early one.
- **An empty break table means the defaults, not "no breaks".** The one place
  this app overrides what the database literally says. The direction is the
  point: a break not deducted *overstates* hours worked, which is the side an
  employer is answerable for. The cost is that "no breaks at all" cannot be
  expressed, and in Germany that is not a configuration anybody needs.
- **An overridden break is never recomputed, and always drawn in `--amber`.**
  A break of 30 the rules produced and a break of 30 somebody typed are the same
  number and mean entirely different things to whoever signs the timesheet off.
  `break_is_override` is what stops the recomputation; `break_differs_from_rules`
  is what drives the colour, and the two are deliberately *different questions* —
  a typed break that happens to equal the computed one needs no highlight, and a
  break the rules produced under an older table does need one once the table
  changes.
- **Leave is pro rata by days, never by hours.** A day of leave buys a day off;
  how long that day is does not change how many of them a year holds. Somebody
  on three ten-hour days has the same number of days off as somebody on three
  six-hour days, and scaling by hours would quietly give the second person
  fewer — which is the discrimination case every works agreement on part-time
  leave exists to avoid. `apps/organisation/tests.py` pins it with two employees
  whose hours differ by half and whose entitlement must be identical.
- **A day is only spent if it was a working day.** `Absence.working_days` walks
  the range one date at a time and subtracts three things: a date the contract
  gives no hours, a public holiday, and a date outside the employment. A version
  that subtracted two dates would be right for a full-timer taking a whole week
  and wrong for everybody else.
- **Pending is not subtracted from the balance.** A request that has not been
  decided has not been spent — showing it as spent means somebody whose request
  is declined watches their days come back, which reads as the app having lost
  them. `Balance.remaining` and `Balance.remaining_if_all_approved` are both on
  the page, side by side.
- **The contract is seven columns, not a weekly total.** A weekly total cannot
  answer either question the app is built on: whether a given date is a working
  day for this person, and how long that day is. "20 hours a week" is 8/8/4 for
  one person and 4×5 for another; they are different contracts, and the person
  who books the Wednesday off loses eight hours in one and four in the other.
- **Those seven columns live on `ContractPeriod`, one row per change, and every
  question is asked *as at a date*.** `employee.hours_on_weekday(weekday, on=day)`,
  `contract_on(day)`, `contract_spans(first, last)`. Editing seven columns in
  place would rewrite the whole year the moment somebody's hours changed:
  January's Wednesday becomes a day they never worked, March's entitlement
  becomes what a three-day week buys, and a timesheet printed in February no
  longer reproduces — with every page still rendering. `Employee` has no
  `hours_*` fields any more; anything that reads them without a date is asking
  about *today*.
- **`annual_leave_days` and `leave_days_in_year` are different questions and
  both are on the page.** The first is what a full year of the current contract
  is worth — the figure on the contract page. The second is what this person is
  actually entitled to *in that year*, weighted across every contract that was
  in force during it and clipped to their employment. `Balance` uses the second.
  Applying today's contract to a whole year overpays somebody who went up and
  short-changes somebody who went down; showing an October joiner a full year's
  leave is not generosity, it is a wrong number on the page they use to decide
  whether they can afford Christmas. The rounding happens **once at the end** —
  rounding each slice would hand out a day per contract change.
- **Changing hours is a separate page from correcting them.** `EmployeeForm`
  moves the *first* period (a correction); `ContractChangeForm` writes a new one
  with a date (a change). A manager who opens the contract page to fix a
  spelling must not be able to rewrite somebody's working week as a side effect,
  and a manager who means to change the hours has to answer the one question the
  contract page cannot ask: from when.
- **An employee is not an account.** `Employee.user` is nullable, because on day
  one a manager rosters eleven people and not one of them has signed in yet —
  identities arrive from the provider at the moment of a first token and not a
  second earlier. `Employee.link_by_email` makes the link at sign-in and refuses
  to guess: it needs a non-empty address on both sides, *exactly one* matching
  employee, that employee unlinked, and that account unlinked. Anything else and
  nothing happens, which is visible and fixable rather than silent and wrong.
- **`SET_NULL`, never `CASCADE`, from an account to an employee.** Deleting an
  account must not take a timesheet with it: somebody who has left still worked
  the hours and payroll may need them for years.
- **Manager and staff are different rights.** `employees.is_manager` plans the
  roster and decides requests; `user.is_staff` administers the software. In a
  kindergarten those are reliably different people — the deputy head has no
  business creating logins, and whoever looks after the NAS may never have met
  the staff. `apps/employees/permissions.py` is the roster door;
  `apps/accounts/permissions.py` is the software one.
- **`own_or_manager` checks `user_id is not None` before comparing.** With both
  sides null a bare `==` is True, which would hand every not-yet-signed-in
  employee's timesheet to anybody with an account.
- **A roster card is a form row, and dragging it moves the row.** The cards are
  rendered once into an off-screen holder and *moved* into the column their
  hidden `date` names; a drop rewrites that one input. There is never a second
  representation of the week — no array, no JSON payload — because two
  representations of one thing is the bug where the picture and the saved roster
  disagree, and the first edit to disagree looks like a save that did not take.
- **The hidden date is validated server-side against the week being edited.** It
  is whatever the browser sent, so a page that trusted it would let a bug in the
  drag handler write a shift into next March from a form that says it is editing
  this week — and the page would look completely correct, the row simply would
  not be on it.
- **Editing a day's hours withdraws its confirmation.** Otherwise the record
  says somebody agreed to figures they have never seen, which is exactly the
  claim a timesheet exists to be able to make honestly.
- **"Confirm the week" skips days that already have a record.** The one thing
  that button must never do is overwrite a correction somebody made by hand. It
  is on the *start page* now rather than on the timesheet: the month is where
  hours are entered, and "have I confirmed" is a question the start page exists
  to ask. Saving the month does not confirm — it withdraws confirmation on any
  day whose hours changed, and a comment is not hours.
- **`DayRecord.from_shifts` calls `refresh_from_db()` before applying the break
  rules.** `apply_break_rules` reads the segments through a cached relation, and
  on a record whose segments were just `bulk_create`d that cache is empty —
  without the refresh every confirmed day gets a break of nought, which is a
  timesheet that overstates everybody's hours and looks completely normal.
- **`OrgSettings.is_stored`, never `self.pk`.** The primary key is pinned to 1
  with a *default*, so an unsaved instance already has `pk == 1` and every
  `if self.pk` guard reads as True — then follows relations on a row that was
  never saved, which does not raise and quietly returns whatever is stored under
  id 1.
- **Nobody starts at nought, and the two opening figures are shaped
  differently.** `Employee.opening_balance_minutes` is signed and feeds the
  *running* hours balance from `opening_balance_on` onwards;
  `opening_leave_days` is added to exactly one year's entitlement — the year
  that date falls in — and never again, after which whatever is left carries
  forward through `LeaveCarryOver` like anybody else's remainder. Adding the
  leave every year hands somebody their joining figure again each January;
  adding it to no year loses it, which is what happens when the date is null, so
  `opening_date` falls back to the start date and the form fills it in.
- **`apps/timesheets/balance.py` and `_day_row` must agree.** The running
  balance and the rows are two readings of one thing computed by two functions,
  and the day they drift is the day a timesheet says one number at the top of
  the page and another in the middle. `test_opening.py` holds them to it across
  a credited absence, a half day, a public holiday and a contract change — the
  branches most likely to be added to one and not the other — and
  `test_month.py` adds the month's own version: the last row of the running
  column must equal `hours_balance` for that date.
- **A duration is written by `hhmm`, a time of day by `timeparse.clock`.** The
  two are wrong for each other in opposite directions and both silently:
  `clock` wraps at 24 and drops the sign, so used on a duration it renders 25
  hours as `01:00` and fourteen hours *owed* as `10:00`; `hhmm` pads and keeps
  the sign, which on a time of day would print `-00:30`. `static/js/hours.js`
  makes the same split and calls its halves `clockOfDay` and `hhmm`.
- **Everything is whole minutes, as an integer**, from the roster to the balance.
  The one exception is the contracted hours on `Employee`, which are a `Decimal`
  of hours because that is how a contract is written;
  `apps/timesheets/hours.contracted_minutes` is the only door between the two.
  No template divides by 60 — `{{ x|hhmm }}` is the one way a duration is
  written.
- **A duration can be negative and must format as `-1:15`, not `-1:-15`.** The
  balance column is worked minus contracted, and somebody who left early is
  legitimately below zero.
- **A span whose end is at or before its start crosses midnight.** The rule
  lives in `apps/timesheets/zones.py:elapsed_minutes`; a subtraction written
  inline gives a night shift minus sixteen hours, which makes a week's total
  smaller than the days in it.
- **A span is measured between two *instants*, never between two clock
  readings.** `elapsed_minutes(date, start, end, tz)`. On 363 days a year it
  returns exactly what the wall-clock subtraction returns, and on the two nights
  the clocks move it does not: 23:00–07:00 is seven hours in March and nine in
  October. Nobody notices, which is the point — the October case is the one that
  ends up in front of a labour court, because the employee was demonstrably at
  work for nine hours and the timesheet says eight.
- **Convert to UTC before subtracting two aware datetimes.** Python subtracts
  two datetimes that share a `tzinfo` by ignoring the offset entirely. It is
  documented behaviour and it silently gives back exactly the wall-clock answer
  the zone handling exists to avoid — the code reads as timezone-aware, the
  objects *are* timezone-aware, and the number is wrong twice a year. This was
  a real bug in the first version and a test caught it.
- **The zone is the workplace's, or the employee's own.** `OrgSettings.time_zone`
  is the house clock and is distinct from Django's `TIME_ZONE`, which is the
  *server's* — the NAS may be set to anything. `Employee.time_zone` is blank for
  everybody in an ordinary business and filled in for the colleague who works
  elsewhere: they clock in at nine *their* time, and a button writing the
  office's nine would record a lie about when they were at work. The house zone
  is cached for a minute and `OrgSettings.save` clears it.
- **A stored time is a wall clock reading plus the zone it was read in, not a
  UTC instant.** Storing UTC makes `08:00` render as `07:00` for half the year
  unless every single read converts back, and the read that forgets is silent.
- **A clocked start belongs to the date it is *there*.** `local_today(tz)`.
  Somebody clocking off at 00:30 in Lisbon is clocking off on a date Berlin has
  already left, and the server's date puts the end of a night shift on the wrong
  row — where it reads as a second, unexplained half-hour of work.
- **A `WorkSegment` with no `end` is a shift in progress, and it is worth zero
  minutes.** The tempting answer is "up to now", and it is wrong for the one job
  `minutes` has: it is summed into the day's gross, which the break rules and
  the balance are computed from, and a number that changes on every page refresh
  is not something anybody can sign off. `minutes_so_far` is what a page prints
  beside it and is never stored or summed.
- **At most one stretch may be open at a time**, checked in `_SegmentFormSet`
  and again in `clocking.start`. Two open stretches is a state with no reading —
  Stop would have to guess which of them it ended.
- **A running day cannot be confirmed.** `DayRecord.confirm` raises. Confirming
  means "this is what I worked", and a day with an open stretch has no such
  figure yet.
- **Start and Stop are one route, and the page offers exactly one of them.**
  `apps/timesheets/clocking.py`. Which one it is is decided from the database
  and not from what the form said, so a tab left open overnight cannot start a
  second shift by being the older of the two. There is no second representation
  of "at work" — the button, the week row and the day form all read the same
  open stretch.
- **Clocking does not round.** 07:58 is stored as 07:58. Rounding always in the
  same direction is how a minute a day becomes four hours a year, and §16 ArbZG
  expects a record of the time actually worked.
- **A time is read however it was typed, and there is no format setting.**
  `8:30`, `8,5`, `8.5`, `0830`, `830` and `8` are all half past eight.
  `apps/timesheets/timeparse.py` is the one implementation and
  `static/js/hours.js` repeats it so a box can normalise itself on blur. Asking
  somebody which notation they are about to use is asking them to do the
  computer's job, and the answer is wrong the first time a colleague borrows the
  terminal.
- **Two digits after a separator are genuinely ambiguous, and the context
  settles it.** `8,30` is decimal hours to a payroll clerk and half past eight
  to everybody else — both are ordinary German. A *time of day* prefers the
  clock, a *duration* prefers decimal. One digit is decimal in both, and the two
  readings converge for the common cases. `8,50` is the one that does not
  converge (08:50 as a clock, 8 h 30 as a duration) and it is pinned by a test.
  What makes the guess safe is that **every box normalises what it read as soon
  as you leave it**, so the interpretation is on the screen before anything is
  saved.
- **`type="text"`, never `type="time"` or `type="number"`, for a time.** The
  native widgets look like the stricter choice and are the opposite: `type="time"`
  rejects `830` by *emptying itself*, so the page cannot say what was typed —
  which is the one thing a validation message needs. `type="number"` is the same
  trap wearing a different name. A test walks every `forms.py` for it.
- **A break in minutes is the one field where bare digits are not hours.** The
  label says minutes, and nobody has ever meant forty-five hours by typing 45
  into a box marked "break". Anything with a separator is still read as a
  duration, so `0:45` works too.
- **Two work segments may not cover the same minute.** Checked in the browser as
  it is typed *and* in `_SegmentFormSet.clean`, and compared as minutes on a
  timeline rather than as clock values — the naive version reports every night
  shift as an overlap and lets the one real overlap through whenever a night
  shift is on the day. A segment ticked for deletion cannot clash: it is still
  in the DOM and in the POST, because a formset is an index range.
- **An employee is matched by their directory name, never by e-mail.** Synology
  SSO reads its accounts from LDAP and what LDAP carries is a username. The
  provider sends it as `preferred_username`; `SSOIdentity.provider_username`
  stores it and `Employee.link_by_username` matches on it. `Employee.username`
  is unique case-insensitively, which is what removed the "two people share an
  address, refuse to guess" branch the e-mail version needed.
- **`suggest_username` is a suggestion and stops the moment somebody types.**
  The directory is the authority on what an account is called; a house whose
  convention is `aberger` has to be able to say so. Umlauts transliterate the
  way German directories do (ä → ae), because `mller` is nobody's account name.
- **Time off in lieu costs no leave and keeps no account.** A day with no hours
  entered already reads as a shortfall against the contracted hours, which *is*
  the arithmetic of using up overtime. Recording the kind only names what the
  shortfall was for, so a manager sees a day that was agreed rather than a day
  somebody failed to answer for. Building an overtime balance on top would be
  inventing a second set of figures to disagree with the first. It is the one
  absence that credits no hours, and that is what makes the mechanism work —
  see the next rule.
- **Every other absence credits the contracted hours; time off in lieu does
  not.** `Absence.credits_hours` and `Absence.credited_minutes`, read by
  `build_week`. A sick day is paid as though it had been worked (§3 EFZG) and so
  is a day of leave (§11 BUrlG), so both hand back the contracted minutes and
  the week comes out level with the reason named on the row. **This reverses the
  original "absence is not added back" decision**, and the reversal is not a
  preference: the first version showed a fortnight's flu as eighty hours of
  shortfall, which is a debt German law says outright the employee does not owe.
  A half day credits half, through the same `portion_of` the balance uses, so
  the hours and the days cannot disagree.
- **A sick day counts from the moment it is reported, not from the moment a
  manager acknowledges it.** Sickness is now `REQUESTED` so it appears on the
  manager's list, but `credits_hours` returns True for anything not
  `REJECTED` — the acknowledgement is a *receipt*, not a permission. An employer
  does not grant illness. The one thing that withholds the credit is the
  employer positively refusing to accept the absence, which requires a written
  reason. A version that waited for the button would show somebody off with flu
  as eighty hours short for as long as their manager was on holiday.
- **A half day is one date, and only one date.** `Absence.is_half_day` is
  refused on a range, by `clean` and by both forms. The general version — half at
  the start of a range, half at the end — is four more states and every one has
  to be right in `working_days`, in the credited hours and in the closure
  materialiser. "Wednesday afternoon, then Thursday and Friday" is two rows,
  which is one more click and no ambiguity at all about what was booked.
- **`Absence.working_days` returns a `Decimal`, never an `int`.** 0.5 has to
  survive being added to 2 and compared against an entitlement, and doing that
  in floats is how a balance page ends up reading 17.499999999999996.

## Security

- **A login is not authorisation.** `LoginRequiredMiddleware` gates on an
  enumerated open list (`apps/accounts/pages.py`) rather than per-view
  decorators, because a forgotten decorator leaves a page that answers to
  anybody and looks completely normal. Who may see *whose* time is a second
  question, answered by `apps/employees/permissions.py`; who may change the
  *rules* is a third, answered by `@staff_required`. Those two are per-view —
  and the exposure a forgotten one would create is covered from the other side,
  by tests that walk the URLconf for the `employees`, `roster` and `organisation`
  namespaces and refuse to let any route answer an account without the right.
- **This app stores no files, deliberately.** There is no `MEDIA_ROOT` and no
  upload path. A timesheet is rows; a sick note is a piece of paper that belongs
  in a personnel file under somebody else's retention policy, not in a
  container's bind mount — and once one is stored here the app is holding health
  data it has no lawful basis to keep. `config/tests.py` walks every model and
  fails on a `FileField`.
- **A sick absence records that somebody was ill and never why.** There is no
  diagnosis field and no note on the sickness form, and adding one would turn an
  ordinary attendance record into a health record.
- **Sickness is stated, not requested.** An employer does not grant it, so there
  is no route by which a sick day becomes `REQUESTED` and no button a manager
  can press to refuse one.
- **The OIDC client secret is in the database**, encrypted at rest with a key
  derived from `DJANGO_SECRET_KEY`, never rendered back to a browser, and behind
  a superuser-only page. `apps/accounts/models.py` states the trade at length;
  it was a deliberate reversal and should not be quietly undone in either
  direction.
- **Identity is the OIDC `sub`, never e-mail.** The one exception — linking a
  token to an existing local account by address — is hedged about with four
  conditions in `SynologyOIDCBackend._account_to_link`, and
  `Employee.link_by_email` repeats the same shape for the same reason.
- **The SSO settings page must never be able to lock everybody out.** The local
  password form stays reachable at `?local=1` whatever is configured.

## Tests

~610 cases. The value is concentrated in the ones that **discover their own
targets**, so a page added next month is covered the day it lands:

- `config/tests.py` walks the URLconf (the sidebar registry and the open list
  must both name routes that exist), every template (inline script/style,
  `onclick=`, multi-line `{# #}`, remote fonts), every `.js` file, every `.po`,
  and `main.css` (the closed scales).
- `apps/organisation/tests.py` holds the break resolution — ten lengths of day
  chosen because the naive implementation gets each one wrong — plus an
  invariant checked across every five-minute step: the working time left after
  the break must not exceed any tier whose break was not fully granted. A
  reimplementation that satisfies that cannot be wrong in the direction that
  costs somebody a break.
- `apps/absences/tests.py` pins the three subtractions in `working_days`, and
  Easter for five known years — four of the thirteen holidays are offsets from
  it, so getting it wrong moves a quarter of the year at once, and "returns a
  Sunday" is something every wrong answer also does.
- `apps/timesheets/tests.py` holds the confirm/override core, and the check that
  `static/js/hours.js` still computes the break the way Python does.
- `apps/timesheets/test_month.py` holds the month: the pairing of comings and
  goings and each shape it refuses, the correction landing *after* the break,
  the saldo's sign, and the invariant that the last row of the running column
  equals `hours_balance` for that date. Saving is per day and answers with the
  whole month, so a refusal is checked to leave that day — and only that day —
  exactly as it was.
- `apps/timesheets/test_zones.py` names the two real nights the clocks move and
  asserts seven hours in March and nine in October — plus the invariant that on
  an ordinary day the zone-aware answer equals the plain subtraction, without
  which every existing night-shift test would be quietly wrong.
- `apps/timesheets/test_clocking.py` holds Start and Stop, the open-ended day,
  and the four refusals (already running, nothing running, no length, inside an
  existing stretch).
- `apps/absences/test_leave_year.py` holds half days, credited hours, the
  contract history and the whole of carry-over and expiry — including the case
  that matters most: **without a recorded reminder, nothing lapses.**
- `apps/timesheets/test_locks.py` walks the write paths against a locked day —
  both pop-ups, the comment, the old day form, both confirm routes, Start, and
  every way an absence can be written. A lock is worth as much as its
  least-guarded door, and a test naming three of them passes for exactly as long
  as it takes somebody to add a fourth.
- `apps/employees/test_privacy.py` walks the *whole* URLconf and refuses to let
  any route answer somebody who is not signed in, then checks each of the
  cross-employee doors by hand. Its route-reverser fails loudly on a route it
  cannot reverse rather than skipping it, because a skipped route is an
  unchecked route.
- `apps/employees/tests.py` holds the four conditions on `link_by_email` and the
  manager/staff split.

Two harness notes carried over from the family: the `english` fixture in
`conftest.py` sets **both** `LANGUAGE_CODE` and `translation.override`, because
`LocaleMiddleware` resolves the language again per request; and the `monday`
fixture is a fixed date well clear of any real public holiday, so a test that
counts working days is not quietly changed by the calendar it runs on.

## Standing decisions

Things that look like gaps, have an answer, and are listed so the next pass
recognises them as decided rather than missed.

- **The public holidays are computed, not a dependency.** A holiday table
  somebody else maintains goes stale silently: it is right for the years it
  shipped with, and the first January nobody upgrades, every Karfreitag in the
  app is missing. Ninety lines of arithmetic have no release cadence to track and
  are pinned by a test naming real dates.
- **Land level, not municipality.** Fronleichnam in parts of Saxony and
  Thuringia and Mariä Himmelfahrt in Catholic Bavaria are decided by the town
  hall. This app answers at Land level and says so on the page — which is the
  whole reason `BankHoliday` is a *table* rather than a function: the calculation
  is a first draft, `is_generated` marks its own rows, and regenerating a year
  leaves anything added by hand alone.
- **Leave carries over, and the two halves of it expire on different terms.**
  `apps/absences/carryover.py`. `OrgSettings.statutory_leave_days` splits the
  entitlement; the statutory part carries to a deadline (31 March by default,
  §7(3) BUrlG) and the employer's extra to its own (31 December by default).
  This replaces an earlier standing decision that said carry-over was not
  modelled — the reason it changed is that not modelling it was not neutral: an
  app that silently dropped everything at midnight on 31 December was asserting
  a policy, and the wrong one.
- **`LeaveCarryOver` is the one thing in the leave accounting that is stored
  rather than derived**, and the exception is deliberate. Expiry is an *event*:
  it has a date, somebody may have extended it for one person for a reason, and
  under German law it may not have happened at all. Re-deriving it in June would
  answer with June's settings, June's contract and June's deadline — so a
  deadline extended afterwards would un-expire days that were already gone.
- **Statutory days do not lapse unless the employee was told.** Since the
  Bundesarbeitsgericht's *Hinweispflicht* decisions the employer must
  demonstrably have said what was left and that it was about to expire.
  `notice_given_on` is that record and `expires_statutory` is gated on it; a
  deadline with no notice against it is reported on the year-end page and does
  not bite. Expiring the days anyway would destroy an entitlement that legally
  still exists, along with the only record that it did.
- **The perishable pot is spent first.** `close_year` splits what is left by
  drawing the statutory days down before the employer's extra, and
  `statutory_remaining` reads it the same way. The other order would let
  protected days lapse while contractual extra sat safe, which is the opposite
  of what the protection is for.
- **Closing a year and expiring its days are two separate acts.** Closing
  records what was left on 31 December; expiry happens on 31 March to whatever
  of it is still there. Expiring early is refused — the days are the employee's
  until the morning after, and there is no undo.
- **Absence is not added back as time worked.** A week containing a holiday shows
  fewer hours worked than contracted, with the reason named on the row. This app
  reports hours; it is not payroll, and a "credit" that guessed the contracted
  length of an absent day would be inventing figures somebody pays against.
- **The week starts on Monday and it is not a setting.** Germany's week starts on
  Monday and `date.weekday()` numbers it that way, so a weekday index never needs
  converting. A configurable first day would mean every seven-long list in the
  codebase knowing which rotation it is in, for a business that will never change
  the answer.
- **The roster's seven columns never reflow to one.** At a narrow width the week
  scrolls sideways instead. A week that is not seven columns is not a week, and
  the comparison across days is the whole reason anybody opens the page. The
  contract's seven hour boxes *do* reflow, because they are seven independent
  numbers and nothing is compared across them.
- **Copying a week adds rather than replaces**, and the button says so.
  Replacing is the tidier implementation and would silently discard a fortnight
  somebody had already adjusted; adding leaves a visible duplicate that takes one
  drag to fix.
- **"Fill from contracts" adds the break on top of the contracted hours.** A
  contract counts working time and a shift is clock-in to clock-out, so without
  it everybody rostered against a 7.5-hour contract would be down 45 minutes a
  day the moment they took the break they are legally required to take — an
  arithmetic error that turns up in a payroll audit rather than on the page.
- **A closure materialises absence rows rather than being consulted at read
  time.** So the balance page shows it beside the days somebody chose, in one
  list with no second code path — and somebody who joins in September does not
  retroactively acquire the August closure.
- **`Balance` is derived, never stored.** A stored balance has to be kept in step
  with every absence written, withdrawn, approved and declined, and with every
  contract change that moves the entitlement underneath it. Each of those is a
  chance for the figure and the absences to disagree, and when they do the number
  on the page is wrong with nothing on the page to show it.
- **One `build_week`, one `Balance`, used by both the employee's page and the
  manager's.** A figure that reads differently depending on who is looking at it
  is the single most damaging bug this app could have, and two implementations is
  how it happens.
- **The day and confirm routes are duplicated under two prefixes.** `day` and
  `employee-day` resolve to one view and differ only in their path, because
  `apps/nav.py` keys the sidebar on the resolved `(app, url_name)` pair and a
  single shared route would light "My time" while a manager was looking at
  somebody else's Tuesday. The prefix is presentation; `own_or_manager` in the
  view is the check.
- **Three assignment modes for special leave, not one.** Fixed, pro rata and a
  threshold table all exist in real agreements and give genuinely different
  numbers. A single pro-rata mode would be tidier and would silently turn
  "everybody gets their birthday off" into "everybody gets three fifths of their
  birthday off". The threshold mode's *gap* is the point: "five days a week gets
  two, three days gets one" says by implication that two days gets none.
- **Having a leave type does not grant it.** `SpecialLeaveGrant` is the row that
  says a particular person has one, which is what makes it possible to offer a
  type to some employees and not others without inventing a second type for the
  people who do not get it. A type not listed on somebody's contract is not
  theirs — it is not "zero days of it".
- **Deleting is refused once anything is recorded**, for employees and for leave
  types alike, and the message names the reversible operation instead. The
  destructive version exists for the row created by a mistyped name ten seconds
  ago and nothing else.
- **`tzdata` is an unconditional dependency, not a Windows-only one.**
  `zoneinfo` reads the operating system's IANA database and falls back to the
  wheel when there is none — and `python:3.13-slim`, which is what the container
  runs, is not guaranteed to carry one. Without it `ZoneInfo("Europe/Berlin")`
  raises, `zones.py` falls back to UTC exactly as designed, and every clocked
  time is an hour or two out all summer in a way that looks almost right.
  `test_zones.py` asserts four real zones resolve, so dropping it is a red
  build rather than a silent hour.
- **No in-app export.** The database is one SQLite file under `/data`, which
  Hyper Backup already covers, and a payroll export is a format question nobody
  has asked yet. It is the obvious next feature and deliberately not guessed at.
- **The break rules default to the statute exactly**: 30 minutes over six hours
  and 45 over nine (§4 ArbZG). **This reverses an earlier decision** that made
  the second tier eight hours, on the argument that a default about a legal
  minimum may only err towards the employee. It reads as a wrong figure to
  anybody who has looked the law up, and a default that has to be explained is
  not a safe default; a house that wants 45 minutes at eight hours says so in
  one edit on the settings page. An administrator can still edit the table
  looser than the law and nothing stops them, which `docs/COMPLIANCE.md` lists
  as a gap.
- **The app holds no health data and must not start.** Sickness is a date range
  and nothing else — no diagnosis, no note on the form, no certificate. The eAU
  flow keeps that between the doctor, the insurer and payroll, which is where it
  belongs. The same argument applies to SGB IX disability leave: naming a leave
  type after it makes the grant list a record of somebody's disability status.
- **Both a drag and arrow keys move a roster card.** A drag has no keyboard
  equivalent and cannot be offered to a screen reader at all, so the `‹` and `›`
  buttons are not a courtesy — they are the only way half a team can use the
  page.
