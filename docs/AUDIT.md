# Who audits a German time-tracking system, and what they ask it for

**Engineering notes, not legal advice.** `docs/COMPLIANCE.md` is the companion to
this file and the two do different jobs. That one asks *what does the law require
of the employer, and what does the app do about it*. This one asks the question a
buyer in a corporate environment actually asks: **who is going to turn up, what
standard will they hold this to, and what will they want out of the software on
the day.** The distinction matters, because the two lists are not the same. A rule
can be fully implemented and still fail an audit, for the single reason that
nobody can *demonstrate* it was implemented on the day the record was written.

Same three columns as the compliance notes: what is required, what the app does,
what it does **not**. The third is still the useful one.

---

## 0. The first thing to get straight: there is no licence

Germany does not certify time-tracking software, and no authority approves one
before it may be used. There is no equivalent of the *Kassensicherungsverordnung*
regime — no certified TSE, no BSI *Technische Richtlinie*, no registration.
Anybody selling "the only officially certified Zeiterfassung" is selling a
privately issued attestation, not a permission.

What exists instead is four different things that all get called "certification",
and a corporate buyer usually means one of them without saying which:

| What people say | What it actually is | Who issues it | Compulsory? |
|---|---|---|---|
| "GoBD-zertifiziert" | Nothing. The BMF says outright that it certifies no software and that no certificate binds a tax auditor. | — | No, and it means nothing |
| "GoBD-Testat", "Softwarebescheinigung" | An audit against **IDW PS 880** by a *Wirtschaftsprüfer*, ending in a report and a certificate with an expiry date | An audit firm | No — but it is what large customers ask to see |
| "Revisionssicher" | A property, not a document: a record cannot be changed without the change itself being recorded | The design of the software | The property is required; the word is marketing |
| "Verfahrensdokumentation" | The employer's own written description of the process, **required by the GoBD** | The employer, with the vendor's input | **Yes** |

The honest summary: **the compulsory artefacts are the Verfahrensdokumentation,
the DPIA, and — where there is a works council — the Betriebsvereinbarung. Every
certificate is optional, and none of them is a defence.** What actually gets
inspected is the data and the process, by the bodies below.

---

## 1. Who turns up

### 1.1 FKS — Finanzkontrolle Schwarzarbeit (the Zoll)

The one that arrives unannounced. Under §2 SchwarzArbG the customs authority
checks compliance with MiLoG, AEntG and AÜG, and under **§17 MiLoG** it demands
the working-time records for anybody who is *geringfügig beschäftigt* or works in
one of the §2a SchwarzArbG industries. It may inspect on the premises, on the
spot.

| | |
|---|---|
| **Requires** | Start, end and **duration** of each day, recorded **within seven calendar days** of the day worked, kept **two years**, held **in Germany**, **in German**, produced on demand. §21 MiLoG: fines to €30,000. |
| **Does** | Records exactly those three figures per day and keeps them indefinitely. German is the default language of the interface and of the data. The database is one SQLite file on the employer's own NAS, which is trivially "in Germany". |
| **Does not** | Know which employees are minijobbers, enforce the seven-day deadline for them, flag a record entered late, or produce a printable or exportable record for an inspector standing at a desk. **An inspector asking for "the records for these four people for last year" has to be shown the screen, a month at a time.** |

The seven-day deadline is the strictest number anywhere in this file and the
easiest to fail, because failing it is invisible: the record looks identical
whether it was written on the day or six weeks later. The app does not store
*when* a day's hours were entered as distinct from when the row was last touched.

### 1.2 DRV — the Betriebsprüfung under §28p SGB IV

Every employer, every four years, by the *Deutsche Rentenversicherung*. The
auditor reconciles the payroll against the working-time records: this is how
underpaid minimum wage, unrecorded overtime and misclassified minijobs are found,
because the hours and the money have to agree.

| | |
|---|---|
| **Requires** | The *Entgeltunterlagen* of §8 BVV, which since 2022 must be kept **electronically** and under §9 BVV must be **maschinell auswertbar** — machine-evaluable, not a stack of screenshots. Kept until the end of the calendar year following the last audit. |
| **Does** | Holds the hours per person per day in a relational database, with the contract history beside them, so that "what were they contracted to work that month" reproduces for a past month rather than being answered with today's contract. |
| **Does not** | Export anything. "Machine-evaluable" is precisely what a screen is not. |

