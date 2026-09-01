# German working time law, and what this app does about it

**This is engineering notes, not legal advice.** It is a working list of the
statutory duties a time-tracking system for a German employer runs into, written
so that the next person changing this code knows which lines are load-bearing
for a legal reason rather than a design one. Nobody here is a lawyer. Before any
of it is relied on, it wants an hour of a *Fachanwalt für Arbeitsrecht* and — if
there is a works council — a conversation with them, because §87 BetrVG makes
that conversation mandatory rather than polite.

Each section says three things: what the law requires, what the app does, and
what it does **not** do. The third is the useful column.

---

## 1. ArbZG — Arbeitszeitgesetz (working time)

### §3 — how long a day may be

Eight hours. Extendable to ten, provided the average across six calendar months
or 24 weeks stays at eight.

| | |
|---|---|
| **Does** | Nothing. A day of any length can be entered and saved. |
| **Does not** | Warn at 8 h, refuse at 10 h, or compute the 24-week rolling average. |

The rolling average is the harder half and the one that actually bites: an
employer who runs ten-hour days through a busy quarter has to be able to show
the compensating weeks. **This is the single largest compliance gap in the app.**

### §4 — breaks

30 minutes for more than six hours of working time and up to nine; 45 minutes
for more than nine. Splittable into blocks of at least 15 minutes. Fixed in
advance (*im Voraus feststehend*). And: **nobody may work more than six hours
consecutively without a break.**

| | |
|---|---|
| **Does** | Computes the break each day still owes and deducts it, from the *shape* of the day — each unbroken stretch and the gaps between them. `D = max(Σ per-stretch requirement, whole-day requirement)`, both in the constraint form, so a 6 h 05 day gets 5 minutes rather than a full 30 and a 9 h 05 day does not jump to the higher tier. `OrgSettings.required_break` explains it; `apps/organisation/tests.py` pins it from three sides — the working time left is never over an ungranted tier, no stretch is worked through without the break its own length owes, and one minute less would always have broken one of those. An empty rule table falls back to the statutory defaults rather than to nothing, because a break not deducted overstates hours worked. |
| **Does** | Count a break the employee **actually took** — the gap between clocking out and clocking back in — against what the tier requires. 09:30–15:30 and 16:00–18:00 is eight hours at work with thirty minutes off, which is what §4 asks; nothing further comes off. Deducting the statutory figure on top of a break already taken charged the employee twice for it. |
| **Does** | Apply §4 sentence 3 — *no more than six hours in a row without a break* — to the deduction. Each unbroken stretch owes the break its own length asks for, so 08:30–15:00 followed by 16:00–17:00 still has thirty minutes taken off: the hour off afterwards cannot pay for a break that was never taken during the six and a half. A gap under 15 minutes is not a Ruhepause (§4 s.2), counts towards nothing, and does not split the stretch either. |
| **Does not** | *Refuse* a stretch over six hours, or place the break at a particular time. It deducts what should have been taken; it does not stop the record being entered, and the working time left can still exceed six hours on a long enough stretch — which is a §4 breach the app deducts for but does not report. |
| **Does not** | Model breaks as *fixed in advance*. The roster carries shift start and end, not planned break windows. |
| **Note** | The shipped tiers are **the statute exactly**: 6 h → 30 min and 9 h → 45 min. The second was 8 hours for a while, on the argument that a default may only err towards the employee; it was changed back because a figure that does not match the law somebody has looked up has to be explained, and a house wanting 45 minutes at eight hours can say so in one edit. An administrator editing the table must not go looser than 6 h → 30 and 9 h → 45. Nothing in the app stops them. |

### §5 — rest between shifts

At least 11 uninterrupted hours. Reducible to 10 in listed sectors (care,
hospitals, gastronomy, agriculture) if compensated within four weeks.

| | |
|---|---|
| **Does** | Nothing. |
| **Does not** | Check the gap between one day's end and the next day's start, in the roster or in the timesheet. A closing shift ending 22:00 followed by an opening shift at 06:00 is eight hours' rest and is accepted silently. |

