"""German for the second pass: clocking in, half days, contract history, year end.

A third table rather than more of the second, on the same reasoning that split
the first two: one file nobody scrolls through is one nobody checks. What is in
here is everything added by the round of work that brought in Start and Stop,
the time zones, half days, the contract as a history, and leave that expires.

The long entries are again the ones that carry the *reasoning*. They matter more
here than anywhere else in the app, because the figures on these pages are the
ones somebody will dispute: why last year's days are still there, why they went,
why the entitlement moved in April. A number nobody can explain is a ticket; a
number with the sentence beside it is a conversation that does not happen.

Two conventions kept from the other tables:

* the polite ``Sie``, because a works notice is not written in ``du``;
* German typographic quotes ``„…“`` and the em dash with spaces, as the German
  strings elsewhere already use.
"""

YEAR_END = {
    # -- carried-over leave, the model ------------------------------------
    "into the year": "in das Jahr",
    "The year these days were carried into, not the year they were earned.":
        "Das Jahr, in das diese Tage übertragen wurden — nicht das Jahr, in dem sie erworben wurden.",
    "statutory days carried": "übertragene gesetzliche Tage",
    "the employer’s extra, carried": "übertragene zusätzliche Tage des Arbeitgebers",
    "statutory days lapse on": "gesetzliche Tage verfallen am",
    "the extra lapses on": "die zusätzlichen Tage verfallen am",
    "they were told on": "informiert am",
    "When they were told what was left and that it would lapse. Without this the statutory days are treated as not expiring at all.":
        "Wann die Person erfahren hat, wie viele Tage offen sind und dass sie verfallen. Ohne dieses Datum gelten die gesetzlichen Tage als nicht verfallend.",
    "why it was extended": "Grund der Verlängerung",
    "Required to move a deadline. It is the only record of why this person’s is different.":
        "Erforderlich, um eine Frist zu verschieben. Es ist der einzige Nachweis, warum die Frist dieser Person abweicht.",
    "statutory days lost": "verfallene gesetzliche Tage",
    "extra days lost": "verfallene zusätzliche Tage",
    "lost on": "verfallen am",
    "carried-over leave": "Urlaubsübertrag",
    "There is no deadline to extend.": "Es gibt keine Frist, die verlängert werden könnte.",
    "Say why. An extension nobody can explain is one nobody can defend.":
        "Bitte begründen. Eine Verlängerung, die niemand erklären kann, kann auch niemand vertreten.",
    "Those days have already lapsed. Grant new days instead — moving the deadline now would erase the record of when they went.":
        "Diese Tage sind bereits verfallen. Gewähren Sie stattdessen neue Tage — die Frist jetzt zu verschieben würde den Nachweis löschen, wann sie verfallen sind.",

    # -- half days ---------------------------------------------------------
    "A half day is one date. Ask for the whole days as one request and the half day as another.":
        "Ein halber Tag ist ein einzelnes Datum. Beantragen Sie die ganzen Tage als einen Antrag und den halben Tag als einen zweiten.",
    "A half day is one date.": "Ein halber Tag ist ein einzelnes Datum.",
    "half a day": "halber Tag",
    "Half of that one day. Only for a single date.":
        "Die Hälfte dieses einen Tages. Nur für ein einzelnes Datum.",
    "A half day is one date. Book the whole days as one absence and the half day as another.":
        "Ein halber Tag ist ein einzelnes Datum. Erfassen Sie die ganzen Tage als eine Abwesenheit und den halben Tag als eine zweite.",
    "half day": "halber Tag",

    # -- sickness as a report, not a request -------------------------------
    "Your manager has already seen that. Ask them to correct the dates.":
        "Ihre Leitung hat das bereits gesehen. Bitten Sie sie, die Daten zu korrigieren.",
    "Recorded, and your manager has been shown it. It counts from now — it does not come out of your leave, the hours are credited, and the days you were not due to work are not counted.":
        "Erfasst, und Ihrer Leitung angezeigt. Es zählt ab sofort — es geht nicht von Ihrem Urlaub ab, die Stunden werden gutgeschrieben, und Tage, an denen Sie nicht eingeteilt waren, werden nicht gezählt.",
    "%(who)s’s sickness was acknowledged.":
        "Die Krankmeldung von %(who)s wurde zur Kenntnis genommen.",
    "%(who)s’s sickness was recorded as not accepted, and they were told why. Those days no longer count as time worked.":
        "Die Krankmeldung von %(who)s wurde als nicht anerkannt erfasst, mit Begründung. Diese Tage zählen nicht mehr als Arbeitszeit.",
    "not yet seen": "noch nicht gesehen",

    "You are telling the app, not asking it. It counts from the moment you record it: the hours for those days are credited, it does not come out of your leave, and days you were not due to work are not counted. Your manager is shown it so they know, and confirms that they have seen it — that is a receipt, not a permission.":
        "Sie teilen es der App mit, Sie fragen nicht. Es zählt ab dem Moment der Erfassung: die Stunden dieser Tage werden gutgeschrieben, es geht nicht von Ihrem Urlaub ab, und Tage, an denen Sie nicht eingeteilt waren, werden nicht gezählt. Ihre Leitung sieht es und bestätigt, dass sie es zur Kenntnis genommen hat — das ist eine Empfangsbestätigung, keine Genehmigung.",

    # -- the year-end messages ---------------------------------------------
    "%(count)s people are carrying days into %(next_year)s.":
        "%(count)s Personen nehmen Resttage mit in das Jahr %(next_year)s.",
    "No reminder date was recorded, so the statutory days are treated as not expiring. Tell each person what they have left and that it will lapse, then record the date here.":
        "Es wurde kein Hinweisdatum erfasst, daher gelten die gesetzlichen Tage als nicht verfallend. Teilen Sie jeder Person mit, wie viele Tage offen sind und dass diese verfallen, und tragen Sie das Datum hier ein.",
    "Nobody has days left over from %(year)s.":
        "Aus %(year)s sind bei niemandem Tage offen geblieben.",
    "The deadline is %(date)s and it has not passed. Those days are still theirs to take.":
        "Die Frist ist der %(date)s und noch nicht abgelaufen. Diese Tage stehen weiterhin zu.",
    "%(count)s people lost carried-over days, and each row records what went and when.":
        "Bei %(count)s Personen sind übertragene Tage verfallen; jede Zeile hält fest, wie viele und wann.",
    "There was nothing left to lapse.": "Es war nichts mehr da, was verfallen konnte.",
    "The reminder date was recorded.": "Das Hinweisdatum wurde erfasst.",
    "No new date was given, so nothing was changed.":
        "Es wurde kein neues Datum angegeben, daher wurde nichts geändert.",
    "%(who)s’s deadline was moved, and the reason recorded.":
        "Die Frist von %(who)s wurde verschoben, mit Begründung.",

    # -- time zones --------------------------------------------------------
    "the same as the workplace": "wie der Betrieb",
    "time zone": "Zeitzone",
    "Only for somebody who works in a different one from the workplace.":
        "Nur für Personen, die in einer anderen Zeitzone als der Betrieb arbeiten.",
    "Leave empty unless they work in a different one from the workplace.":
        "Leer lassen, außer die Person arbeitet in einer anderen Zeitzone als der Betrieb.",
    "The clock the workplace keeps. It decides which date a start belongs to and how long a shift across the night the clocks change actually was.":
        "Die Uhr, nach der der Betrieb geht. Sie entscheidet, zu welchem Datum ein Arbeitsbeginn gehört und wie lang eine Schicht über die Nacht der Zeitumstellung tatsächlich war.",
    "The clock the workplace keeps. Somebody who works elsewhere can be given their own on their contract.":
        "Die Uhr, nach der der Betrieb geht. Wer anderswo arbeitet, kann im Vertrag eine eigene erhalten.",
    "Their own clock, not the workplace’s.": "Die eigene Uhr, nicht die des Betriebs.",

    # -- the contract as a history -----------------------------------------
    "in force from": "gültig ab",
    "The first date these hours apply. Everything before it keeps the previous ones.":
        "Das erste Datum, an dem diese Stunden gelten. Alles davor behält die bisherigen.",
    "why it changed": "Grund der Änderung",
    "Shown beside the change on their contract — “went to three days”, “parental leave”.":
        "Wird neben der Änderung im Vertrag angezeigt — „auf drei Tage reduziert“, „Elternzeit“.",
    "contract": "Vertrag",
    "contracts": "Verträge",
    "That is before %(name)s started on %(started)s. A contract cannot begin before the employment does.":
        "Das liegt vor dem Eintritt von %(name)s am %(started)s. Ein Vertrag kann nicht vor dem Arbeitsverhältnis beginnen.",
    "This contract has no working hours in it. Give at least one day some hours — a contract of nothing is not how somebody stops working here.":
        "Dieser Vertrag enthält keine Arbeitsstunden. Geben Sie mindestens einem Tag Stunden — ein Vertrag über nichts ist nicht der Weg, ein Arbeitsverhältnis zu beenden.",
    "%(name)s is on the new hours from %(date)s. %(days)s day(s) they had already confirmed fall inside that, so the hours those days are measured against have changed — the hours worked have not.":
        "%(name)s arbeitet ab dem %(date)s nach den neuen Stunden. %(days)s bereits bestätigte(r) Tag(e) fallen in diesen Zeitraum; die Sollstunden dieser Tage haben sich damit geändert — die geleisteten Stunden nicht.",
    "%(name)s is on the new hours from %(date)s. Everything before that keeps the old ones.":
        "%(name)s arbeitet ab dem %(date)s nach den neuen Stunden. Alles davor behält die alten.",
    "That is the only contract %(name)s has, not a change to one. Edit the hours instead — an employee with no contract has no working days at all.":
        "Das ist der einzige Vertrag von %(name)s, keine Änderung daran. Bearbeiten Sie stattdessen die Stunden — ohne Vertrag hat eine Person überhaupt keine Arbeitstage.",
    "The change from %(date)s was removed. The contract before it applies again.":
        "Die Änderung vom %(date)s wurde entfernt. Der vorherige Vertrag gilt wieder.",
    "Change the working hours": "Arbeitszeit ändern",
    "Change the hours": "Stunden ändern",
    "Change the hours from a date": "Stunden ab einem Datum ändern",
    "From when": "Ab wann",
    "The new working week": "Die neue Arbeitswoche",
    "Contracts so far": "Bisherige Verträge",
    "In force from": "Gültig ab",
    "Why": "Grund",
    "now": "aktuell",
    "Remove this change?": "Diese Änderung entfernen?",
    "The contract before it applies again from that date, and every figure derived from it moves back with it. Nothing that was worked is lost.":
        "Der vorherige Vertrag gilt ab diesem Datum wieder, und jede daraus abgeleitete Zahl geht mit zurück. Nichts von der geleisteten Arbeit geht verloren.",
    "Remove it": "Entfernen",
    "Leave in %(year)s": "Urlaub in %(year)s",
    "Everything before this date keeps the hours they are on now. Nothing already worked is rewritten — what moves is the contracted hours those days are measured against, and the leave the year is worth.":
        "Alles vor diesem Datum behält die derzeitigen Stunden. Nichts bereits Geleistetes wird umgeschrieben — es ändern sich die Sollstunden, an denen diese Tage gemessen werden, und der Urlaubsanspruch des Jahres.",
    "Their leave for %(year)s is worked out from every contract in force during it, each weighted by how much of the year it covered — so a change in April gives a quarter of the old entitlement and three quarters of the new one. Nothing is stored and recalculated; the balance is derived each time it is shown, so it cannot fall out of step.":
        "Der Urlaubsanspruch für %(year)s wird aus jedem in diesem Jahr gültigen Vertrag berechnet, jeweils gewichtet nach dem Anteil des Jahres — eine Änderung im April ergibt also ein Viertel des alten und drei Viertel des neuen Anspruchs. Es wird nichts gespeichert und nachgerechnet; der Saldo wird bei jeder Anzeige neu abgeleitet und kann daher nicht auseinanderlaufen.",
    "Dating this in the past is allowed — paperwork is slow, and an agreement made in April is often typed in June. You will be told how many already-confirmed days it reaches back over.":
        "Eine Rückdatierung ist zulässig — Papier ist langsam, und eine im April getroffene Vereinbarung wird oft erst im Juni erfasst. Sie erfahren, über wie viele bereits bestätigte Tage die Änderung zurückreicht.",
    "Editing the boxes above corrects the contract they started on. To put them on different hours from a date — everything before it staying as it is — use the change page.":
        "Die Felder oben zu bearbeiten korrigiert den Vertrag, mit dem die Person begonnen hat. Um sie ab einem Datum auf andere Stunden zu setzen — bei allem davor unverändert —, nutzen Sie die Änderungsseite.",
    "Their hours changed during this period, so the entitlement is worked out from each contract in turn, weighted by how much of the year it covered.":
        "Die Stunden haben sich in diesem Zeitraum geändert; der Anspruch wird daher aus jedem Vertrag einzeln berechnet, gewichtet nach dem Anteil des Jahres.",
    "This year is worth %(this_year)s days, worked out from every contract that was in force during it — so a change to your hours part-way through moves it, and so does joining or leaving part-way through.":
        "Dieses Jahr ist %(this_year)s Tage wert, berechnet aus jedem in diesem Jahr gültigen Vertrag — eine unterjährige Änderung Ihrer Stunden verschiebt den Wert also ebenso wie ein unterjähriger Ein- oder Austritt.",

    # -- the statutory split, in the settings ------------------------------
    "The statutory part cannot be more than the whole entitlement. Raise the full-time figure, or lower this one.":
        "Der gesetzliche Anteil kann nicht größer sein als der Gesamtanspruch. Erhöhen Sie den Vollzeitwert oder verringern Sie diesen.",
    "There is no such day in that month. It will be read as the last day of it.":
        "Diesen Tag gibt es in dem Monat nicht. Er wird als der letzte Tag des Monats gelesen.",
    "of which statutory, per year": "davon gesetzlich, pro Jahr",
    "The protected part, for somebody working a full week. 20 days on a five-day week is the statutory minimum. Anything above it is the employer’s own and may expire on the employer’s own terms.":
        "Der geschützte Anteil, bezogen auf eine volle Woche. 20 Tage bei einer Fünftagewoche sind das gesetzliche Minimum. Alles darüber gehört dem Arbeitgeber und kann nach dessen eigenen Regeln verfallen.",
    "statutory leave expires": "gesetzlicher Urlaub verfällt",
    "Switch off to carry it indefinitely, which is what an employer who does not send the reminder should assume.":
        "Ausschalten, um ihn unbefristet zu übertragen — wovon ein Arbeitgeber ausgehen sollte, der keinen Hinweis versendet.",
    "statutory carry-over deadline — month": "Frist für gesetzlichen Übertrag — Monat",
    "statutory carry-over deadline — day": "Frist für gesetzlichen Übertrag — Tag",
    "the employer’s extra expires": "der zusätzliche Urlaub verfällt",
    "the employer’s deadline — month": "Frist des Arbeitgebers — Monat",
    "the employer’s deadline — day": "Frist des Arbeitgebers — Tag",
    "Everybody’s leave is this many days scaled by how much of a full week they work — by days, never by hours, so somebody on three ten-hour days gets exactly as many days off as somebody on three six-hour days.":
        "Der Urlaub aller ergibt sich aus dieser Zahl, skaliert nach dem Anteil einer vollen Woche — nach Tagen, niemals nach Stunden. Wer an drei Zehnstundentagen arbeitet, hat also genau so viele freie Tage wie jemand mit drei Sechsstundentagen.",
    "The statutory part is protected: it carries over only until the deadline below, and under German case law it does not lapse at all unless the employee was told beforehand what was left. Whatever the employer grants on top follows the employer’s own deadline, which most contracts set at the end of the year it was earned in.":
        "Der gesetzliche Anteil ist geschützt: er wird nur bis zu der unten stehenden Frist übertragen, und nach der deutschen Rechtsprechung verfällt er überhaupt nicht, wenn die Person nicht vorher über den Reststand informiert wurde. Was der Arbeitgeber darüber hinaus gewährt, folgt dessen eigener Frist, die die meisten Verträge auf das Ende des Erwerbsjahres legen.",

    # -- Start and Stop ----------------------------------------------------
    "A shift is already running. Stop that one before starting another.":
        "Es läuft bereits eine Schicht. Beenden Sie diese, bevor Sie eine neue beginnen.",
    "There is no shift running, so there is nothing to stop.":
        "Es läuft keine Schicht, es gibt also nichts zu beenden.",
    "That would be a shift of no length. If you started it by mistake, remove the stretch on the day instead.":
        "Das wäre eine Schicht ohne Dauer. Wenn Sie versehentlich gestartet haben, entfernen Sie stattdessen den Abschnitt am Tag.",
    "You already have %(span)s recorded today, and now is inside it. Correct the day by hand instead.":
        "Für heute ist bereits %(span)s erfasst, und der jetzige Zeitpunkt liegt darin. Korrigieren Sie den Tag stattdessen von Hand.",
    "%(from)s – still running": "%(from)s – läuft noch",
    "Only one stretch can be left open at a time. Fill in the end of the earlier one — a day with two unfinished stretches cannot be added up.":
        "Es kann immer nur ein Abschnitt offen bleiben. Tragen Sie das Ende des früheren ein — ein Tag mit zwei unfertigen Abschnitten lässt sich nicht summieren.",
    "The clocks went forward on %(date)s, so %(time)s did not happen that night. Use the time you actually looked at.":
        "Am %(date)s wurde die Uhr vorgestellt; %(time)s hat es in dieser Nacht nicht gegeben. Verwenden Sie die Uhrzeit, die Sie tatsächlich abgelesen haben.",
    "That day is still running — stop the shift first, and then confirm it.":
        "Dieser Tag läuft noch — beenden Sie zuerst die Schicht und bestätigen Sie ihn dann.",
    "Leave empty while the shift is still running.":
        "Leer lassen, solange die Schicht noch läuft.",
    "Started at %(time)s.": "Um %(time)s begonnen.",
    "Stopped at %(time)s. %(hours)s recorded for %(date)s so far.":
        "Um %(time)s beendet. Für den %(date)s sind bisher %(hours)s erfasst.",

    "since %(time)s": "seit %(time)s",

    "Stop": "Beenden",
    "still running": "läuft noch",

    "Leave the end empty to record a start and stop later — the day then counts as still running and cannot be confirmed until it has an end. A stretch that ends at or before it starts runs past midnight, so 23:00 to 03:00 is four hours.":
        "Lassen Sie das Ende leer, um einen Beginn zu erfassen und später zu beenden — der Tag gilt dann als laufend und kann erst bestätigt werden, wenn er ein Ende hat. Ein Abschnitt, der zur Startzeit oder davor endet, läuft über Mitternacht: 23:00 bis 03:00 sind also vier Stunden.",

    # -- credited hours on the timesheet -----------------------------------

    "Credited, not worked — an absence the hours are paid for.":
        "Gutgeschrieben, nicht geleistet — eine Abwesenheit, für die die Stunden bezahlt werden.",

    # -- the year-end page -------------------------------------------------
    "Year end": "Jahresabschluss",
    "Days left over at the end of a year are carried into the next one. The statutory part lapses on %(statutory)s; anything the employer grants on top follows the employer’s own deadline. Neither happens by itself — closing the year writes down what is left, and the days only lapse when the deadline has actually passed.":
        "Am Jahresende offene Tage werden in das Folgejahr übertragen. Der gesetzliche Anteil verfällt am %(statutory)s; was der Arbeitgeber darüber hinaus gewährt, folgt dessen eigener Frist. Beides geschieht nicht von selbst — der Jahresabschluss hält fest, was offen ist, und die Tage verfallen erst, wenn die Frist tatsächlich abgelaufen ist.",
    "Statutory days only lapse if the employee was told.":
        "Gesetzliche Tage verfallen nur, wenn die Person informiert wurde.",
    "German case law requires the employer to tell each person, before the year ends, how many days are left and that they will lapse. Without a date recorded against a row, this app treats those days as not expiring — which is the safe answer, because the alternative is destroying an entitlement that still exists.":
        "Nach der deutschen Rechtsprechung muss der Arbeitgeber jeder Person vor Jahresende mitteilen, wie viele Tage offen sind und dass sie verfallen. Ohne ein in der Zeile erfasstes Datum behandelt diese App die Tage als nicht verfallend — das ist die sichere Antwort, denn die Alternative wäre, einen weiterhin bestehenden Anspruch zu vernichten.",
    "Carried into this year": "In dieses Jahr übertragen",
    "Lapsed": "Verfallen",
    "Who": "Person",
    "Carried in": "Übertrag",
    "Lapses": "Verfällt",
    "Lapsed and no longer available.": "Verfallen und nicht mehr verfügbar.",
    "lapsed %(date)s": "verfallen am %(date)s",
    "They were not told, so these days do not expire.":
        "Die Person wurde nicht informiert, daher verfallen diese Tage nicht.",
    "no reminder sent": "kein Hinweis versendet",
    "does not expire": "verfällt nicht",
    "extended": "verlängert",
    "Change": "Ändern",
    "Statutory days lapse on": "Gesetzliche Tage verfallen am",
    "The extra lapses on": "Die zusätzlichen Tage verfallen am",
    "They were told on": "Informiert am",
    "Without this the statutory days do not lapse at all.":
        "Ohne dieses Datum verfallen die gesetzlichen Tage überhaupt nicht.",
    "Why it was extended": "Grund der Verlängerung",
    "Closing the year": "Das Jahr abschließen",
    "Closing writes down what each person has left at the end of %(year)s and carries it into the next year. It can be run again after a late correction — it recomputes from the absences rather than adding to what is already there.":
        "Der Abschluss hält fest, was bei jeder Person am Ende von %(year)s offen ist, und überträgt es in das Folgejahr. Er kann nach einer späten Korrektur erneut ausgeführt werden — er rechnet aus den Abwesenheiten neu und addiert nicht auf das Bestehende.",
    "Close the year?": "Das Jahr abschließen?",
    "Each person’s remaining days are written down and carried into the next year, with the deadlines from the working time settings. Nothing lapses yet.":
        "Die Resttage jeder Person werden festgehalten und mit den Fristen aus den Arbeitszeiteinstellungen in das Folgejahr übertragen. Es verfällt noch nichts.",
    "Close it": "Abschließen",
    "Everybody was told on": "Alle informiert am",
    "The date the reminder went out to the whole team. Leave it empty if it has not, and the statutory days will be treated as not expiring until you record one.":
        "Das Datum, an dem der Hinweis an das gesamte Team ging. Leer lassen, wenn er noch nicht versendet wurde — die gesetzlichen Tage gelten dann als nicht verfallend, bis ein Datum erfasst ist.",
    "Close %(year)s": "%(year)s abschließen",
    "Letting the days lapse": "Die Tage verfallen lassen",
    "Once %(date)s has passed, whatever is left of the carried-over days can be written off. This is refused before the deadline — until then the days are still theirs to take, and there is no undo for removing them.":
        "Nach dem %(date)s kann abgeschrieben werden, was von den übertragenen Tagen übrig ist. Vor der Frist wird das abgelehnt — bis dahin stehen die Tage weiterhin zu, und ein Entfernen lässt sich nicht rückgängig machen.",
    "Let the carried days lapse?": "Die übertragenen Tage verfallen lassen?",
    "Every carried-over day past its deadline is written off, and each row records what went and on what date. Days belonging to somebody who was never sent the reminder are left alone.":
        "Jeder übertragene Tag jenseits seiner Frist wird abgeschrieben; jede Zeile hält fest, wie viele und zu welchem Datum. Tage von Personen, die nie einen Hinweis erhalten haben, bleiben unangetastet.",
    "Write them off": "Abschreiben",
    "Write off what has lapsed": "Verfallene Tage abschreiben",
    "%(days)s day(s) were carried over from %(year)s.":
        "%(days)s Tag(e) wurden aus %(year)s übertragen.",
    "They lapse on %(date)s.": "Sie verfallen am %(date)s.",
    "They do not expire.": "Sie verfallen nicht.",
    "%(lost)s day(s) lapsed on %(date)s and are no longer available.":
        "%(lost)s Tag(e) sind am %(date)s verfallen und stehen nicht mehr zur Verfügung.",
    "The deadline was extended: %(reason)s":
        "Die Frist wurde verlängert: %(reason)s",
    "No reminder was recorded.": "Es wurde kein Hinweis erfasst.",

    # -- what somebody arrives with ----------------------------------------
    #
    # "Saldo" is what a German payslip and a works agreement call a running
    # balance of hours, and it is what the staff will say out loud — so the
    # column is "Saldo" and not a literal rendering of "balance".
    "hours brought with them": "mitgebrachte Stunden",
    "Hours already owed to them, or by them, on the date below. Write a minus in front if they start in debit — “-14” or “-14:00”.":
        "Stunden, die ihnen zum unten stehenden Datum bereits zustehen oder die sie schulden. Bei einem Minussaldo ein Minus voranstellen — „-14“ oder „-14:00“.",
    "Hours already owed to them, or by them, when they started here. Leave at nought unless something was agreed.":
        "Stunden, die ihnen beim Eintritt bereits zustanden oder die sie schuldeten. Auf null lassen, sofern nichts vereinbart wurde.",
    "leave days brought with them": "mitgebrachte Urlaubstage",
    "Days of leave carried in from wherever they were before.":
        "Urlaubstage, die aus dem vorherigen Arbeitsverhältnis mitgebracht werden.",
    "as at": "Stand",
    "The date those figures were true. Usually the day they started.":
        "Das Datum, zu dem diese Werte galten. Üblicherweise der Eintrittstag.",
    "Say when those figures were true. Without a date the leave days cannot be counted into a year, and they would be lost.":
        "Geben Sie an, zu welchem Datum diese Werte galten. Ohne Datum lassen sich die Urlaubstage keinem Jahr zuordnen und gingen verloren.",
    "That is before they started here. The figures they arrived with are true on their first day, not before it.":
        "Das liegt vor dem Eintritt. Die mitgebrachten Werte gelten am ersten Arbeitstag, nicht davor.",
    "What they arrived with": "Was mitgebracht wurde",
    "Nobody starts at nought. Somebody moving from another contract arrives with a figure already agreed — hours in hand, days of leave not yet taken — and this is where it goes. Leave it empty for anybody starting fresh.":
        "Niemand fängt bei null an. Wer aus einem anderen Vertrag wechselt, bringt einen bereits vereinbarten Stand mit — Stunden im Guthaben, noch nicht genommene Urlaubstage — und hier gehört er hin. Bei einem Neuanfang leer lassen.",
    "The hours are added to their running balance from that date onwards. The leave days are added to that one year’s entitlement — whatever is left of them afterwards carries forward like anybody else’s.":
        "Die Stunden fließen ab diesem Datum in den laufenden Saldo ein. Die Urlaubstage werden dem Anspruch dieses einen Jahres hinzugerechnet — was davon offen bleibt, wird anschließend übertragen wie bei allen anderen auch.",
    "Balance now": "Saldo aktuell",
    "Of which brought with them": "davon mitgebracht",
    "Balance": "Saldo",

    "Includes %(opening)s brought from a previous contract.":
        "Enthält %(opening)s aus einem früheren Vertrag.",

    "German case law says statutory leave only lapses if the employee was told, before the year ended, how many days were left and that they would expire. Until a date is recorded on the Year end page, these days go on being owed.":
        "Nach der deutschen Rechtsprechung verfällt gesetzlicher Urlaub nur, wenn die Person vor Jahresende erfahren hat, wie viele Tage offen sind und dass sie verfallen. Solange auf der Seite „Jahresabschluss“ kein Datum erfasst ist, bleiben diese Tage geschuldet.",
}

# The djangojs half. One string, and it is the label on a stretch that has been
# started and not yet stopped — which is the one the browser writes for itself
# while somebody is typing.
JAVASCRIPT_YEAR = {
    # What the day form writes beside a stretch that has been started and not
    # stopped. A duration, not a time, and deliberately not a number.
    "running": "läuft",

}
