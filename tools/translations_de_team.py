"""The German for the manager's pages: coverage, requests, people, presets.

A fourth table beside ``translations_de``, ``translations_de_pages`` and
``translations_de_year``, split for the reason those are: one file of two
thousand lines is one nobody scrolls through, and these belong together because
they are the strings on the pages a *manager* opens rather than the ones an
employee sees.

The terms are the ones the other three fix, and two more that matter here:

    Anmeldename     the directory name a contract is matched on
    Abwesenheit     an absence of any kind, on the coverage grid
    Regenerationstage   left in German — it is the word in the agreement, and
                        translating it would make it unsearchable

``tools/apply_translations.py`` merges the four and refuses a msgid that
appears in more than one, so anything here is guaranteed not to be shadowing
an entry elsewhere.
"""

TEAM = {
    # -- the coverage grid -------------------------------------------------
    "Absence calendar": "Abwesenheitskalender",
    "Who is off": "Wer ist abwesend",
    "Time off in %(month)s, one row per person":
        "Abwesenheiten im %(month)s, eine Zeile pro Person",
    "Away that day": "An dem Tag abwesend",
    "Off": "Abw.",
    "of which are still waiting for a decision":
        "davon warten noch auf eine Entscheidung",
    "Not a working day for this person.":
        "An diesem Tag ist die Person nicht eingeteilt.",
    # The key under the grid. Lower case because each sits beside a swatch in a
    # running line rather than standing as a label of its own.
    "off": "Urlaub",
    "sick": "krank",
    "hours taken back": "Überstundenabbau",
    "the workplace is shut": "Betriebsferien",
    "waiting for a decision": "wartet auf Entscheidung",

    # -- requests, as a tile a person -------------------------------------
    "Everybody waiting": "Alle Wartenden",
    "What is waiting": "Was auf eine Entscheidung wartet",
    "Waiting for a decision": "Wartet auf Entscheidung",
    "Already approved": "Bereits genehmigt",
    "Days asked for": "Beantragte Tage",
    "Left after": "Danach übrig",
    "Earliest day asked for: %(date)s": "Frühester beantragter Tag: %(date)s",
    "%(days)s more asked for and not yet decided":
        "%(days)s weitere beantragt und noch nicht entschieden",

    # -- the person picker on the timesheet -------------------------------
    "Choose somebody": "Person auswählen",
    "%(name)s’s timesheet": "Stundenzettel von %(name)s",

    # -- the team overview -------------------------------------------------
    "Where everybody stands: the days off they still have this year, and the hours they are up or down overall. Open a name for the month behind the figure.":
        "Wie alle stehen: die Urlaubstage, die ihnen dieses Jahr noch bleiben, und ihr Stundensaldo insgesamt. Ein Klick auf den Namen öffnet den Monat hinter der Zahl.",
    "Days off still to be taken": "Noch zu nehmende Urlaubstage",
    "Hours, everybody together": "Stunden, alle zusammen",
    "Hours balance": "Stundensaldo",

    # -- the people list, and what each of its columns means ---------------
    #
    # The two username columns are the whole reason several of these exist: the
    # page printed one string twice and said nothing about which was which.
    "Sign-in name": "Anmeldename",
    "The name the directory knows them by. The first token that arrives with this name is matched to this contract.":
        "Der Name, unter dem das Verzeichnis die Person führt. Die erste Anmeldung mit diesem Namen wird diesem Vertrag zugeordnet.",
    "Working week": "Arbeitswoche",
    "Which days of the week the contract gives hours to.":
        "An welchen Wochentagen der Vertrag Stunden vorsieht.",
    "Contracted hours per week, added up across the seven days.":
        "Vertragliche Wochenstunden, über die sieben Tage summiert.",
    "Days a week": "Tage pro Woche",
    "How many days a week the contract gives hours to. The leave entitlement is worked out from this.":
        "An wie vielen Tagen pro Woche der Vertrag Stunden vorsieht. Daraus ergibt sich der Urlaubsanspruch.",
    "Days off a year": "Urlaubstage pro Jahr",
    "Days off a full year of this contract is worth. Any extra leave they have been granted is the pill beside it.":
        "Urlaubstage, die ein volles Jahr dieses Vertrags bringt. Zusätzlich gewährter Sonderurlaub steht als Marke daneben.",
    "Hours worked, less hours contracted, since they started. Positive means they are owed time.":
        "Geleistete minus vertragliche Stunden seit Eintritt. Ein Plus bedeutet, dass der Person Zeit zusteht.",
    "Whether a sign-in has been matched to this contract yet.":
        "Ob diesem Vertrag bereits eine Anmeldung zugeordnet ist.",
    "linked": "verknüpft",
    "They have signed in, and the account matches the sign-in name on the contract.":
        "Die Person hat sich angemeldet, und das Konto entspricht dem Anmeldenamen im Vertrag.",
    "Signed in as %(account)s — not the %(contract)s this contract is matched on.":
        "Angemeldet als %(account)s — nicht der Anmeldename %(contract)s, auf den dieser Vertrag zugeordnet wird.",
    "Nobody has signed in with this name yet. That is ordinary — the link is made by itself at the first sign-in.":
        "Mit diesem Namen hat sich noch niemand angemeldet. Das ist normal — die Verknüpfung entsteht bei der ersten Anmeldung von selbst.",

    # -- the contract change, said on the timesheet ------------------------
    "The contract changed on %(date)s.": "Am %(date)s hat sich der Vertrag geändert.",
    "From here on the week is %(after)s hours over %(after_days)s days, where it was %(before)s hours over %(before_days)s days.":
        "Ab hier umfasst die Woche %(after)s Stunden an %(after_days)s Tagen; vorher waren es %(before)s Stunden an %(before_days)s Tagen.",
    "From here on the week is %(after)s hours over %(after_days)s days.":
        "Ab hier umfasst die Woche %(after)s Stunden an %(after_days)s Tagen.",
    "The leave entitlement is worked out from the working days, so it moves with this.":
        "Der Urlaubsanspruch richtet sich nach den Arbeitstagen und ändert sich damit mit.",

    # -- Regenerationstage --------------------------------------------------
    #
    # The name itself is not translated: it is the word the collective agreement
    # uses, it is what somebody will search the app for, and an "Erholungstage"
    # here would make the entitlement unfindable in a payroll conversation.
    "Add %(name)s": "%(name)s hinzufügen",
    "Two days a calendar year on a five-day week, fewer on fewer days — the table the TVöD gives for the Sozial- und Erziehungsdienst.":
        "Zwei Tage pro Kalenderjahr bei einer Fünf-Tage-Woche, bei weniger Tagen entsprechend weniger — die Staffel, die der TVöD für den Sozial- und Erziehungsdienst vorsieht.",
    "Two days a calendar year on a five-day week (TVöD SuE, Anlage D.12 Nr. 1a); fewer days a week gives fewer, rounded up from half a day. Set the days by hand for anybody who has already taken some of them elsewhere this year, who had less than four months of pay entitlement in it, or whose days were carried past 31 December — the app does not work those three out.":
        "Zwei Tage pro Kalenderjahr bei einer Fünf-Tage-Woche (TVöD SuE, Anlage D.12 Nr. 1a); weniger Wochenarbeitstage ergeben weniger, ab einem halben Tag aufgerundet. Tragen Sie die Tage von Hand ein für alle, die in diesem Jahr bereits welche anderswo genommen haben, die weniger als vier Monate Entgeltanspruch im Jahr hatten oder deren Tage über den 31. Dezember hinaus übertragen wurden — diese drei Fälle rechnet die App nicht aus.",
    "“%(name)s” already exists, so nothing was changed. Edit it if the days are not what your agreement says.":
        "„%(name)s“ gibt es bereits, es wurde nichts geändert. Bearbeiten Sie den Eintrag, wenn die Tage nicht dem entsprechen, was Ihr Tarifvertrag vorsieht.",
    "“%(name)s” was added with the table the agreement gives for a five-day week. A full week here is %(days)s days, so check the steps against what your own agreement says before granting it.":
        "„%(name)s“ wurde mit der Staffel angelegt, die der Tarifvertrag für eine Fünf-Tage-Woche vorsieht. Eine volle Woche sind hier %(days)s Tage — prüfen Sie die Stufen daher an Ihrem eigenen Tarifvertrag, bevor Sie den Anspruch gewähren.",
    "“%(name)s” was added: two days for a four- or five-day week, one for two or three days, none for one. Grant it to the people it applies to on their contract.":
        "„%(name)s“ wurde angelegt: zwei Tage bei einer Vier- oder Fünf-Tage-Woche, ein Tag bei zwei oder drei Tagen, keiner bei einem Tag. Gewähren Sie den Anspruch den betreffenden Personen in deren Vertrag.",

    # -- a granted type, and the figure typed over its rule ----------------
    "what this is": "worum es sich handelt",
    "Where the entitlement comes from, and anything about it the app does not work out for itself. Shown to a manager beside the grant on somebody’s contract — which is the moment they need to know it.":
        "Woher der Anspruch stammt und alles daran, was die App nicht selbst ausrechnet. Wird der Leitung im Vertrag der Person neben der Gewährung angezeigt — genau dann, wenn sie es wissen muss.",
    "Only needed when the days above are set by hand.":
        "Nur nötig, wenn die Tage oben von Hand gesetzt sind.",
    "e.g. one day already taken at a previous employer":
        "z. B. ein Tag bereits beim vorherigen Arbeitgeber genommen",
    "Say why this is set by hand — “two days already taken at a previous employer”, for instance. A figure typed over the rule with no reason beside it is one nobody can account for later.":
        "Geben Sie an, warum hier von Hand eingetragen wird — etwa „zwei Tage bereits beim vorherigen Arbeitgeber genommen“. Eine Zahl, die ohne Begründung über die Regel gesetzt wird, kann später niemand mehr erklären.",
}

TEAM_PLURALS = {
    "%(counter)s request": ("%(counter)s Antrag", "%(counter)s Anträge"),
    "%(counter)s cancellation": ("%(counter)s Stornierung", "%(counter)s Stornierungen"),
    "%(counter)s request is waiting. Open somebody to see their calendar and answer it.": (
        "%(counter)s Antrag wartet. Öffnen Sie eine Person, um deren Kalender zu sehen und zu entscheiden.",
        "%(counter)s Anträge warten. Öffnen Sie eine Person, um deren Kalender zu sehen und zu entscheiden.",
    ),
    "%(counter)s day on this page is still waiting for a decision — it is drawn with a dotted edge, and until somebody answers it is neither cover you have nor cover you have lost.": (
        "%(counter)s Tag auf dieser Seite wartet noch auf eine Entscheidung — er ist gepunktet umrandet, und bis jemand entscheidet, ist er weder gesicherte Besetzung noch verlorene.",
        "%(counter)s Tage auf dieser Seite warten noch auf eine Entscheidung — sie sind gepunktet umrandet, und bis jemand entscheidet, sind sie weder gesicherte Besetzung noch verlorene.",
    ),
}