Worth noting that the app already has the arithmetic: `minutes_between` and the
segment model know when a day ends. The check is small; it is simply absent.

### §6 — night work

Night time is 23:00–06:00 (bakeries 22:00–05:00). A *Nachtarbeitnehmer* works
at least two hours of it in normal rotation, or 48 nights a year. Their day is
capped at 8 h, extendable to 10 only with compensation within a calendar month;
they have a right to periodic health checks and to a surcharge or compensating
days off (§6(5)).

| | |
|---|---|
| **Does** | Handles a shift that crosses midnight correctly, everywhere. |
| **Does not** | Identify night workers, count night hours, apply the tighter cap, or track the §6(5) entitlement. |

Not relevant to a kindergarten. Very relevant if this app is ever pointed at a
care home, which is the obvious next kind of user.

### §9–§11 — Sundays and public holidays

Work on a Sunday or public holiday is prohibited unless an exception applies.
At least 15 Sundays a year must be free. Sunday work is compensated with a
replacement rest day within two weeks; public holiday work within eight.

| | |
|---|---|
| **Does** | Knows every public holiday per Bundesland and never charges leave for one. |
| **Does not** | Refuse or flag a shift rostered on a Sunday or holiday, count free Sundays, or track replacement rest days. |

### §16(2) — **the record-keeping duty**

Working time **beyond the eight-hour working day** must be recorded, and the
records kept for **at least two years**.

| | |
|---|---|
| **Does** | Records every day in full — start, end, break, total — which is more than §16(2) asks for and is what §3 ArbSchG now requires anyway (below). Records are immutable in the sense that nothing deletes them: an employee leaving is switched off, and deleting their *account* is `SET_NULL` and never touches the timesheet. |
| **Does not** | Have any retention policy at all — neither a minimum that resists deletion nor a maximum that enforces erasure. See §9 (data protection) for why the maximum matters as much as the minimum. |

### §16(1) — the notice

A copy of the ArbZG must be displayed in the workplace. Nothing to do with
software; noted because it is the duty most often forgotten.

### §22 — what it costs

Up to €30,000 as an *Ordnungswidrigkeit*; §23 makes wilful, repeated breaches
endangering health a criminal matter.

---

## 2. ArbSchG §3 + the BAG and ECJ rulings — recording *all* working time

This is the part most people mean when they say "the new time recording law",
and it is worth being precise because the position is unusual.

- **ECJ C-55/18 (CCOO, 14 May 2019)** — member states must require employers to
  set up an "objective, reliable and accessible" system measuring daily working
  time.
- **BAG 1 ABR 22/21 (13 September 2022)** — the German Federal Labour Court read
  that into the *existing* §3(2) Nr. 1 ArbSchG. So the duty to record **all**
  working time — not just the overtime §16(2) ArbZG asks for — already applies,
  today, without any new statute. The same decision held that a works council
  has no *Initiativrecht* to introduce time recording, precisely because it is
  already required.
- **A draft amendment to §16 ArbZG** (Referentenentwurf, April 2023) would add an
  explicit duty to record electronically, on the day the work is done, with
  transition periods by employer size. **As of this writing it has not been
  enacted.** Do not build against its detail; do assume the direction.

| | |
|---|---|
| **Does** | Records start, end and break for every day, per person, and keeps them. The employee is the one who enters or confirms, and the record says who confirmed and when — which is the "objective and accessible" part. Delegating the entry to the employee is expressly permitted; the *duty* stays with the employer. |
| **Does not** | Enforce recording **on the day**. Somebody can confirm a fortnight late, and the start page nudges rather than insists. If the amendment passes in its draft form this becomes a real gap. |
| **Does not** | Make records tamper-evident. A manager can edit a confirmed day and the only trace is that the confirmation is withdrawn — there is no audit trail of *what it was before*. For a document that is evidence in a wage dispute, that is thin. **See §11 below; this is the second-largest gap.** |

---

### Recording in advance

