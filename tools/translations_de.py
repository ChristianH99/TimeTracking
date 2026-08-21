"""The German catalogue, as a table.

German is this app's default language and the only one its users are expected
to read, so an untranslated string is not a cosmetic gap — it is an English
sentence on the page everybody actually uses. ``config/tests.py`` fails on one,
which is what keeps this file honest.

**Why a Python table and not a hand-edited `.po`.** Two reasons, and both are
failures this pipeline has actually had. gettext on Windows reliably emits a
malformed wrapped ``#:`` reference line that makes ``msgfmt`` refuse the whole
file and write no ``.mo`` at all — so the app carries on serving the *previous*
catalogue and a session's translations look compiled and simply are not there.
And a long ``msgstr`` broken across continuation lines is valid `.po` that the
completeness check reads as *empty*. Generating from here means the `.po` is
written once, in one shape, by ``tools/apply_translations.py``, and neither
trap has anywhere to occur.

Terms are fixed rather than varied for readability, because they are what
people will search the app for and argue about with payroll:

    Urlaub          annual leave (never "Ferien")
    Sonderurlaub    special leave
    Pause           break
    Dienstplan      roster
    Schicht         shift
    Stundenzettel   timesheet
    Arbeitszeit     working time
    Feiertag        public holiday
    Betriebsferien  a closure that costs leave
    Krankheit       sickness
"""

