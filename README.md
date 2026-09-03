# Time Tracking

Roster and time tracking for a small business that schedules its staff — a
kindergarten, a school, a practice. The manager plans the week; the people who
worked it confirm what they actually did; the app keeps the leave, sickness and
public-holiday accounting behind that.

Self-hosted: one container on a Synology NAS, behind that NAS's reverse proxy,
signing people in against the Synology SSO Server over OIDC with a local
password as the way back in. German by default, English from the topbar globe.

---

## What it does

**For everybody**

- **Start and Stop.** One button, and only ever the one that makes sense: press
  Start when you arrive and Stop when you leave, and the current time in your own
  clock goes onto the timesheet. Nothing is rounded. A shift started at 22:00 is
  still yours to stop at 02:00, and it lands on the day it began.
- **Confirm the week in one press.** Most days are exactly what was rostered, so
  the normal case needs no typing at all. The manual form is for the days that
  are not.
- **Enter a day by hand** — as many stretches of work as it takes. A split shift
  is two rows; the gap between them is not a break you enter, it is simply time
  you were not there. Two stretches that overlap are refused before the page can
  be saved, because the overlapping time would otherwise be counted twice.
- **Leave a stretch open.** A start with no end yet is a shift in progress, drawn
  as one and counted as nothing until it has an end. Only one may be open at a
  time, and a day that is still running cannot be confirmed — agreeing to a total
  that is about to change is exactly what a timesheet must not be able to record.
- **Work across midnight, and across the clock change.** 23:00 to 03:00 is four
  hours. On the last Sunday in March the same shift is three, and in October it
  is five, because that is how long the people working it were actually there.
- **Book half a day.** Half a day of leave, half a day's hours credited, one
  number behind both.
- **Type a time however you type times.** `8:30`, `8,5`, `8.5`, `0830`, `830` and
  `8` are all half past eight. There is no setting for it and there is not meant
  to be: the box reads what you wrote and rewrites it as `08:30` the moment you
  leave it, so you can see what it understood. Anything it genuinely cannot read
  is refused with the value quoted back.
- **Breaks work themselves out** from rules an administrator sets, and can be
  overridden. An overridden break is drawn in amber everywhere it appears,
  because a 30 the rules produced and a 30 somebody typed mean different things
  to whoever signs the timesheet off.
- **Ask for holiday**, see the balance before you do, and watch it wait for a
  decision — the days are not taken off until somebody says yes.
- **Ask for time off in lieu** of overtime. It costs no leave: a day with no
  hours on it already counts as a shortfall against your contract, so the
  request only marks the day as agreed rather than unanswered.
- **Report sickness.** You are telling the app, not asking it, and it counts from
  the moment you record it — the hours for those days are credited and it costs
  no leave. Your manager is shown it and confirms they have seen it; that is a
  receipt, not a permission, because an employer does not grant illness.
- **See where you stand overall**, not only this week — a running balance of
  everything worked against everything owed, including whatever was agreed
  before you started here.
- **See a week that adds up.** A public holiday, a day of leave and a sick day
  are credited at your contracted hours, so a week containing one comes out level
  with the reason named on the row rather than looking like time you owe. Time
  off in lieu is the exception and is credited nothing, because that shortfall is
  the overtime being taken back.

**For a manager**

- **Plan the week by dragging cards** between seven day columns. People who are
  already away are drawn in the columns too, including requests nobody has
  decided yet — because deciding one and planning around it are the same job.
- **Draft a whole week from the contracts**, or copy last week onto this one.
- **See the team's week at a glance** — one row per person, one cell per day,
  coloured by what state it is in and outlined when the hours entered are not
  the hours rostered.
- **Decide requests** with that person's balance printed beside each one.
- **Keep the contracts**: which days somebody works and how long each one is,
  what that entitles them to, and which special leave they have been granted.
- **Record what somebody arrived with.** Hours in hand or in debit, and leave
  days not yet taken, carried in from a previous contract. The hours start the
  running balance; the leave is added to that year's entitlement and then
  behaves like anybody else's remainder. Nobody starts at nought, and the
  alternative was inventing a week of hours nobody worked.