| | |
|---|---|
| **Does not** | Accept hours on a day that has not happened. §16 ArbZG asks for a record of the time actually worked, and a booking dated tomorrow is not one — so bookings, corrections and the day's comment are refused after today, at `save_day`, the day form and `confirm_day` alike. |
| **Does** | Accept a *status* for any future date. Booking leave or recording a training day in advance is the ordinary use of a roster, and it is a statement about a plan rather than about hours worked. |

### Closing a month

| | |
|---|---|
| **Does** | Let a manager lock a month, per person, after which no booking, status, correction or comment in it can be changed. `DayLock` is one row per closed date; `assert_unlocked` gates every write path and `DayRecord.save`/`delete` gate it again. Who locked it and when is on every row. |
| **Does** | Refuse to lock a month with an absence still waiting for a decision in it, because approving one afterwards would change hours the month had been signed off on. |
| **Does not** | Prevent a manager unlocking a day and changing it. That is the point of the unlock, and the row records who locked it and when — but there is no log of *what changed* while it was open. §16 ArbZG asks for the record to be kept two years; it does not ask for an edit history, and this app does not keep one. |
| **Does not** | Stop `close_year` materialising a company closure into a locked month. It is the employer's own act on its own page, and the year it runs over is normally long shut. |

## 3. MiLoG §17 — the stricter recording duty

For **minijobs** (geringfügig Beschäftigte) and for anybody in the industries
listed in §2a SchwarzArbG, the employer must record the **start, end and
duration** of daily working time **within seven days**, and keep it for **two
years**. Fines to €30,000 (§21).

| | |
|---|---|
| **Does** | Records exactly those three things. |
| **Does not** | Know which employees are minijobbers, enforce the seven-day deadline for them, or flag a record entered late. |

A kindergarten with one 556-€ Minijob cleaner is inside this rule, and the
seven-day deadline is stricter than anything else here. If any employee is a
minijobber, **this is the deadline to implement first** — it is the one with a
number attached.

---

## 4. BUrlG — Bundesurlaubsgesetz (annual leave)

### §3 — the minimum

24 working days on a six-day week; 20 on a five-day week.

| | |
|---|---|
| **Does** | `full_time_leave_days` defaults to 30 and the help text names 20 as the statutory floor. `statutory_leave_days` (default 20) records how much of that total is the protected part, scaled pro rata by working days in `OrgSettings.statutory_days_for` and capped so that it can never exceed the whole. |
| **Does not** | Refuse a setting below the statutory minimum. An administrator can still enter 15, and nothing stops them. |

### §4/§5 — waiting period and part-year entitlement

Full entitlement after six months (*Wartezeit*). Before that, and for somebody
joining in the second half of the year or leaving in the first half, one twelfth
per full month of employment (*Teilurlaub*, §5).

| | |
|---|---|
| **Does** | Holds `started_on` and `ended_on`, and never counts a day outside employment. |
| **Does** | Compute *Teilurlaub*. `Employee.leave_days_in_year` clips the year to the employment and weights the entitlement by the proportion covered, so a joiner in October is now shown roughly a quarter of a year rather than a full one. It also weights across a mid-year **contract change**, which the older single-set-of-columns model could not express at all. |
| **Does not** | Model the six-month *Wartezeit* of §4 as a distinct state. The app shows the pro-rata figure from day one rather than nothing for six months and everything afterwards. That is the shape most small employers actually operate, and it is more generous than §4 requires — but it is not §4. |
| **Does not** | Round by *whole months*. §5 says one twelfth per full month; this weights by days. The two differ by at most a day and the rounding setting absorbs most of it, but for a contested final settlement the day-weighted figure is not the statutory one. |

### §7(2) — leave should be contiguous

If split, one part must be at least 12 consecutive working days where the
entitlement exceeds that.

| | |
|---|---|
| **Does not** | Anything. Not obviously a software duty, but a report would help. |

### §7(3) + the *Hinweispflicht* — **and this one is a trap**

Leave must be taken in the calendar year; carry-over to 31 March only for urgent
operational or personal reasons.