### 1.3 The Finanzamt — Außenprüfung, and the GoBD

Working-time records feed the *Lohnkonto* (§41 EStG, §4 LStDV), and that makes
them tax-relevant records inside the scope of the **GoBD** (BMF-Schreiben of
28.11.2019, revised 11.03.2024). This is the standard with the most to say about
how the software is built, and section 2 goes through it line by line.

| | |
|---|---|
| **Requires** | §§145–147 AO: orderly, complete, correct, timely, ordered and **unalterable** records; the *Verfahrensdokumentation*; retention; and **Datenzugriff** in three forms — Z1 direct read access to the system, Z2 the auditor asking the employer to run evaluations, Z3 handing the data over on a medium in an evaluable format. |
| **Does** | Keeps the data in one relational file with a per-person, per-day shape an auditor would recognise, and can grant a read-only account for Z1. |
| **Does not** | Satisfy **Unveränderbarkeit** (nothing records what a value was before it changed), **Datenzugriff Z3** (no export), or **Verfahrensdokumentation** (does not exist yet). Three of the GoBD's headline requirements, and the first is the one the whole standard is built around. |

Retention is not one number. **2 years** under ArbZG §16(2) and MiLoG §17;
**6 years** for the *Lohnkonto* and the *Arbeitszeitlisten* that support it
(§41 EStG / §4 LStDV, §147(3) AO); **8 years** for *Buchungsbelege* since the
Bürokratieentlastungsgesetz IV shortened it from ten with effect from 1 January
2025; and for social-insurance records *until the end of the calendar year
following the last audit* — a date nobody can compute in advance. An app that
wants to be right here keeps to the longest applicable period and then deletes,
because the DSGVO makes the maximum as binding as the minimum.

### 1.4 The Arbeitsschutzbehörde (Gewerbeaufsicht)

§17 ArbZG gives the *Aufsichtsbehörde* the right to demand the records and to
enter the workplace. It is looking at something different from everybody else:
not whether the hours were paid, but whether they were **lawful** — §3 (eight
hours, ten by exception, averaged over 24 weeks), §4 (breaks), §5 (eleven hours'
rest), §9 (Sundays).

| | |
|---|---|
| **Requires** | Records of working time beyond eight hours a day, kept two years — and in practice an answer to "show me the compensating weeks for this run of ten-hour days". |
| **Does** | Computes and enforces the break of §4 correctly, including the second sentence about six hours worked consecutively, which most implementations get wrong. Measures a span between two *instants*, so a night shift across a clock change comes out at its true length. |
| **Does** | Flag a day over eight hours, a day over the ten-hour ceiling, and a rest period under eleven hours, on the row and in the month's footer — see `apps/timesheets/limits.py`. **Flags, never refuses**: §16 ArbZG asks for a record of the time actually worked, and software that refused to record an unlawful day would be destroying the only evidence that it happened. |
| **Does not** | Compute the 24-week average that decides whether the ten-hour days were lawful, or model the §7 collective-agreement exceptions that can displace both limits. |

### 1.5 The Datenschutzaufsicht

A time-tracking system is systematic processing of employee data suited to
monitoring behaviour and performance. The DSK's *Muss-Liste* under Art. 35(4)
DSGVO puts extensive processing of employee data capable of behavioural or
performance control on the list requiring a **Datenschutz-Folgenabschätzung**.

| | |
|---|---|
| **Requires** | A DPIA before go-live (Art. 35), a *Verzeichnis von Verarbeitungstätigkeiten* (Art. 30), technical and organisational measures (Art. 32), data minimisation (Art. 5(1)(c)), **storage limitation with a real deletion concept** (Art. 5(1)(e)), and the ability to answer an access request with a copy of the data (Art. 15(3)). |
| **Does** | Data minimisation, unusually well and deliberately: no uploads at all, no diagnosis field, no location, no device data, no performance scoring. Authorisation is per-view and tested by a suite that walks the whole URLconf. The OIDC secret is encrypted at rest. |
| **Does not** | Delete anything, ever. Produce a copy of one person's data on request. Log who *read* whose timesheet — which matters here more than usual, because "the manager looked at my hours" is exactly the processing a works council asks about. |

The DPIA and the Art. 30 record are the employer's documents, not the app's, but
neither can be written without the app describing itself. That description is the
same document the GoBD calls the *Verfahrensdokumentation*, which is why writing
it once discharges two duties.

### 1.6 The Betriebsrat