- **Change somebody's hours from a date**, mid-month or mid-year, without
  rewriting a single week that has already been worked. The contract is a
  history, so February is still measured against February's hours and the year's
  leave is worked out from every contract that was in force during it, each
  weighted by how much of the year it covered.
- **Close the leave year**, see what everybody is carrying, and extend one
  person's deadline with a reason when the circumstances call for it. The page
  says out loud whose days *cannot* expire because nobody was told they would —
  which under German case law is most of them, most of the time.

**For an administrator**

- Break tiers, the full-time week, what a full-time year of leave is and how the
  fraction rounds for everybody else.
- How much of that leave is the **statutory** part, and when each half expires —
  the protected days to a carry-over deadline, the employer's extra to its own.
- The **time zone** the workplace keeps, with a per-person override for anybody
  who works somewhere else.
- German public holidays, generated per Bundesland.
- Closures — Betriebsferien, the days between Christmas and New Year.
- Special leave types, with three ways of working out who gets how much.
- Accounts and the SSO connection, both edited in the app.

---

## The three things worth knowing before reading the code

**The roster and the timesheet are separate tables.** A shift is what the
manager arranged; a day record is what happened. They are never merged, which is
what lets a timesheet say *"you were rostered 08:00–14:00 and you have entered
08:00–15:30"* — the sentence the whole app exists to be able to print.

**Leave is pro rata by days, never by hours.** A day of leave buys a day off;
how long that day is does not change how many of them a year holds. Somebody on
three ten-hour days gets the same number of days off as somebody on three
six-hour days.

**A day of leave is only spent if it was a working day.** Not a working day
under the contract, a public holiday, or outside the employment — none of those
costs anything.

**The contract is a history, not seven columns.** Every question about hours is
asked *as at a date*: was this a working day, how long was it, what is the year
worth. Changing somebody's hours writes a new row with the date it took effect,
and everything before it keeps what it had. The alternative — editing the columns
in place — silently rewrites every week already worked, with every page still
rendering and different numbers than the day before.

**A span is measured between two instants, not two clock readings.** On 363 days
a year those are the same number. On the two nights the clocks move they are not,
and the difference is an hour of somebody's pay in each direction.

**People are recognised by their directory name.** Synology SSO reads its
accounts from LDAP, and what LDAP carries is a username — `anna.berger`, not an
e-mail address. That name goes on the contract when somebody is added (the form
suggests `firstname.surname`), and the link to their account is made by itself
the first time they sign in.

---

## Layout

```
apps/
  accounts/       sign-in, the SSO connection, account management, preferences
  organisation/   the rules: break tiers, entitlement, Bundesland, leave types
  employees/      contracts, the account link, who manages the roster
  roster/         shifts and the week planner
  absences/       holiday, special leave, sickness, closures, public holidays
  timesheets/     day records, the week, the start page, hour formatting
  nav.py          which sidebar entry a resolved URL marks
config/           settings, URLs, CSP, health, the cross-cutting tests
static/           css (one file), js (one per page), fonts, the icon
templates/        base.html and one directory per app
tools/            the German catalogues, as tables, and the script that writes them
docs/             COMPLIANCE.md — the German statutes and what the app does about them
                  AUDIT.md — who inspects a time-tracking system here, and what they ask it for
deploy/           Dockerfile, compose files, entrypoint
locale/de/        the compiled catalogue (.po and .mo are both committed)
```

## Getting it running

```
uv sync
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
uv run python manage.py seed_demo
uv run python manage.py runserver
```

Then sign in as `ben` / `timetracking-dev-pass` (a manager), `anna` (an
employee) or `admin` (a superuser).

`collectstatic` is not optional even in development — static files go through
WhiteNoise's manifest storage in every mode, and a checkout that has never run
it fails most of the test suite with "Missing staticfiles manifest entry".

### Tests

```
uv run pytest
```

~610 cases, about four minutes. Most of the value is in the ones that
discover their own targets — every URL, every template, every `.js` file, every
`.po` — so a page added next month is covered the day it lands. Two of them walk
the whole URLconf from the outside and refuse to let any route answer somebody
who is not signed in, or answer about an employee who is not theirs.

### Translations

The German catalogue is generated from a table rather than hand-edited:

```
uv run python manage.py makemessages -l de --no-obsolete --no-wrap
uv run python manage.py makemessages -d djangojs -l de --no-obsolete --no-wrap
uv run python tools/apply_translations.py
uv run python manage.py compilemessages -l de --ignore=.venv
```

A new string goes into `tools/translations_de.py`, `tools/translations_de_pages.py`
or `tools/translations_de_year.py`, not into the `.po`. A key in more than one of
them is refused rather than silently resolved. `CLAUDE.md` explains why.

## Deployment

`DEPLOYMENT.md` is the run-book: the reverse proxy rule, the SSO client, the
data folder, backups and rolling back. In short — run the published image with
`deploy/docker-compose.release.yml`, bind-mount a folder to `/data`, and set
`TIMETRACK_UID`/`TIMETRACK_GID` in `.env` to the DSM user that owns that folder.
`/volume1/docker` is an ACL-enabled share where `chown` succeeds and grants
nothing, and the container's own uid 1000 then cannot write, which is the one
failure that costs an afternoon.

`.env.example` documents every setting. Nothing loads it automatically; Django
reads the process environment.

## Legal

`docs/COMPLIANCE.md` lists the German statutes a time-tracking system runs into
— ArbZG, BUrlG, EFZG, MiLoG, ArbSchG, TzBfG, JArbSchG, BetrVG, DSGVO and the
relevant BAG and ECJ decisions — with, for each, what this app does and what it
does not.

**It is worth reading before this is used for real.** The app covers the break
rules, the public holidays, the pro-rata leave, the part-year entitlement for
somebody who joins or leaves mid-year, and the §7(3) BUrlG carry-over — including
the *Hinweispflicht*, which is the part most systems get wrong. It records
whether each person was told their days were about to lapse, and if there is no
such record it treats the days as **not expiring**, because under German case law
they do not.

It also flags the two working-time limits — a day over eight or ten hours (§3
ArbZG) and a rest period under eleven (§5) — on the row and in a count under the
month. **Flagged and never refused**, because §16 requires a record of the time
actually worked and refusing an eleven-hour day removes the evidence rather than
the hour. What it still does *not* cover is the 24-week average that decides
whether the long days were lawful, the six-month waiting period of §4 BUrlG, a
retention policy, an export, or an audit trail on an edited timesheet.

`docs/AUDIT.md` is the companion and asks the other question: **who turns up.**
The FKS with §17 MiLoG, the DRV every four years, the Finanzamt with the GoBD,
the Arbeitsschutzbehörde, the data protection authority, the works council, a
labour court — and, if a corporate customer asks for "the certificate", an
IDW PS 880 *Softwarebescheinigung*. It says what each of them wants out of the
software, and it holds the ordered list of what is still missing. The short
version of that list: an audit trail, an export, and a retention policy, in that
order, because those three are what more than one of them asks for.

Neither file is legal advice, and if there is a works council then §87 BetrVG
makes talking to them a precondition rather than a courtesy.

## Status

**v0.1.0 — the first release.** Everything described above is built and the test
suite covers it: about 640 cases, including the ones that walk the URLconf, every
template, every `.js` file and every `.po` so that a page added next month is
covered the day it lands.

What has **not** happened yet, stated plainly because a release note that only
lists what works is not much use:

- **No OIDC round trip has completed against a real Synology SSO Server.** The
  handshake is exercised by tests against a stubbed provider, which is not the
  same thing. Keep a local superuser and remember `?local=1` — the local sign-in
  form stays reachable whatever SSO is doing, deliberately.
- **Nothing has run on a NAS.** The image is built, started and probed by CI on
  every commit and again on every tag, so "it starts and serves" is verified;
  "it starts and serves *there*" is not, and `DEPLOYMENT.md` §9 exists for the
  first afternoon.
- **The German wording is a first pass by one translator.** Worth reading over
  before it goes in front of staff, especially the explanatory paragraphs on the
  leave and break pages — those are the strings that stop somebody opening a
  ticket about a number they think is wrong.
- **No audit trail on an edited timesheet, no export, and no retention policy.**
  `docs/AUDIT.md` ranks them in that order and says which auditor each one is
  for; the audit trail is the only item that appears in every column of that
  file. All three want a decision from whoever runs the business rather than a
  guess from the code.