But: **BAG 19.02.2019 – 9 AZR 541/15** and **BAG 20.12.2022 – 9 AZR 266/20**
(following ECJ C-684/16, Max-Planck) hold that leave does **not** expire unless
the employer has *specifically and in good time* told the employee how many days
they have left and that the days will lapse if not taken. Without that notice,
the entitlement rolls forward — and **BAG 20.12.2022 – 9 AZR 266/20** further
held that the three-year limitation period does not even begin to run until the
employer has fulfilled that duty.

| | |
|---|---|
| **Does** | Model carry-over properly. `apps/absences/carryover.py` holds a `LeaveCarryOver` row per person per year, recording how many days came forward, split into the **statutory** part and the **employer's extra**, each with its own deadline (31 March and 31 December by default, both configurable). |
| **Does** | Record the notice. `notice_given_on` is the date the employee was told what was left and that it would lapse. **`expires_statutory` is gated on it**: without a date, the statutory days do not expire — the app treats the deadline as not biting rather than dropping the days. `expire_due` skips those rows and the year-end page reports them as "no reminder sent". |
| **Does** | Assume the employee spent the **perishable** pot first, so the protected statutory days are drawn down before the contractual extra. The other order would let protected days lapse while the extra sat safe. |
| **Does** | Let a manager extend one person's deadline for special circumstances, with a written reason that is required and recorded against the row (`extend`). Refuses to move a deadline on days that have already been forfeited, because that would erase the record of when they went. |
| **Does** | Keep closing a year and expiring its days as two separate acts, months apart, and refuse to expire before the deadline has actually passed. |
| **Does not** | *Send* the notice. The app records that it was sent and by when; it does not e-mail anybody. Somebody still has to do it and then type the date in. |
| **Does not** | Distinguish "urgent operational or personal reasons" from an ordinary carry-over. Everything left over carries; §7(3) strictly permits it only for those reasons. This errs in the employee's favour and matches what most small employers do in practice. |
| **Does not** | Model the three-year limitation period, which under **9 AZR 266/20** does not begin to run until the notice duty has been met. Days simply stay on the row until they are taken or written off. |

The consequence has changed and is worth stating plainly. **An employer who
records no reminder date will find that nothing lapses — which is the legally
correct answer, and now the app's answer too.** The liability is still real, but
it is now visible: the year-end page names every person whose days cannot expire
because nobody was told. The previous version of this document called
"no carry-over rules" a standing decision made on complexity grounds; that
decision has been reversed, and the reason is that *not* modelling it was not
neutral — an app that silently dropped everything at midnight on 31 December was
asserting a policy, and the wrong one.

### §9 — falling ill during leave

Days covered by a medical certificate are **not** counted against leave.

| | |
|---|---|
| **Does not** | Handle it. Sickness overlapping an approved holiday is refused outright by the overlap check in `AbsenceRequestForm`, which is the wrong answer — the correct one is to give the days back. |

### §11 — holiday pay, §7(4) — payment in lieu on termination

Out of scope: this app reports hours and does not compute money.

---

### The half day

Not a statute, but it belongs here because the arithmetic is the same:
`Absence.is_half_day` costs half a working day of entitlement and credits half
the contracted hours, through one `portion_of` so the two readings cannot
diverge. It is restricted to a single date; a half day at either end of a longer
range is entered as a second absence.

---

## 5. EFZG — continued pay in sickness

Six weeks (42 calendar days) at full pay, per illness (§3). Recurrence of the
*same* illness restarts the clock only after six months free of it, or twelve
months from the first occurrence. Notification is immediate; a certificate is
due from the fourth day, earlier if the employer demands it (§5). Since 2023 the
certificate arrives electronically (**eAU**) — the employer retrieves it from
the health insurer and the employee no longer hands over paper.

| | |
|---|---|
| **Does** | Records sick days, self-reported, approved on arrival, costing no leave. Counts them per year. |
| **Does not** | Track the six-week entitlement, distinguish one illness from another, or know about certificates at all. |

**Not tracking certificates is deliberate and should stay that way.** A
diagnosis, or a document implying one, is Art. 9 DSGVO health data and this app
has no lawful basis to hold it. The eAU flow keeps that data between the doctor,
the insurer and payroll, which is where it belongs. What the app *could* add
without touching health data is the 42-day counter, since it already knows the
dates.