Where one exists, **§87(1) Nr. 6 BetrVG** makes the introduction and use of
technical devices *suited to* monitoring behaviour or performance subject to
mandatory co-determination — "suited to", not "intended to", so intent is no
defence — and **§87(1) Nr. 2 and 3** cover the roster itself. **§80(2)** gives the
council a right to the information it needs, which in practice means a read-only
view.

Without a *Betriebsvereinbarung*, introducing this app in a co-determined
workplace is unlawful, and records made in the interim may be unusable as
evidence. Nothing in the code addresses this and nothing in the code can. It is
listed because it is the step most often skipped and the only one that
invalidates everything else.

### 1.7 The Arbeitsgericht

Not an auditor, but the reader whose opinion matters most. **BAG 4.5.2022 –
5 AZR 359/21** held that the CCOO ruling does not reverse the burden of proof in
an overtime claim: the employee must still show that the hours were worked *and*
that the employer ordered, tolerated or needed them.

Which is exactly what this app's separation of **rostered / entered / confirmed**
is for — not tidiness, but the difference between "I say I worked late" and "I was
asked to work these hours, I recorded these, and here is who agreed and when".
What undermines it is the missing edit history. A confirmed day that can be
silently rewritten afterwards is a claim, not a document, and in front of a court
that distinction is the case.

### 1.8 The Wirtschaftsprüfer — IDW PS 880, and the voluntary attestations

If a corporate customer asks for "the certificate", this is what they mean.

- **IDW PS 880** — *Erteilung und Verwendung von Softwarebescheinigungen*. An
  auditor examines the processing functions, the software's security and its
  documentation, and issues a *Softwarebescheinigung* saying that the product,
  **properly applied**, permits accounting that complies with the GoBD. It is
  time-limited and has to be repeated. It is a recommendation, not a statute, and
  it binds no tax auditor — but it is the artefact procurement asks for.
- **IDW RS FAIT 1 / 3** — the underlying position papers on IT in accounting and
  on electronic archiving. What PS 880 is measured against.
- **IDW PS 951 / ISAE 3402** — for the *operator* rather than the software, if it
  is ever hosted for somebody else. Not applicable while every customer runs their
  own container.

**Two things about PS 880 are worth knowing before anybody commissions one.**
First, the auditor tests the documentation as a deliverable in its own right — no
Verfahrensdokumentation, no certificate, and that is the item this project does
not have. Second, PS 880 is emphatically about *Unveränderbarkeit* and the journal
function: a system that overwrites a value in place with no record of the prior
value does not pass. Both of the gaps that block a PS 880 are the same two gaps
the tax auditor, the labour court and the works council each arrive at from their
own direction. That convergence is the useful finding in this whole document.

### 1.9 Corporate procurement — ISO 27001, TISAX, BSI IT-Grundschutz, C5

Not audits of the software but of the *organisation running it*, and a corporate
buyer passes the questionnaire down. The parts that land on the app:

- **ISO/IEC 27001 A.5.15–A.5.18** — access control, privileged access, removal of
  rights on leaving. Partly there: roles are split into manager and staff and both
  are tested from either side. Missing: any record of *who was granted what, when*.
- **A.8.15 Logging** — event logs of user activities, exceptions and security
  events, protected against tampering. Sign-ins are logged to a **rotating file
  with three backups**, which is to say they are deleted after roughly eight
  megabytes. That is not a log an auditor accepts.
- **BSI IT-Grundschutz APP.3.1 / CON.8** — web application and secure development.
  The CSP with no nonce, the absence of any upload path, and the URLconf-walking
  authorisation tests are all strong answers here.
- **BSI C5** — cloud only. Not applicable to a container on the customer's own NAS,
  and worth saying so in a questionnaire rather than leaving the row blank.

---

## 2. The GoBD, criterion by criterion

The BMF's own headings, in its own order, with what this app does about each.
The closest thing to a pass/fail sheet that exists.