# msgid -> msgstr. Placeholders must survive exactly: a translation that drops
# or renames a %(name)s raises at render time, on the page it is on, in
# production only. config/tests.py::test_the_placeholders_survive_translation
# is what catches that.
SINGULAR = {
    # -- absences: forms and models ------------------------------------
    "—": "—",
    "The end is before the start.": "Das Ende liegt vor dem Anfang.",
    "Say which special leave this is.": "Bitte angeben, um welchen Sonderurlaub es sich handelt.",
    "You already have time off recorded that overlaps these dates.":
        "Für diesen Zeitraum ist bei Ihnen bereits eine Abwesenheit eingetragen.",
    "Leave empty if you do not know yet — you can say when it ended later.":
        "Leer lassen, wenn es noch nicht absehbar ist — das Ende können Sie später nachtragen.",
    "reply": "Antwort",
    "Say why. Somebody whose time off is declined without a reason has to come and ask for one.":
        "Bitte begründen. Wer eine Absage ohne Grund bekommt, muss nachfragen kommen.",
    "Holiday": "Urlaub",
    "Special leave": "Sonderurlaub",
    "Sick": "Krank",
    "Workplace closed": "Betrieb geschlossen",
    "Waiting for approval": "Wartet auf Genehmigung",
    "Approved": "Genehmigt",
    "Declined": "Abgelehnt",
    "Withdrawn": "Zurückgezogen",
    "date": "Datum",
    "name": "Name",
    "Generated rows are replaced when the year is generated again; added ones are not.":
        "Berechnete Einträge werden beim erneuten Erzeugen des Jahres ersetzt, von Hand hinzugefügte nicht.",
    "public holiday": "Feiertag",
    "public holidays": "Feiertage",
    "from": "von",
    "to": "bis",
    "comes out of their leave": "geht vom Urlaub ab",
    "Off for a day the employer closes and pays for.":
        "Aus, wenn der Betrieb schließt und den Tag bezahlt.",
    "closure": "Schließzeit",
    "closures": "Schließzeiten",
    "employee": "Mitarbeiter/in",
    "reason": "Anmerkung",
    "which": "welcher",
    "status": "Status",
    "note": "Anmerkung",
    "absence": "Abwesenheit",
    "absences": "Abwesenheiten",
    "Say which special leave this is, or it cannot be counted.":
        "Bitte angeben, um welchen Sonderurlaub es sich handelt — sonst kann er nicht angerechnet werden.",
    "Only special leave names a leave type.": "Nur Sonderurlaub nennt eine Urlaubsart.",
    "Your request was sent for approval. It shows as waiting until your manager decides, and the days are not taken off your balance before then.":
        "Ihr Antrag wurde zur Genehmigung weitergeleitet. Er steht auf „wartet“, bis Ihre Leitung entscheidet; bis dahin werden die Tage nicht von Ihrem Guthaben abgezogen.",
    "That is not something you can withdraw.": "Das können Sie nicht zurückziehen.",
    "That time off has already started. Ask your manager to change it.":
        "Diese Abwesenheit hat bereits begonnen. Bitte wenden Sie sich an Ihre Leitung.",
    "The request was withdrawn.": "Der Antrag wurde zurückgezogen.",
    "Those dates could not be read.": "Diese Daten konnten nicht gelesen werden.",
    "That date could not be read.": "Dieses Datum konnte nicht gelesen werden.",
    "That is before the illness started.": "Das liegt vor dem Beginn der Krankheit.",
    "Thank you — the sickness is recorded as ended.": "Danke — die Krankheit ist als beendet eingetragen.",
    "That request has already been decided.": "Über diesen Antrag wurde bereits entschieden.",
    "That could not be saved.": "Das konnte nicht gespeichert werden.",
    "%(who)s’s time off was approved.": "Die Abwesenheit von %(who)s wurde genehmigt.",
    "%(who)s’s request was declined and they were told why.":
        "Der Antrag von %(who)s wurde abgelehnt, mit Begründung.",

    # -- accounts: forms -----------------------------------------------
    "Password": "Passwort",
    "Repeat password": "Passwort wiederholen",
    "The two passwords do not match.": "Die beiden Passwörter stimmen nicht überein.",
    "What they type to sign in. Letters, digits and . @ + - _":
        "Was zum Anmelden eingegeben wird. Buchstaben, Ziffern und . @ + - _",
    "Managed by the identity provider.": "Wird vom Identitätsanbieter verwaltet.",
    "You cannot switch off your own account.": "Sie können Ihr eigenes Konto nicht abschalten.",
    "You cannot take the administrator right off your own account.":
        "Sie können sich das Administratorrecht nicht selbst entziehen.",
    "This is the last active administrator. Give somebody else the right first.":
        "Das ist der letzte aktive Administrator. Geben Sie das Recht zuerst jemand anderem.",
    "Client secret": "Client-Secret",
    "Leave empty to keep the one already stored.": "Leer lassen, um das gespeicherte zu behalten.",
    "Remove the stored secret": "Gespeichertes Secret entfernen",
    "A client secret is needed before Synology sign-in can be switched on.":
        "Ohne Client-Secret lässt sich die Synology-Anmeldung nicht einschalten.",
    "A client ID is needed before Synology sign-in can be switched on.":
        "Ohne Client-ID lässt sich die Synology-Anmeldung nicht einschalten.",
    "Give the SSO server’s address, or fill the authorisation and token endpoints in by hand.":
        "Geben Sie die Adresse des SSO-Servers an, oder tragen Sie Autorisierungs- und Token-Endpunkt von Hand ein.",
    "RS256 verifies the token against the provider’s key, so the JWKS address is needed and could not be read from this server. Check the address, fill the endpoints in by hand below, or choose HS256, which signs with the client secret instead.":
        "RS256 prüft das Token gegen den Schlüssel des Anbieters, dafür wird die JWKS-Adresse gebraucht — sie konnte von diesem Server nicht gelesen werden. Prüfen Sie die Adresse, tragen Sie die Endpunkte unten von Hand ein, oder wählen Sie HS256, das stattdessen mit dem Client-Secret signiert.",
    "RS256 — signed with the provider’s key (needs the JWKS endpoint)":
        "RS256 — signiert mit dem Schlüssel des Anbieters (braucht den JWKS-Endpunkt)",
    "HS256 — signed with the client secret (no key fetch)":
        "HS256 — signiert mit dem Client-Secret (kein Schlüsselabruf)",
    "offer single sign-on": "Single Sign-on anbieten",
    "With this off, the local password form is the only way in.":
        "Ist das aus, ist das lokale Passwortformular der einzige Weg hinein.",
    "SSO server": "SSO-Server",
    "The issuer, e.g. https://sso.example.org — or paste the full …/.well-known/openid-configuration address if that is what your provider gives you.":
        "Der Issuer, z. B. https://sso.example.org — oder fügen Sie die vollständige Adresse …/.well-known/openid-configuration ein, wenn Ihr Anbieter Ihnen diese nennt.",
    "authorisation endpoint": "Autorisierungs-Endpunkt",
    "token endpoint": "Token-Endpunkt",
    "user info endpoint": "Benutzerinfo-Endpunkt",
    "JWKS endpoint": "JWKS-Endpunkt",
    "client ID": "Client-ID",
    "signature algorithm": "Signaturalgorithmus",
    "scopes": "Scopes",
    "Separated by spaces.": "Durch Leerzeichen getrennt.",
    "allowed groups": "Erlaubte Gruppen",
    "Separated by commas. Empty means anybody the SSO server authenticates.":
        "Durch Kommas getrennt. Leer heißt: alle, die der SSO-Server authentifiziert.",
    "group claim": "Gruppen-Claim",
    "The claim the group names arrive in. Some providers send none at all.":
        "Der Claim, in dem die Gruppennamen ankommen. Manche Anbieter senden gar keinen.",
    "administrator group": "Administratorgruppe",
    "Members of this group may manage people. Re-applied at every sign-in.":
        "Mitglieder dieser Gruppe dürfen Konten verwalten. Wird bei jeder Anmeldung neu gesetzt.",
    "verify the certificate": "Zertifikat prüfen",
    "Leave on. Verification is the whole point of putting the SSO server behind a real certificate.":
        "An lassen. Die Prüfung ist der ganze Sinn eines echten Zertifikats vor dem SSO-Server.",
    "request timeout": "Zeitlimit",
    "Seconds to wait for the provider before giving up.":
        "Sekunden, die auf den Anbieter gewartet wird.",
    "SSO configuration": "SSO-Konfiguration",
    "account": "Konto",
    "subject": "Subject",
    "matched by e-mail address": "über die E-Mail-Adresse zugeordnet",
    "Attached to an account that already existed, rather than creating one.":
        "An ein bereits vorhandenes Konto angehängt, statt ein neues anzulegen.",
    "provider identity": "Anbieter-Identität",
    "provider identities": "Anbieter-Identitäten",
    "decimal — 7,5 h": "dezimal — 7,5 h",
    "clock — 7:30 h": "Uhrzeit — 7:30 h",
    "hours": "Stunden",
    "How durations are written on every page that shows one.":
        "Wie Zeitdauern auf jeder Seite geschrieben werden, die eine anzeigt.",
    "preferences": "Einstellungen",

    # -- accounts: sso views -------------------------------------------
    "Saved, but the endpoints could not be read from %(url)s: %(error)s. Fill them in by hand under “Enter the endpoints by hand”.":
        "Gespeichert, aber die Endpunkte konnten von %(url)s nicht gelesen werden: %(error)s. Tragen Sie sie unter „Endpunkte von Hand eintragen“ ein.",
    "Saved, and the endpoints were read from %(url)s.":
        "Gespeichert, und die Endpunkte wurden von %(url)s gelesen.",
    "The SSO settings were saved.": "Die SSO-Einstellungen wurden gespeichert.",
    "The endpoints could not be read from %(url)s: %(error)s":
        "Die Endpunkte konnten von %(url)s nicht gelesen werden: %(error)s",
    "Authorisation": "Autorisierung",
    "Token": "Token",
    "User info": "Benutzerinfo",
    "JWKS": "JWKS",
    "there is no SSO server address to look at": "es ist keine SSO-Server-Adresse hinterlegt",
    "it answered, but with nothing that looks like a discovery document":
        "es kam eine Antwort, aber nichts, was wie ein Discovery-Dokument aussieht",
    "Could not read the discovery document from %(url)s: %(error)s":
        "Das Discovery-Dokument konnte von %(url)s nicht gelesen werden: %(error)s",
    "(nowhere — no address is set)": "(nirgends — es ist keine Adresse gesetzt)",
    "Read from %(url)s. Check the addresses below, then save.":
        "Von %(url)s gelesen. Prüfen Sie die Adressen unten und speichern Sie dann.",
    "There is nothing configured to check yet.": "Es ist noch nichts konfiguriert, das geprüft werden könnte.",
    "the certificate was refused — wrong hostname, or an internal CA":
        "das Zertifikat wurde abgelehnt — falscher Hostname oder eine interne CA",
    "the response was not JSON": "die Antwort war kein JSON",
    "timed out": "Zeitüberschreitung",
    "the name could not be resolved from inside the container":
        "der Name konnte aus dem Container heraus nicht aufgelöst werden",
    "the connection was refused — nothing is listening on that port":
        "die Verbindung wurde abgelehnt — auf diesem Port lauscht nichts",
    "no connection could be made": "es kam keine Verbindung zustande",
    "answered, HTTP %(code)s": "geantwortet, HTTP %(code)s",
    "the request failed": "die Anfrage schlug fehl",

    # -- accounts: user management -------------------------------------
    "The account “%(name)s” was created.": "Das Konto „%(name)s“ wurde angelegt.",
    "“%(name)s” was saved.": "„%(name)s“ wurde gespeichert.",
    "The password for “%(name)s” was changed.": "Das Passwort für „%(name)s“ wurde geändert.",
    "“%(name)s” has no password of their own, so single sign-on is the only way in. Delete the account instead.":
        "„%(name)s“ hat kein eigenes Passwort, Single Sign-on ist also der einzige Weg hinein. Löschen Sie das Konto stattdessen.",
    "“%(name)s” is not linked to the identity provider.":
        "„%(name)s“ ist nicht mit dem Identitätsanbieter verknüpft.",
    "“%(name)s” is no longer linked to the identity provider and signs in with their password.":
        "„%(name)s“ ist nicht mehr mit dem Identitätsanbieter verknüpft und meldet sich mit Passwort an.",
    "You cannot delete your own account.": "Sie können Ihr eigenes Konto nicht löschen.",
    "“%(name)s” was deleted.": "„%(name)s“ wurde gelöscht.",
    "“%(name)s” can sign in again.": "„%(name)s“ kann sich wieder anmelden.",
    "“%(name)s” can no longer sign in.": "„%(name)s“ kann sich nicht mehr anmelden.",
    "Your settings were saved.": "Ihre Einstellungen wurden gespeichert.",

    # -- employees ------------------------------------------------------
    "They cannot leave before they started.": "Das Austrittsdatum liegt vor dem Eintritt.",
    "This contract has no working hours in it. Give at least one day some hours, or switch the employee off if they have left.":
        "In diesem Vertrag stehen keine Arbeitsstunden. Tragen Sie mindestens an einem Tag Stunden ein, oder schalten Sie die Person ab, wenn sie ausgeschieden ist.",
    "Monday": "Montag",
    "Tuesday": "Dienstag",
    "Wednesday": "Mittwoch",
    "Thursday": "Donnerstag",
    "Friday": "Freitag",
    "Saturday": "Samstag",
    "Sunday": "Sonntag",
    "Filled in by itself when they first sign in, if the e-mail addresses match.":
        "Wird bei der ersten Anmeldung von selbst gesetzt, wenn die E-Mail-Adressen übereinstimmen.",
    "first name": "Vorname",
    "surname": "Nachname",
    "manages the team": "leitet das Team",
    "May plan the roster, see everybody’s timesheets and decide requests.":
        "Darf den Dienstplan erstellen, alle Stundenzettel sehen und Anträge entscheiden.",
    "employed": "beschäftigt",
    "Switching this off keeps every hour they have worked and takes them off the roster.":
        "Abschalten behält jede geleistete Stunde und nimmt die Person aus dem Dienstplan.",
    "started on": "Eintritt am",
    "left on": "Austritt am",
    "After this date they are not rostered and their leave stops accruing.":
        "Nach diesem Datum wird die Person nicht mehr eingeteilt und erwirbt keinen Urlaub mehr.",
    "leave days": "Urlaubstage",
    "Leave empty to work it out from the working days. Fill it in only for a contract that says something else.":
        "Leer lassen, um sie aus den Arbeitstagen zu berechnen. Nur ausfüllen, wenn der Vertrag etwas anderes sagt.",
    "employees": "Mitarbeitende",
    "leave type": "Urlaubsart",
    "days": "Tage",
    "Leave empty to use the type’s own rule.": "Leer lassen, um die Regel der Urlaubsart zu verwenden.",
    "special leave": "Sonderurlaub",
    "%(name)s was saved.": "%(name)s wurde gespeichert.",
    "That account is already attached to somebody else, so it was not linked.":
        "Dieses Konto ist bereits jemand anderem zugeordnet und wurde deshalb nicht verknüpft.",
    "%(name)s has hours, shifts or absences recorded and cannot be deleted — those are the record of work that was actually done. Switch them off instead: that takes them off the roster and keeps everything.":
        "Für %(name)s sind Stunden, Schichten oder Abwesenheiten erfasst; ein Löschen ist nicht möglich — das ist der Nachweis tatsächlich geleisteter Arbeit. Schalten Sie die Person stattdessen ab: das nimmt sie aus dem Dienstplan und behält alles.",
    "%(name)s was deleted.": "%(name)s wurde gelöscht.",

    # -- organisation ---------------------------------------------------
    "working time over": "Arbeitszeit über",
    "In hours. 6 means “more than six hours of work”.":
        "In Stunden. 6 bedeutet „mehr als sechs Stunden Arbeit“.",
    "There is already a rule at this length.": "Für diese Länge gibt es bereits eine Regel.",
    "A leave type worked out from a table needs at least one row in it, or nobody gets any of it.":
        "Eine aus einer Tabelle berechnete Urlaubsart braucht mindestens eine Zeile, sonst bekommt niemand etwas davon.",
    "There is already a row for this many days.": "Für diese Anzahl Tage gibt es bereits eine Zeile.",
    "Baden-Württemberg": "Baden-Württemberg",
    "Bavaria": "Bayern",
    "Berlin": "Berlin",
    "Brandenburg": "Brandenburg",
    "Bremen": "Bremen",
    "Hamburg": "Hamburg",
    "Hesse": "Hessen",
    "Mecklenburg-Vorpommern": "Mecklenburg-Vorpommern",
    "Lower Saxony": "Niedersachsen",
    "North Rhine-Westphalia": "Nordrhein-Westfalen",
    "Rhineland-Palatinate": "Rheinland-Pfalz",
    "Saarland": "Saarland",
    "Saxony": "Sachsen",
    "Saxony-Anhalt": "Sachsen-Anhalt",
    "Schleswig-Holstein": "Schleswig-Holstein",
    "Thuringia": "Thüringen",
    "always up — 16.8 days becomes 17": "immer auf — aus 16,8 Tagen werden 17",
    "to the nearest half day — 16.8 becomes 17, 16.6 becomes 16.5":
        "auf den halben Tag — aus 16,8 werden 17, aus 16,6 werden 16,5",
    "leave the fraction — 16.8 stays 16.8": "Bruchteil behalten — 16,8 bleibt 16,8",
    "full-time working days per week": "Arbeitstage pro Woche bei Vollzeit",
    "The divisor for everybody’s leave. Five for a Monday-to-Friday business.":
        "Der Teiler für den Urlaub aller. Fünf für einen Betrieb von Montag bis Freitag.",
    "full-time leave days per year": "Urlaubstage pro Jahr bei Vollzeit",
    "What somebody working a full week is entitled to. The statutory minimum is 20 on a five-day week.":
        "Was jemandem bei voller Woche zusteht. Der gesetzliche Mindesturlaub sind 20 Tage bei einer Fünftagewoche.",
    "rounding": "Rundung",
    "What happens to the fraction when the entitlement does not come out whole.":
        "Was mit dem Bruchteil geschieht, wenn der Anspruch nicht ganzzahlig aufgeht.",
    "federal state": "Bundesland",
    "Which public holidays apply. Nine of the thirteen differ by Land.":
        "Welche Feiertage gelten. Neun der dreizehn hängen vom Bundesland ab.",
    "the day usually starts at": "Der Tag beginnt üblicherweise um",
    "Used only when filling a week from the contracts, as the first draft.":
        "Wird nur beim Erzeugen einer Woche aus den Verträgen als erster Entwurf verwendet.",
    "working time settings": "Arbeitszeit-Einstellungen",
    "Working time settings": "Arbeitszeit-Einstellungen",
    "In minutes. 360 is six hours.": "In Minuten. 360 sind sechs Stunden.",
    "break": "Pause",
    "In minutes.": "In Minuten.",
    "break rule": "Pausenregel",
    "break rules": "Pausenregeln",
    "the same for everybody who has it": "für alle gleich, die ihn haben",
    "scaled by working days, like the annual leave": "anteilig nach Arbeitstagen, wie der Jahresurlaub",
    "from a table of working days per week": "aus einer Tabelle nach Arbeitstagen pro Woche",
    "how it is worked out": "wie er berechnet wird",
    "For “the same for everybody”, the number itself. For “scaled”, what a full-time employee would get.":
        "Bei „für alle gleich“ die Zahl selbst. Bei „anteilig“ das, was eine Vollzeitkraft bekäme.",
    "offered": "wird angeboten",
    "Switching this off keeps the leave already taken and stops it being granted to anybody new.":
        "Abschalten behält den bereits genommenen Urlaub und verhindert, dass die Art neu vergeben wird.",
    "special leave type": "Sonderurlaubsart",
    "special leave types": "Sonderurlaubsarten",
    "A leave type worked out from a table needs at least one row in it.":
        "Eine aus einer Tabelle berechnete Urlaubsart braucht mindestens eine Zeile.",
    "working days per week, at least": "Arbeitstage pro Woche, mindestens",
    "threshold": "Staffel",
    "thresholds": "Staffeln",
    "The working time rules were saved.": "Die Arbeitszeitregeln wurden gespeichert.",
    "There are already break rules; nothing was changed.":
        "Es gibt bereits Pausenregeln; es wurde nichts geändert.",
    "The usual break rules were added.": "Die üblichen Pausenregeln wurden hinzugefügt.",
    "“%(name)s” cannot be deleted: leave has been taken against it and the record of it would lose its name. Switch it off instead — nobody new gets it and the days already taken keep their meaning.":
        "„%(name)s“ kann nicht gelöscht werden: es wurde bereits Urlaub darauf genommen, und dessen Nachweis verlöre seinen Namen. Schalten Sie die Art stattdessen ab — niemand bekommt sie neu, und die bereits genommenen Tage behalten ihre Bedeutung.",
    "%(added)s public holidays for %(year)s in %(land)s. %(removed)s previously generated ones were replaced; anything added by hand was left alone.":
        "%(added)s Feiertage für %(year)s in %(land)s. %(removed)s zuvor berechnete wurden ersetzt; von Hand hinzugefügte blieben unangetastet.",
    "“%(name)s” was saved and applied to everybody currently employed.":
        "„%(name)s“ wurde gespeichert und für alle derzeit Beschäftigten eingetragen.",
    "“%(name)s” was deleted and the days it took off everybody were given back.":
        "„%(name)s“ wurde gelöscht; die dadurch abgezogenen Tage wurden allen zurückgegeben.",

    # -- roster ----------------------------------------------------------
    "That day is not in the week being planned.": "Dieser Tag liegt nicht in der geplanten Woche.",
    "A shift needs a length.": "Eine Schicht braucht eine Dauer.",
    "copy from the week beginning": "kopieren aus der Woche ab",
    "Shown on the card — “group 2”, “outing”, anything the shift needs saying about.":
        "Erscheint auf der Karte — „Gruppe 2“, „Ausflug“, was zur Schicht zu sagen ist.",
    "shift": "Schicht",
    "shifts": "Schichten",
    "The roster was saved.": "Der Dienstplan wurde gespeichert.",
    "The roster was not saved — see the cards marked below.":
        "Der Dienstplan wurde nicht gespeichert — siehe die markierten Karten unten.",
    "That is not a date this app can read.": "Das ist kein Datum, das diese App lesen kann.",
    "That is this week — copying it onto itself would double every shift.":
        "Das ist diese Woche — sie auf sich selbst zu kopieren würde jede Schicht verdoppeln.",
    "%(count)s shifts were copied from the week of %(from)s. They were added to what was already here, so anything that is now doubled can be dragged off.":
        "%(count)s Schichten wurden aus der Woche ab %(from)s kopiert. Sie wurden zum Vorhandenen hinzugefügt; was jetzt doppelt ist, lässt sich wegziehen.",
    "That week has no shifts to copy.": "In dieser Woche gibt es keine Schichten zum Kopieren.",
    "%(count)s shifts were drafted from the contracts, starting at %(start)s. Days that already had somebody on them were left alone — drag the cards to where they belong.":
        "%(count)s Schichten wurden aus den Verträgen entworfen, beginnend um %(start)s. Tage, an denen bereits jemand eingeteilt war, blieben unangetastet — ziehen Sie die Karten dorthin, wo sie hingehören.",
    "Nothing to draft: everybody who works this week is already rostered.":
        "Nichts zu entwerfen: alle, die diese Woche arbeiten, sind bereits eingeteilt.",
    "The shift was removed.": "Die Schicht wurde entfernt.",

    # -- timesheets ------------------------------------------------------
    "This stretch has no length.": "Dieser Abschnitt hat keine Dauer.",
    "A day needs at least one stretch of work. If you did not work at all, delete the day instead.":
        "Ein Tag braucht mindestens einen Arbeitsabschnitt. Wenn Sie gar nicht gearbeitet haben, löschen Sie den Tag.",
    "work the break out from the rules": "Pause aus den Regeln berechnen",
    "Uncheck to enter a different break. A break entered by hand is shown in amber.":
        "Haken entfernen, um eine andere Pause einzutragen. Eine von Hand eingetragene Pause wird bernsteinfarben angezeigt.",
    "Enter the break, or tick the box to have it worked out.":
        "Tragen Sie die Pause ein, oder setzen Sie den Haken, damit sie berechnet wird.",
    "confirmed as rostered": "wie geplant bestätigt",
    "entered by hand": "von Hand eingetragen",
    "break entered by hand": "Pause von Hand eingetragen",
    "day": "Tag",
    "work segment": "Arbeitsabschnitt",
    "work segments": "Arbeitsabschnitte",
    "The day was saved.": "Der Tag wurde gespeichert.",
    "There is nothing rostered on that day, so there is nothing to confirm. Enter the hours instead.":
        "An diesem Tag ist nichts eingeteilt, es gibt also nichts zu bestätigen. Tragen Sie die Stunden ein.",
    "%(date)s was confirmed: %(hours)s worked.": "%(date)s wurde bestätigt: %(hours)s gearbeitet.",
    "%(confirmed)s days were confirmed. %(skipped)s already had hours entered and were left exactly as they are.":
        "%(confirmed)s Tage wurden bestätigt. Bei %(skipped)s waren bereits Stunden eingetragen; sie blieben unverändert.",
    "%(confirmed)s days were confirmed.": "%(confirmed)s Tage wurden bestätigt.",
    "Every rostered day this week already has hours entered, so nothing was changed.":
        "An jedem eingeteilten Tag dieser Woche sind bereits Stunden eingetragen; es wurde nichts geändert.",
    "There is nothing rostered this week to confirm.":
        "Diese Woche ist nichts eingeteilt, das bestätigt werden könnte.",

    # -- languages and the shell ----------------------------------------
    "German": "Deutsch",
    "English": "Englisch",
    "Language": "Sprache",
    "Time off": "Abwesenheit",
    "Time Tracking": "Zeiterfassung",
    "Skip to content": "Zum Inhalt springen",
    "Start": "Start",
    "My time": "Meine Zeit",
    "Timesheet": "Stundenzettel",
    "Team": "Team",
    "Roster": "Dienstplan",
    "Timesheets": "Stundenzettel",
    "Employees": "Mitarbeitende",
    "Settings": "Einstellungen",
    "Working time": "Arbeitszeit",
    "Administration": "Verwaltung",
    "Sign out": "Abmelden",
    "Toggle navigation": "Navigation ein-/ausblenden",
    "Unsaved changes": "Ungespeicherte Änderungen",
    "You have unsaved changes on this page. Do you want to save them before leaving?":
        "Auf dieser Seite gibt es ungespeicherte Änderungen. Möchten Sie sie vor dem Verlassen speichern?",
    "Discard": "Verwerfen",
    "Cancel": "Abbrechen",
    "Close": "Schließen",
    "Save": "Speichern",
    "Save changes": "Änderungen speichern",
    "Edit": "Bearbeiten",
    "Delete": "Löschen",
    "Remove": "Entfernen",
    "Back": "Zurück",
    "Help": "Hilfe",
    "Show": "Anzeigen",
    "Copy": "Kopieren",
    "Name": "Name",
    "Year": "Jahr",
    "Week": "Woche",
    "Day": "Tag",
    "Date": "Datum",
    "Days": "Tage",
    "Hours": "Stunden",
    "From": "Von",
    "To": "Bis",
    "Type": "Art",
    "Reason": "Anmerkung",
    "State": "Status",
    "Note": "Anmerkung",
    "Employee": "Mitarbeiter/in",
    "Leave": "Urlaub",
    "Contract": "Vertrag",
    "Break": "Pause",
    "Shift": "Schicht",
    "min": "Min.",
    "minutes": "Minuten",
    "h": "Std.",
    "never": "nie",
    "left": "ausgeschieden",
    "manager": "Leitung",
    "waiting": "wartet",
    "confirmed": "bestätigt",
    "not confirmed": "nicht bestätigt",
    "differs": "abweichend",
    "away": "abwesend",
    "not yet": "noch nicht",
    "no contract": "kein Vertrag",
    "not offered": "nicht angeboten",
    "switched off": "abgeschaltet",
    "worked out": "berechnet",
    "added by hand": "von Hand ergänzt",
    "asked for": "beantragt",
    "or": "oder",
    "Previous": "Zurück",
    "This week": "Diese Woche",
    "Next": "Weiter",
    "Total": "Summe",
    "Difference": "Differenz",
    "Worked": "Gearbeitet",
    "Rostered": "Eingeteilt",
    "Contracted": "Vertraglich",
    "Confirm": "Bestätigen",
    "Approve": "Genehmigen",
    "Decline": "Ablehnen",
    "Withdraw": "Zurückziehen",
    "Reply": "Antwort",
    "Reply:": "Antwort:",
    "Dates": "Zeitraum",
    "Decision": "Entscheidung",
    "By": "Von",
    "Entitled": "Anspruch",
    "Taken": "Genommen",
    "Left": "Rest",
    "Waiting": "Wartet",
    "Actions": "Aktionen",
    "Rights": "Rechte",
}