---

## 6. TzBfG — part-time

§4 is the *pro rata temporis* principle: a part-timer may not be treated worse
than a comparable full-timer except where objectively justified.

| | |
|---|---|
| **Does** | This is the legal basis for the app's most important arithmetic decision. Leave is scaled by **working days, never by hours** — somebody on three ten-hour days gets the same number of days off as somebody on three six-hour days. Scaling by hours would give the second person fewer, which is exactly the §4 discrimination case. Pinned by `test_the_same_days_gets_the_same_leave_however_short`. |
| **Note** | §12 (*Arbeit auf Abruf*) is not modelled: if no weekly hours are agreed, 20 h/week is deemed, shifts need four days' notice, and a call-out is at least three consecutive hours. The app requires a contract with hours in it, which sidesteps most of this. |

---

## 7. JArbSchG — young people under 18

Very relevant: a kindergarten with an *Auszubildende* or a *Praktikantin* under
18 is inside this act, and its limits are tighter than the ArbZG's.

- Max 8 h/day and 40 h/week; no more than five days a week.
- Breaks: 30 minutes for 4½–6 hours, **60 minutes for more than 6** — double the
  adult rule.
- Rest: 12 hours, not 11.
- No work before 06:00 or after 20:00; no Saturdays or Sundays (with listed
  exceptions).
- Leave graduated by age at the start of the calendar year: **30** working days
  under 16, **27** under 17, **25** under 18.

| | |
|---|---|
| **Does** | Nothing. There is no date of birth on `Employee` and no concept of a young worker. |
| **Does not** | Apply any of the above. A 17-year-old apprentice would be given the adult break table and the adult leave entitlement, both of which are wrong. |

If anybody under 18 is ever entered, **every figure the app produces for them is
wrong.** That is worth a guard rail even before the full rules: a date of birth
and a refusal would be honest.

---

## 8. The other entitlements

| Act | Duty | App |
|---|---|---|
| **MuSchG** | 6 weeks before / 8 (12) after birth; max 8½ h/day; no night, Sunday or holiday work; leave preserved and carried into the year after return (§24) | Nothing |
| **BEEG** | Elternzeit up to 3 years; employer **may** reduce leave by 1/12 per full month (§17); part-time up to 32 h/week during it | Nothing |
| **SGB IX §208** | **Five extra paid leave days** a year for employees with a *Grad der Behinderung* ≥ 50, pro rata by working days | Modellable as a `SpecialLeaveType` in PRO_RATA mode **today**, and that is the right way to do it — but see the warning below |
| **PflegeZG / FPfZG** | Up to 10 days' short-term care leave; longer periods | Modellable as a special leave type |
| **Bildungszeitgesetze der Länder** | Education leave, varies by Land (Baden-Württemberg: 5 days/year) | The seed's "Fortbildung" type is exactly this |
| **§616 BGB** | Short paid absence for personal reasons, frequently excluded by contract | Modellable as a special leave type |

**The SGB IX warning.** A special leave type named "Schwerbehinderung" makes the
grant list on somebody's contract a record of their disability status — Art. 9
DSGVO special category data, visible to every manager who can open the Employees
page. If that entitlement is granted here, name the type something neutral
("Zusatzurlaub") and be aware that the *inference* is still available to anybody
who knows the rule. The lawful, boring alternative is to fold the five days into
`leave_days_override` and keep the reason out of the app entirely.

---

## 8a. Summer time, and the hour that does not exist

Not named in any statute, and it decides what somebody is paid twice a year.

The clocks move on the last Sunday in March and of October. A shift rostered
23:00–07:00 across the March night is **seven** hours — 02:00 becomes 03:00 and
the hour between never happens. Across the October night it is **nine**. A
wall-clock subtraction says eight both times, which overpays an hour every
spring and short-pays an hour every autumn.