| GoBD criterion | What it means in practice | App |
|---|---|---|
| **Nachvollziehbarkeit / Nachprüfbarkeit** (Rz. 30–36) | A knowledgeable third party must be able to follow the records in reasonable time, from the individual entry to the total and back — the *progressive* and *retrograde* trail | **Partly.** The month adds up on the page, every figure derives from stored minutes, and `build_month`/`build_week` are one implementation so two pages cannot disagree. But there is no trail from a figure to *who wrote it and when*, and no Verfahrensdokumentation to follow it with. |
| **Vollständigkeit** (Rz. 36–43) | Every transaction recorded, none missing, none twice | **Good.** One row per person per day, enforced by a unique constraint. A date with no row is deliberately distinguishable from a day of nought hours, which is the completeness question actually asked. |
| **Richtigkeit** (Rz. 44) | Records reflect the facts | **Good, unusually so.** Clocking does not round. Times are read however they are typed and normalised on screen before saving. A span is measured between instants, so the two nights a year the clocks move come out right. |
| **Zeitgerechte Erfassung** (Rz. 45–53) | Recorded without delay; a record made much later is suspect | **Weak.** Hours on a future day are refused, which is the right half of the rule. The other half — *how late was this entry* — is not recorded. `created_at` is the row's creation, not the day's entry, and a row created for a comment in March can gain January's hours in April with nothing to show it. |
| **Ordnung** (Rz. 54–59) | Systematically arranged, findable | **Good.** Per person, per date, indexed, with the month as the unit somebody reads. |
| **Unveränderbarkeit** (Rz. 107–112) | A record once made may not be changed so that the original content is no longer ascertainable. Changes are permitted; **silently overwriting is not.** Log who, when, from what, to what | **Absent, and this is the finding.** `DayRecord` fields are updated in place. A locked month cannot be changed and `DayLock` records who locked it and when — but unlocking is one click, and after it the edit is invisible. Editing hours withdraws the confirmation, which shows *that* something changed and never *what*. |
| **Aufbewahrung** (Rz. 115–125) | For the statutory period, readable and available throughout | **Partly.** Nothing is ever deleted, which meets the minimum by accident rather than by policy and breaches the DSGVO maximum for the same reason. |
| **Maschinelle Auswertbarkeit** (Rz. 126–128) | The data must stay sortable and filterable by the auditor, not merely printable | **Partly.** The database is relational and would satisfy this through Z1, but there is nothing to hand over. |
| **Datenzugriff Z1 / Z2 / Z3** (Rz. 158–179) | Direct read access / evaluations run for the auditor / **data handed over on a medium** | **Z1 possible** with a read-only account. **Z2 by hand.** **Z3 absent** — there is no export, and Z3 is the form auditors most often choose. |
| **Internes Kontrollsystem** (Rz. 100–102) | Access rules, separation of duties, controls that the process was followed, and evidence they ran | **Partly.** Roles are separated and tested from both sides, the lock is enforced at every door *and* at the model, and both confirm routes refuse a running day. What is missing is evidence: no record of a control having been exercised. |
| **Datensicherheit** (Rz. 103–106) | Loss and unauthorised change must be prevented; backup must be demonstrable | **Partly.** SSO, CSP without a nonce, encrypted secret, per-view authorisation, HSTS, secure cookies. Backup is Hyper Backup on the NAS, which is real but is nowhere described — and an undescribed backup does not count. |
| **Verfahrensdokumentation** (Rz. 151–157) | Four parts: general description, user documentation, technical system documentation, operating documentation — plus a **history of its own versions** | **Absent as such.** The material largely exists — `CLAUDE.md`, `docs/COMPLIANCE.md`, `DEPLOYMENT.md`, `README.md` — but it is written for the next developer, not for an auditor, and the GoBD asks for a specific four-part structure with a change history. The cheapest large win in this document. |

---

## 3. What is coming: the ArbZG amendment

A **Referentenentwurf from the BMAS, mid-June 2026**, would put an explicit
electronic recording duty into the ArbZG. There was no cabinet decision as of
late August 2026, so none of this is law and the detail will move. The direction
will not.

| Draft provision | What the app would need |
|---|---|
| Beginn, Ende **und Dauer** recorded **electronically** | Already done. |
| **On the day the work is performed** (*am Tag der Arbeitsleistung*) | **New.** Record *when* an entry was made, and surface a day recorded late. This is the MiLoG seven-day rule arriving for everybody. |
| Kept **two years** | A retention policy that also stops there where nothing longer applies. |
| Employees may **request information and a copy** of their records | **New, and it reverses this project's "no export" standing decision.** A right to a copy is not a feature request. |
| Vertrauensarbeitszeit permitted, but the employer must have measures that **detect** breaches of maximum hours and rest periods | **Half done.** The per-day §3 and §5 flags are in; the 24-week average of §3(1) is not, and it is the half that decides whether a ten-hour day was lawful. |
| Employer may **delegate** recording to employees, stays responsible, must spot-check | Already the model. A "days nobody has answered for" view for managers would be the spot-check. |
| Under 10 employees exempt from the electronic form; transition of 1 / 2 / 5 years by size | Nothing to build. Relevant to who has to hurry. |
| Breaches of the recording, information and retention duties become fineable | Raises the price of every gap above. |

---

## 4. What has to change

Ordered by how much trouble each causes, not by effort. The first three appear in
more than one auditor's column, which is what makes them worth doing first.

1. **An audit trail on every record that is evidence.** Who changed what, from
   what value to what, when. Append-only, never edited, never rotated away.
   Required by GoBD *Unveränderbarkeit*, expected by IDW PS 880, asked for by
   ISO 27001 A.8.15, and the difference between a document and a claim in front of
   a labour court. **The single item that appears in every column of this file.**
2. **An export.** Per employee and per period, in a machine-evaluable format, plus
   a printable record. Discharges GoBD Datenzugriff Z3, the DRV's §9 BVV
   *maschinelle Auswertbarkeit*, an FKS inspector at a desk, DSGVO Art. 15(3) and
   the employee's right to a copy in the draft ArbZG. Five duties, one feature. It
   reverses a standing decision, deliberately.
3. **A retention policy, enforced in both directions.** Pick the number per class
   of record — 2 years ArbZG/MiLoG, 6 years for what supports the Lohnkonto,
   longer where the employer says so — resist deletion before it, erase after it.
   The app currently neither keeps nor deletes deliberately, which is the wrong
   answer to the AO and the DSGVO at the same time.
4. **Recording *when* an entry was made**, distinctly from when the row was last
   touched. The GoBD's *Zeitgerechtheit*, the MiLoG's seven days and the draft
   ArbZG's *am Tag der Arbeitsleistung* are one field and one report.
5. **The 24-week average of §3 ArbZG.** The per-day flags landed with
   `apps/timesheets/limits.py`; the averaging window that decides whether a run of
   ten-hour days was lawful did not, and it is the half an Arbeitsschutz inspector
   actually asks for.
6. **A Verfahrensdokumentation** in the GoBD's four parts, with its own version
   history. The material mostly exists and needs restructuring for a different
   reader.
7. **A durable security log.** Sign-ins, refusals, permission changes, locks and
   unlocks, exports — to something other than a file rotated away after eight
   megabytes.
8. **A read log for cross-employee access.** Who looked at whose timesheet. The
   works council will ask, and it is the one piece of processing this app does
   that the people recorded in it cannot see.
9. **Minijob status on the employee**, so the seven-day MiLoG deadline can be
   enforced for the people it applies to and nobody else.
10. **The process artefacts, which are not code and block go-live anyway**: the
    DPIA, the Art. 30 record, and the Betriebsvereinbarung where there is a works
    council.

---

## 5. What already answers well

Worth knowing, because an audit is a conversation and half of it is being able to
say what was decided and why.

- **The roster and the timesheet are separate tables**, so "what were you asked to
  work" and "what did you work" are both answerable and can differ. This is the
  evidentiary structure BAG 5 AZR 359/21 makes valuable.
- **Clocking does not round**, in either direction.
- **Spans are measured between instants**, so the two nights a year the clocks move
  are right, and a test names those two nights.
- **The break rules implement both sentences of §4 ArbZG**, including the one about
  six hours worked consecutively that most implementations miss, and the
  resolution is pinned from three sides by tests.
- **An overridden break is never recomputed and is always drawn in amber**, so a
  typed figure and a computed one are visibly different to whoever signs off.
- **A correction is stored apart from the bookings and always carries a reason**,
  refused in `clean` as well as in both forms — so no figure on a timesheet is
  unaccounted for.
- **The contract is a history**, so a month reprinted a year later reproduces
  against the contract that was in force then.
- **The lock is enforced at every door and again at the model**, and a test sweeps
  the doors rather than naming three of them.
- **The app stores no files and no health data, by design**, and a test walks every
  model and fails on a `FileField`.
- **Authorisation is checked by tests that walk the whole URLconf** rather than by
  trusting that every view remembered its decorator.
- **The daily limits of §3 and the rest period of §5 are flagged and never
  enforced**, which is the right way round: an unlawful day still has to be
  recordable, because the record is the evidence.

Each of those is a question an auditor asks and a sentence that answers it.
Section 4 is what is left.