| | |
|---|---|
| **Does** | Measure every span between two *instants* rather than two clock readings (`apps/timesheets/zones.py`), so both nights come out at what was actually worked — and the break tiers, which are computed from that span, follow. |
| **Does** | Refuse a clock time the spring-forward skipped. 02:30 on that morning is not a time that happened, and a shift claiming to start then is a shift measuring an hour short. Python resolves it silently, so the form is the only place anybody finds out. |
| **Does** | Accept the repeated October hour as ordinary, taking the first of the two. No paper timesheet has ever distinguished them either. |
| **Does** | Keep a per-employee zone for somebody who works in another country, and file their clocked start under the date it is *there*. |
| **Does not** | Distinguish the two occurrences of the repeated hour. Somebody who worked 02:00–02:30 twice over is recorded once. |

---

## 8b. §3 EFZG and §11 BUrlG on the timesheet — credited hours

The app now credits the contracted hours for a day of sickness, a day of leave,
a public holiday and an employer closure, so that a week containing them comes
out level rather than showing a shortfall.

| | |
|---|---|
| **Does** | Credit at the contracted hours for the day, halved for a half day (`Absence.credited_minutes`). The credited figure is kept in its own column beside the worked one, so a timesheet can still say "you were ill" and "you worked eight hours" as different sentences. |
| **Does** | Credit a reported sick day **immediately**, before any manager has acknowledged it. Illness is a fact, not a permission; waiting for a button would show a fortnight's flu as eighty hours of shortfall for as long as the manager was away. Only a positive refusal, with a written reason, withholds the credit. |
| **Does not** | Credit time off in lieu, deliberately — that shortfall *is* the overtime being taken back. |
| **Does not** | Use the §11 BUrlG *Lohnausfallprinzip* reference period (the last thirteen weeks' average earnings). It credits the **contracted** hours, which is the right figure for an hours report and not necessarily the right one for a payslip. This app reports hours; it does not run payroll. |

---

## 9. DSGVO / BDSG — data protection

A time tracking system is employee monitoring and is squarely inside this.

| Article | Requirement | App |
|---|---|---|
| **Art. 5(1)(c)** | Data minimisation | Good. No uploads, no e-mail addresses (removed), no reason field on sickness, no location, no device data. |
| **Art. 5(1)(e)** | Storage limitation | **Absent.** Nothing is ever deleted or anonymised. Working time records may be kept 2 years (ArbZG/MiLoG); payroll-relevant records fall under §28f SGB IV and §147 AO, which push to 6 years and beyond. Somebody has to decide the number and the app has to enforce it. |
| **Art. 6(1)(c) / §26 BDSG** | Lawful basis | Legal obligation (ArbZG, MiLoG) plus performance of the employment contract. Note that ECJ C-34/21 cast doubt on §26 BDSG(1) as a standalone basis; the ArbZG duty is the safer footing. |
| **Art. 9** | Health data | Sickness *dates* are attendance data and are fine. **Diagnoses, certificates and disability status are not**, and the app must stay out of them — see EFZG and SGB IX above. |
| **Art. 15** | Right of access | Partly. An employee can see their own timesheet and balance in the app; there is no export. |
| **Art. 30** | Record of processing activities | The employer's job, not the app's, but it needs writing. |
| **Art. 32** | Security of processing | Sessions, CSP, encrypted OIDC secret, SSO, per-view authorisation. **No audit log.** |
| **Art. 35** | Data protection impact assessment | Systematic monitoring of employees is on most supervisory authorities' DPIA blacklist. **Assume one is required** before this goes live. |

---

## 10. BetrVG — the works council

If there is a *Betriebsrat*, this is not optional and it is not a formality.

- **§87(1) Nr. 2** — start and end of daily working time, breaks, and the
  distribution of hours across days: mandatory co-determination. The roster is
  precisely this.
- **§87(1) Nr. 3** — temporary shortening or extension of working time.
- **§87(1) Nr. 6** — the introduction and use of **technical devices suited to
  monitoring the behaviour or performance of employees**. A time tracking system
  is the textbook example. Note "suited to": it does not matter whether anybody
  intends to monitor.

The practical consequence: **introducing this app without a Betriebsvereinbarung
is unlawful where a works council exists**, and anything recorded in the interim
may be unusable as evidence. BAG 1 ABR 22/21 removed the council's right to
*demand* time recording (it is already required) but not their say in how.

Nothing in the code addresses this. It is listed because it is the step most
likely to be skipped, and the only one that can invalidate everything else.

---

## 11. Evidence, and the one thing worth building next

**BAG 04.05.2022 – 5 AZR 359/21** held that the CCOO ruling does *not* reverse
the burden of proof in an overtime claim: an employee must still show both that
the hours were worked and that the employer ordered, tolerated or needed them.

That makes this app's separation of **rostered / entered / confirmed** genuinely
valuable rather than merely tidy — it is the difference between "I say I worked
late" and "I was asked to work these hours, I recorded these, and here is who
agreed to them and when". `apps/roster/models.py` argues for the separation on
design grounds; this is the legal argument for the same thing.

What undermines it is the missing audit trail. A confirmed day can be edited and
the record keeps only the *current* values plus the fact that the confirmation
lapsed. In a dispute, "this is what it says now" is a much weaker document than
"this is what it said, and here is every change to it".

---

## Priorities, if this is going to be used for real

Ordered by how much trouble each one causes, not by effort. Items struck through
have since been done; they are kept rather than deleted so that the list reads as
a history of what was decided and not only as a to-do.

1. **Betriebsrat and DPIA** — process, not code, and both block go-live. Still
   the first two things, and neither has moved.
2. **A retention policy.** Pick the number, then make the app enforce it in both
   directions. Right now it neither keeps nor deletes deliberately. This is now
   the largest gap in the code.
3. **An audit trail on `DayRecord` and `WorkSegment`** — who changed what, from
   what, when. It is the difference between a record and a claim. It has grown
   more important, not less: `ContractPeriod` and `LeaveCarryOver` both now
   record *their* history, which makes the timesheet's silence about its own the
   conspicuous exception.
4. ~~**Wartezeit and Teilurlaub** (§4/§5 BUrlG).~~ **Done for Teilurlaub.**
   `Employee.leave_days_in_year` clips to the employment and weights by the part
   of the year covered, so an October joiner is shown roughly a quarter of a year.
   The six-month Wartezeit of §4 is still not modelled as a distinct state, and
   the weighting is by days rather than by whole months — see §4/§5 above.
5. ~~**The §7(3) notice.**~~ **Done.** `apps/absences/carryover.py` implements
   the Hinweispflicht *and* carry-over together, which is what "half of it is
   worse than none" meant: `notice_given_on` gates whether the deadline bites at
   all, so an employer with no record of the reminder finds that nothing lapses.
   What is still missing is *sending* the reminder — the app records that it went
   out and does not put it in anybody's inbox.
6. **The 11-hour rest check** (§5 ArbZG). Small, and the arithmetic already
   exists — more so now that `zones.elapsed_minutes` measures real elapsed time
   between instants, which is exactly what a rest period is.
7. **A daily-hours warning** at 8 h and a refusal at 10 h, plus the 24-week
   average (§3 ArbZG).
8. **A guard on under-18s** (JArbSchG) — at minimum, a date of birth and a
   refusal, since every figure is currently wrong for them.
9. **Sickness during leave** (§9 BUrlG) — give the days back instead of refusing
   the overlap. The half-day machinery makes this easier than it was: the
   absence can now be worth a fraction of a day without a second model.
10. **The MiLoG seven-day deadline**, if any employee is a minijobber. Move this
    to the top if so.
11. **The six-hours-consecutive break rule** (§4 ArbZG), which needs breaks to
    have a *position* in the day and not just a length.
12. **A minimum on the statutory leave setting.** `statutory_leave_days` can now
    be set below the §3 BUrlG floor and nothing stops it, exactly as the break
    table can be set looser than §4 ArbZG. Both are the same shape of gap and
    should be fixed together.
13. **The two occurrences of the repeated October hour.** Recorded as one. It
    affects one shift a year in businesses that roster that night at all, and
    fixing it means storing an instant rather than a clock reading — which is a
    trade the rest of the app has deliberately not made.
