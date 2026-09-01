"""The page-level German strings — headings, leads and the help panels.

Split from ``translations_de.py`` only because one file of nine hundred lines is
one nobody scrolls through. The two are merged by
``tools/apply_translations.py``; a key in both is a mistake and that script
refuses rather than picking one.

The long entries here are the ones that carry the *reasoning* — why a part-time
entitlement is what it is, why a sick day costs nothing, why an overridden break
is a different colour. They are the most important strings in the app: they are
what stops somebody opening a ticket about a number they think is wrong.
"""

PAGES = {
    # -- the sign-in page -----------------------------------------------
    "Sign in": "Anmelden",
    "Wrong username or password. Please try again.":
        "Benutzername oder Passwort ist falsch. Bitte versuchen Sie es erneut.",
    "Sign in with SSO": "Mit SSO anmelden",
    "Sign in with a local account": "Mit lokalem Konto anmelden",
    "Username": "Benutzername",
    "Show password (hold)": "Passwort anzeigen (gedrückt halten)",

    # -- my settings ------------------------------------------------------

    # -- time off ---------------------------------------------------------
    "My time off": "Meine Abwesenheiten",
    "Days a year": "Tage pro Jahr",
    "Sick days": "Krankheitstage",
    "Days you have asked for are not taken off yet — a request that is declined has not been spent. If everything waiting is approved you will have %(left)s left.":
        "Beantragte Tage sind noch nicht abgezogen — ein abgelehnter Antrag hat nichts verbraucht. Wenn alles Wartende genehmigt wird, bleiben Ihnen %(left)s.",
    "You work %(days)s days a week. A full week here is %(full)s days and carries %(entitlement)s days of leave, so yours is that share of it. Days you are not due to work, and public holidays, never come out of it.":
        "Sie arbeiten %(days)s Tage pro Woche. Eine volle Woche sind hier %(full)s Tage und bringt %(entitlement)s Urlaubstage; Ihr Anspruch ist der entsprechende Anteil davon. Tage, an denen Sie nicht eingeteilt sind, und Feiertage gehen nie davon ab.",
    "Ask for time off": "Abwesenheit beantragen",
    "New request": "Neuer Antrag",
    "Send for approval": "Zur Genehmigung senden",
    "Sickness": "Krankheit",
    "You are recorded as ill.": "Sie sind als krank eingetragen.",
    "Report sickness": "Krankheit melden",
    "Record it": "Eintragen",
    "This year": "Dieses Jahr",
    "Withdraw this?": "Diesen Antrag zurückziehen?",
    "It stays in the list as withdrawn, so the record still shows that it was asked for.":
        "Er bleibt als zurückgezogen in der Liste, damit der Vorgang nachvollziehbar bleibt.",
    "Last day of illness": "Letzter Krankheitstag",
    "Say when it ended": "Ende eintragen",
    "Nothing recorded for this year.": "Für dieses Jahr ist nichts eingetragen.",

    # -- no contract ------------------------------------------------------
    "No contract": "Kein Vertrag",
    "There is no contract on this account": "Zu diesem Konto gehört kein Vertrag",
    "Timesheets and leave belong to an employee record, and this account is not linked to one yet.":
        "Stundenzettel und Urlaub gehören zu einem Mitarbeitendendatensatz, und dieses Konto ist noch mit keinem verknüpft.",
    "If you should have one": "Falls Sie einen haben sollten",
    "If you should not": "Falls Sie keinen haben sollten",
    "That is normal for an account that administers the app rather than working shifts. Nothing is wrong and nothing needs doing.":
        "Das ist normal für ein Konto, das die App verwaltet und keine Schichten arbeitet. Es ist nichts falsch und nichts zu tun.",

    # -- requests ---------------------------------------------------------
    "Requests": "Anträge",
    "Time off waiting for a decision": "Abwesenheiten, die auf eine Entscheidung warten",
    "Entitled to": "Anspruch",
    "Already taken": "Bereits genommen",
    "Left now": "Aktuell übrig",
    "Left if everything waiting is approved": "Übrig, wenn alles Wartende genehmigt wird",
    "Approving everything this person has asked for would take them past their entitlement.":
        "Alles zu genehmigen, was diese Person beantragt hat, überschritte ihren Anspruch.",
    "A sentence back to them — required when declining":
        "Ein Satz zurück — bei einer Ablehnung erforderlich",
    "Nothing is waiting for a decision.": "Es wartet nichts auf eine Entscheidung.",
    "Recently decided": "Zuletzt entschieden",
    "Nothing has been decided yet.": "Es wurde noch nichts entschieden.",

    # -- the SSO settings page -------------------------------------------
    "Sign-in": "Anmeldung",
    "Single sign-on": "Single Sign-on",
    "Help for this page": "Hilfe zu dieser Seite",
    "Signing in through SSO": "Anmeldung über SSO",
    "Setting this up is three steps and two of them are on the provider. Work down this page in order.":
        "Die Einrichtung hat drei Schritte, zwei davon beim Anbieter. Arbeiten Sie diese Seite der Reihe nach durch.",
    "Step 1 — give the provider this redirect URI": "Schritt 1 — dem Anbieter diese Redirect-URI geben",
    "Register this as the redirect URI (some providers call it callback or reply URL). It must match exactly, trailing slash included. The provider then gives you a client ID and a secret for step 2.":
        "Tragen Sie dies als Redirect-URI ein (manche Anbieter nennen es Callback- oder Reply-URL). Sie muss exakt übereinstimmen, einschließlich des abschließenden Schrägstrichs. Der Anbieter gibt Ihnen daraufhin eine Client-ID und ein Secret für Schritt 2.",
    "This is built from the app’s configured public address, not from the address you are on now (%(browsing)s) — that one is only reachable inside the house, and a provider cannot send a browser back to it.":
        "Sie wird aus der konfigurierten öffentlichen Adresse der App gebildet, nicht aus der Adresse, auf der Sie gerade sind (%(browsing)s) — die ist nur intern erreichbar, und ein Anbieter kann keinen Browser dorthin zurückschicken.",
    "This page has never been saved, so what you see below is what the container’s environment configured. Nothing is wrong — it is a starting point. The first save copies it into the database, and from then on this page is the only thing that decides how sign-in works.":
        "Diese Seite wurde noch nie gespeichert; was Sie unten sehen, stammt aus der Umgebung des Containers. Es ist nichts falsch — es ist ein Ausgangspunkt. Das erste Speichern übernimmt es in die Datenbank, und von da an entscheidet allein diese Seite, wie die Anmeldung funktioniert.",
    "Nothing was saved. Fix these first:": "Es wurde nichts gespeichert. Beheben Sie zuerst dies:",
    "The stored client secret cannot be read any more. That happens when DJANGO_SECRET_KEY changes — the secret is encrypted with a key derived from it. Enter the secret again below.":
        "Das gespeicherte Client-Secret ist nicht mehr lesbar. Das passiert, wenn DJANGO_SECRET_KEY sich ändert — das Secret ist mit einem daraus abgeleiteten Schlüssel verschlüsselt. Tragen Sie es unten erneut ein.",
    "One of the addresses below is plain http. The client secret and the tokens would cross the network unencrypted. This is only reasonable on a LAN you trust.":
        "Eine der Adressen unten ist einfaches http. Client-Secret und Tokens gingen unverschlüsselt über das Netz. Das ist nur in einem vertrauenswürdigen LAN vertretbar.",
    "What this container can reach": "Was dieser Container erreicht",
    "Any HTTP answer counts as reachable — a 404 still proves the network path and the certificate work. Whether the address is the right one is what “Read the endpoints from the server” is for.":
        "Jede HTTP-Antwort gilt als erreichbar — auch ein 404 beweist, dass Netzweg und Zertifikat funktionieren. Ob die Adresse die richtige ist, klärt „Endpunkte vom Server lesen“.",
    "Offer the single sign-on button": "Die Single-Sign-on-Schaltfläche anbieten",
    "Step 2 — the SSO server": "Schritt 2 — der SSO-Server",
    "Address": "Adresse",
    "This is the only address you should have to type. Saving reads the provider’s discovery document and fills the four endpoints in from it — do not copy them from documentation, because providers move them between versions.":
        "Dies ist die einzige Adresse, die Sie eingeben sollten. Beim Speichern wird das Discovery-Dokument des Anbieters gelesen und die vier Endpunkte werden daraus gefüllt — kopieren Sie sie nicht aus einer Dokumentation, denn Anbieter verschieben sie zwischen Versionen.",
    "not set": "nicht gesetzt",
    "Read from the server on %(when)s.": "Am %(when)s vom Server gelesen.",
    "Entered by hand.": "Von Hand eingetragen.",
    "Not read from the server yet — these are guesses from the address above. Press Save to read the real ones.":
        "Noch nicht vom Server gelesen — dies sind Vermutungen aus der Adresse oben. Speichern Sie, um die echten zu lesen.",
    "Enter the endpoints by hand instead": "Endpunkte stattdessen von Hand eintragen",
    "For a provider that publishes no discovery document. Anything filled in here wins over what the server says, and is left alone on save unless the address above changes.":
        "Für einen Anbieter ohne Discovery-Dokument. Was hier steht, hat Vorrang vor dem, was der Server sagt, und bleibt beim Speichern unangetastet, solange die Adresse oben sich nicht ändert.",
    "Authorisation endpoint": "Autorisierungs-Endpunkt",
    "Token endpoint": "Token-Endpunkt",
    "User info endpoint": "Benutzerinfo-Endpunkt",
    "Step 3 — the client the provider issued": "Schritt 3 — der vom Anbieter ausgestellte Client",
    "Both of these come from the provider, after you gave it the redirect URI at the top.":
        "Beides bekommen Sie vom Anbieter, nachdem Sie ihm oben die Redirect-URI gegeben haben.",
    "Client ID": "Client-ID",
    "A secret is stored. Leave empty to keep it.": "Ein Secret ist gespeichert. Leer lassen, um es zu behalten.",
    "Nothing stored yet.": "Noch nichts gespeichert.",
    "Signature algorithm": "Signaturalgorithmus",
    "Scopes": "Scopes",
    "Request timeout": "Zeitlimit",
    "Who may sign in": "Wer sich anmelden darf",
    "Allowed groups": "Erlaubte Gruppen",
    "Group claim": "Gruppen-Claim",
    "Administrator group": "Administratorgruppe",
    "Verify the SSO server’s certificate": "Zertifikat des SSO-Servers prüfen",
    "Read the endpoints from the server": "Endpunkte vom Server lesen",
    "Check the connection": "Verbindung prüfen",
    "Both read what is currently saved, not what is typed above — save first.":
        "Beide lesen den gespeicherten Stand, nicht das oben Eingetippte — speichern Sie zuerst.",
    "Setting up single sign-on": "Single Sign-on einrichten",
    "The order the three steps happen in": "Die Reihenfolge der drei Schritte",
    "The redirect URI comes first because the provider asks for it before it will issue anything: you register this app there, give it that address, and it hands back a client ID and a secret. Those two come back here for step 3. Nothing on this page has to be saved before you can copy the redirect URI — it is at the top on every visit.":
        "Die Redirect-URI kommt zuerst, weil der Anbieter sie verlangt, bevor er irgendetwas ausstellt: Sie registrieren diese App dort, geben ihr die Adresse, und bekommen Client-ID und Secret zurück. Diese beiden kommen hierher in Schritt 3. Zum Kopieren der Redirect-URI muss auf dieser Seite nichts gespeichert sein — sie steht bei jedem Besuch oben.",
    "Why there is only one address to type": "Warum nur eine Adresse einzugeben ist",
    "Saving asks the provider for its discovery document and reads the authorisation, token, user info and JWKS addresses out of it. You can paste either the issuer or the full …/.well-known/openid-configuration address — both are understood. The endpoints are shown afterwards with the date they were read, and there is a disclosure below them for a provider that publishes no discovery document at all.":
        "Beim Speichern wird das Discovery-Dokument des Anbieters abgerufen und daraus werden Autorisierungs-, Token-, Benutzerinfo- und JWKS-Adresse gelesen. Sie können den Issuer oder die vollständige Adresse …/.well-known/openid-configuration einfügen — beides wird verstanden. Die Endpunkte werden danach mit dem Datum ihres Abrufs angezeigt; darunter gibt es einen Bereich für Anbieter ganz ohne Discovery-Dokument.",
    "If a save seems to do nothing": "Wenn ein Speichern nichts zu bewirken scheint",
    "It did not save, and the reason is listed in red at the top of the page. Every error is collected there and links to the field it belongs to, including fields inside the closed sections — an error on a box you cannot see is the one case where a page looks like it is ignoring you.":
        "Dann wurde nicht gespeichert, und der Grund steht rot oben auf der Seite. Alle Fehler werden dort gesammelt und verweisen auf das zugehörige Feld, auch auf Felder in zugeklappten Bereichen — ein Fehler an einem Feld, das man nicht sieht, ist der eine Fall, in dem eine Seite wirkt, als ignoriere sie einen.",
    "The order that cannot lock you out": "Die Reihenfolge, die Sie nicht aussperrt",
    "Fill everything in with the switch at the top still off, save, press “Check the connection”, and only then switch it on. The local password form stays available either way — it is at /accounts/login/?local=1 even when the single sign-on button is the only thing on the page.":
        "Füllen Sie alles aus, während der Schalter oben noch aus ist, speichern Sie, drücken Sie „Verbindung prüfen“, und schalten Sie ihn erst dann ein. Das lokale Passwortformular bleibt in jedem Fall erreichbar — unter /accounts/login/?local=1, auch wenn auf der Seite nur die Single-Sign-on-Schaltfläche steht.",
    "If the login reaches the provider and then fails":
        "Wenn die Anmeldung den Anbieter erreicht und dann scheitert",
    "That is almost always the container being unable to reach the SSO server itself, which it has to do for the token exchange. “Check the connection” asks that question from inside the container. If the browser can reach the server and this cannot, it is your router not sending internal traffic back to itself.":
        "Dann kann fast immer der Container selbst den SSO-Server nicht erreichen, was er für den Token-Austausch tun muss. „Verbindung prüfen“ stellt genau diese Frage aus dem Container heraus. Wenn der Browser den Server erreicht und dies nicht, schickt Ihr Router internen Verkehr nicht zu sich selbst zurück.",
    "Where the secret is kept": "Wo das Secret liegt",
    "In the database, encrypted with a key derived from DJANGO_SECRET_KEY — so a copy of the database alone does not reveal it, but a backup taken together with the environment does. Change DJANGO_SECRET_KEY and the secret has to be entered again.":
        "In der Datenbank, verschlüsselt mit einem aus DJANGO_SECRET_KEY abgeleiteten Schlüssel — eine Kopie der Datenbank allein gibt es also nicht preis, eine Sicherung zusammen mit der Umgebung schon. Ändert sich DJANGO_SECRET_KEY, muss das Secret neu eingetragen werden.",

    # -- people -----------------------------------------------------------
    "New account": "Neues Konto",

    "All people": "Alle Personen",
    "This account signs in both ways: with its own password, and through SSO. The two were linked because they share an e-mail address. Its name and e-mail address come from the identity provider and are refreshed at every sign-in, so they cannot be changed here.":
        "Dieses Konto meldet sich auf beiden Wegen an: mit eigenem Passwort und über SSO. Beide wurden verknüpft, weil sie sich eine E-Mail-Adresse teilen. Name und E-Mail-Adresse kommen vom Identitätsanbieter und werden bei jeder Anmeldung erneuert; sie lassen sich hier nicht ändern.",
    "This account signs in through SSO. Its name and e-mail address come from the identity provider and are refreshed at every sign-in, so they cannot be changed here. What this page can change is whether they may sign in at all, and what they may do once they are in.":
        "Dieses Konto meldet sich über SSO an. Name und E-Mail-Adresse kommen vom Identitätsanbieter und werden bei jeder Anmeldung erneuert; sie lassen sich hier nicht ändern. Diese Seite kann ändern, ob sich die Person überhaupt anmelden darf und was sie danach tun darf.",
    "First name": "Vorname",
    "Surname": "Nachname",
    "E-mail": "E-Mail",
    "What they may do": "Was die Person darf",
    "May sign in": "Darf sich anmelden",
    "May manage people": "Darf Konten verwalten",
    "Gives access to this page, and to the Django administration behind it.":
        "Gibt Zugang zu dieser Seite und zur dahinterliegenden Django-Verwaltung.",
    "Administrator": "Administrator",
    "Full rights, including the recovery path when something is wrong. There must always be one active.":
        "Volle Rechte, einschließlich des Wegs zurück, wenn etwas nicht stimmt. Es muss immer ein aktiver vorhanden sein.",
    "If a provider group is configured as the administrator group, the provider decides this at every sign-in and anything set here is replaced.":
        "Ist eine Anbietergruppe als Administratorgruppe konfiguriert, entscheidet der Anbieter dies bei jeder Anmeldung und überschreibt, was hier gesetzt ist.",
    "Create the account": "Konto anlegen",
    "Set a new password": "Neues Passwort setzen",
    "Unlink this account from SSO?": "Dieses Konto von SSO trennen?",
    "They will sign in with their password only. Their employee record and every hour on it stay with the account. Signing in through the provider afterwards creates a separate account — unless the e-mail addresses still match, which links them again.":
        "Die Person meldet sich dann nur noch mit Passwort an. Ihr Mitarbeitendendatensatz und jede darin erfasste Stunde bleiben am Konto. Eine spätere Anmeldung über den Anbieter legt ein eigenes Konto an — es sei denn, die E-Mail-Adressen stimmen weiterhin überein, dann werden sie erneut verknüpft.",
    "Unlink": "Trennen",
    "Linked to the provider identity %(subject)s.": "Verknüpft mit der Anbieter-Identität %(subject)s.",
    "People": "Personen",
    "Add an account": "Konto hinzufügen",
    "Signs in with": "Meldet sich an mit",
    "Last seen": "Zuletzt gesehen",
    "Identity from the provider": "Identität vom Anbieter",
    "SSO": "SSO",
    "Manages people": "Verwaltet Konten",
    "Signs in": "Meldet sich an",
    "Switch this account off?": "Dieses Konto abschalten?",
    "Switch this account on?": "Dieses Konto einschalten?",
    "They will not be able to sign in. Every hour they have worked is kept and nothing is deleted.":
        "Die Person kann sich dann nicht mehr anmelden. Jede geleistete Stunde bleibt erhalten, es wird nichts gelöscht.",
    "They will be able to sign in again.": "Die Person kann sich wieder anmelden.",
    "Switch off": "Abschalten",
    "Switch on": "Einschalten",
    "Delete this account?": "Dieses Konto löschen?",
    "The account is removed for good. Their employee record and every hour on it are kept, but the two are no longer linked and they cannot sign in. Switching the account off is the reversible version of this.":
        "Das Konto wird endgültig entfernt. Der Mitarbeitendendatensatz und jede darin erfasste Stunde bleiben erhalten, aber beide sind nicht mehr verknüpft und die Person kann sich nicht anmelden. Das Konto abzuschalten ist die umkehrbare Variante davon.",
    "Nobody yet.": "Noch niemand.",
    "Accounts in this app": "Konten in dieser App",
    "Two kinds": "Zwei Arten",
    "An account marked “SSO” is the local end of an identity held by the provider. Its name and e-mail are copied from there at every sign-in, so changing them here would be undone; its password lives with the provider and cannot be set from this app at all.":
        "Ein mit „SSO“ markiertes Konto ist das lokale Ende einer Identität beim Anbieter. Name und E-Mail werden bei jeder Anmeldung von dort übernommen; eine Änderung hier würde also rückgängig gemacht. Das Passwort liegt beim Anbieter und lässt sich aus dieser App gar nicht setzen.",
    "An account marked “Password” was created here. Use one for somebody who works here but has no account with the provider — and keep one as the way back in when SSO is the thing that is broken.":
        "Ein mit „Passwort“ markiertes Konto wurde hier angelegt. Nutzen Sie eines für Personen, die hier arbeiten, aber kein Konto beim Anbieter haben — und behalten Sie eines als Weg zurück, wenn ausgerechnet SSO nicht funktioniert.",
    "Why somebody is missing": "Warum jemand fehlt",
    "This app has no way to read the provider’s list of accounts. An SSO account appears here the first time it signs in, and not before.":
        "Diese App kann die Kontenliste des Anbieters nicht lesen. Ein SSO-Konto erscheint hier bei der ersten Anmeldung und nicht früher.",
    "Switching off, or deleting": "Abschalten oder löschen",
    "Switching an account off is reversible and keeps everything. Deleting is not — but it never takes a timesheet with it: an employee record and the hours on it survive the account being removed, because somebody who has left still worked them.":
        "Ein Konto abzuschalten ist umkehrbar und behält alles. Löschen ist es nicht — aber es nimmt nie einen Stundenzettel mit: Mitarbeitendendatensatz und Stunden überleben das Entfernen des Kontos, denn wer ausgeschieden ist, hat sie trotzdem gearbeitet.",
    "New password": "Neues Passwort",
    "A new password for %(name)s": "Ein neues Passwort für %(name)s",
    "There is no “old password” box: this is the organisation’s way back in when somebody has forgotten theirs, and asking for the old one would make it useless for the only case it exists for.":
        "Es gibt kein Feld für das alte Passwort: dies ist der Weg zurück, wenn jemand seines vergessen hat, und nach dem alten zu fragen machte es für genau den Fall unbrauchbar, für den es existiert.",
    "Set the password": "Passwort setzen",

    # -- the contract -----------------------------------------------------
    "New employee": "Neue Person",
    "Who they are": "Wer die Person ist",
    "The account they sign in with": "Das Konto, mit dem sie sich anmeldet",
    "Account": "Konto",
    "— none yet —": "— noch keines —",
    "The working week": "Die Arbeitswoche",
    "Hours per day. A day with nothing in it is a day they do not work — which is what decides whether being away on it costs them a day of leave. 20 hours can be 8, 8 and 4 on three days, or 4 on each of five; the two are different contracts and this is where the difference lives.":
        "Stunden pro Tag. Ein Tag ohne Eintrag ist ein Tag, an dem nicht gearbeitet wird — und davon hängt ab, ob eine Abwesenheit an diesem Tag einen Urlaubstag kostet. 20 Stunden können 8, 8 und 4 an drei Tagen sein oder je 4 an fünf Tagen; das sind zwei verschiedene Verträge, und hier liegt der Unterschied.",
    "Hours a week": "Stunden pro Woche",
    "Working days a week": "Arbeitstage pro Woche",
    "Leave days a year": "Urlaubstage pro Jahr",
    "Only what this person has been given. A type that exists in the organisation but is not listed here is not theirs — it is not “zero days of it”.":
        "Nur, was dieser Person gewährt wurde. Eine Art, die es im Betrieb gibt und die hier nicht steht, gehört ihr nicht — es sind nicht „null Tage davon“.",
    "Days instead of the rule": "Tage abweichend von der Regel",
    "Grant a special leave type": "Sonderurlaubsart gewähren",
    "Save the contract": "Vertrag speichern",
    "Leave balance": "Urlaubskonto",
    "Only possible while there is nothing recorded. Once there are hours, shifts or absences, switching the employee off is the operation you want — it takes them off the roster and keeps every hour they worked.":
        "Nur möglich, solange nichts erfasst ist. Sobald es Stunden, Schichten oder Abwesenheiten gibt, ist das Abschalten der richtige Vorgang — es nimmt die Person aus dem Dienstplan und behält jede geleistete Stunde.",
    "Delete this employee?": "Diese Person löschen?",
    "This cannot be undone. If anything has been recorded for them, the app will refuse and tell you to switch them off instead.":
        "Das lässt sich nicht rückgängig machen. Ist etwas erfasst, verweigert die App den Vorgang und schlägt stattdessen das Abschalten vor.",
    "Worked out": "Berechnet",
    "set on this contract": "in diesem Vertrag gesetzt",
    "Everything recorded this year": "Alles in diesem Jahr Erfasste",
    "Working days": "Arbeitstage",
    "Charged": "Angerechnet",
    "Nothing recorded this year.": "In diesem Jahr ist nichts erfasst.",
    "Back to the contract": "Zurück zum Vertrag",
    "Their timesheet": "Ihr Stundenzettel",
    "Add someone": "Person hinzufügen",
    "A full week here is %(days)s days and carries %(leave)s days of leave. Everybody’s entitlement is that share of it, worked out from the days their contract gives hours to.":
        "Eine volle Woche sind hier %(days)s Tage und bringt %(leave)s Urlaubstage. Der Anspruch aller ist der entsprechende Anteil davon, berechnet aus den Tagen, für die ihr Vertrag Stunden vorsieht.",
    "Set by hand on the contract, not worked out from the working days.":
        "Im Vertrag von Hand gesetzt, nicht aus den Arbeitstagen berechnet.",
    "Nobody has been added yet.": "Es wurde noch niemand angelegt.",

    # -- closures and holidays --------------------------------------------
    "New closure": "Neue Schließzeit",

    "Saving this writes an absence for everybody currently employed, and re-saving it moves them rather than adding a second set. Somebody who joins afterwards does not get one — a closure they were not here for is not theirs.":
        "Das Speichern trägt für alle derzeit Beschäftigten eine Abwesenheit ein; erneutes Speichern verschiebt diese, statt einen zweiten Satz anzulegen. Wer später eintritt, bekommt keine — eine Schließzeit, in der jemand nicht hier war, ist nicht seine.",
    "Save and apply": "Speichern und eintragen",
    "Closures": "Schließzeiten",
    "When the workplace is shut": "Wenn der Betrieb geschlossen ist",
    "Two weeks in August, the days between Christmas and New Year — periods nobody is expected in. Saving one records the absence for everybody currently employed, and by default it comes out of their leave, which is what Betriebsferien normally means. Days somebody was not due to work, and public holidays, are never charged.":
        "Zwei Wochen im August, die Tage zwischen Weihnachten und Neujahr — Zeiträume, in denen niemand erwartet wird. Das Speichern trägt die Abwesenheit für alle derzeit Beschäftigten ein und geht standardmäßig vom Urlaub ab, wie es bei Betriebsferien üblich ist. Tage, an denen jemand ohnehin nicht eingeteilt war, und Feiertage werden nie angerechnet.",
    "Rules": "Regeln",
    "Public holidays": "Feiertage",
    "paid, not deducted": "bezahlt, nicht abgezogen",
    "Delete this closure?": "Diese Schließzeit löschen?",
    "The days it took off everybody are given back. Nothing else is affected.":
        "Die dadurch abgezogenen Tage werden allen zurückgegeben. Sonst ändert sich nichts.",
    "No closures recorded.": "Keine Schließzeiten erfasst.",
    "Worked out for %(land)s — nine of the thirteen German public holidays depend on the Land, and the Land is set on the Rules page. A public holiday is never taken off anybody’s leave, and nobody is expected in on one.":
        "Berechnet für %(land)s — neun der dreizehn deutschen Feiertage hängen vom Bundesland ab, und das Bundesland wird auf der Seite „Regeln“ gesetzt. Ein Feiertag geht nie vom Urlaub ab, und es wird an ihm niemand erwartet.",
    "Generate this year’s holidays?": "Feiertage dieses Jahres erzeugen?",
    "Previously generated rows for this year are replaced. Anything you added by hand is left exactly as it is — which is how a holiday that is decided municipally, and that this app cannot know about, survives.":
        "Zuvor berechnete Einträge dieses Jahres werden ersetzt. Was Sie von Hand ergänzt haben, bleibt unverändert — so überlebt ein Feiertag, der auf Gemeindeebene gilt und den diese App nicht kennen kann.",
    "Generate": "Erzeugen",
    "Generate %(year)s": "%(year)s erzeugen",
    "Where it came from": "Herkunft",
    "Nothing for this year yet — press Generate.": "Für dieses Jahr noch nichts — drücken Sie „Erzeugen“.",
    "Fronleichnam in parts of Saxony and Thuringia, and Mariä Himmelfahrt in Catholic Bavaria, are decided by the municipality rather than the Land. This app answers at Land level, so in those four places check the list against your own town’s and add anything missing through the Django administration — generating the year again will not remove it.":
        "Fronleichnam in Teilen Sachsens und Thüringens sowie Mariä Himmelfahrt im katholischen Bayern werden von der Gemeinde und nicht vom Land bestimmt. Diese App antwortet auf Landesebene; prüfen Sie in diesen vier Ländern die Liste gegen die Ihrer Gemeinde und ergänzen Sie Fehlendes über die Django-Verwaltung — ein erneutes Erzeugen des Jahres entfernt es nicht.",

    # -- special leave types ----------------------------------------------
    "New leave type": "Neue Urlaubsart",

    "The table": "Die Tabelle",
    "Only read when the mode above is “from a table of working days per week”. Each row says: work at least this many days a week and get this many. It is a step, not a proportion — “three days or more gets one, five days gets two” means somebody on two days gets none, which is exactly what a table is for.":
        "Wird nur gelesen, wenn oben „aus einer Tabelle nach Arbeitstagen pro Woche“ gewählt ist. Jede Zeile sagt: wer mindestens so viele Tage pro Woche arbeitet, bekommt so viele. Es ist eine Stufe, kein Anteil — „ab drei Tagen einer, ab fünf Tagen zwei“ heißt, dass jemand mit zwei Tagen keinen bekommt, und genau dafür ist eine Tabelle da.",
    "Working days a week, at least": "Arbeitstage pro Woche, mindestens",
    "Days of this leave": "Tage dieser Urlaubsart",
    "Another row": "Weitere Zeile",
    "New type": "Neue Art",
    "Leave that is not the annual entitlement — a long-service day, a day for a child’s first school morning, whatever the agreement here says. Defining a type does not give it to anybody: it is granted on each employee’s contract, which is what makes it possible to offer it to some people and not others.":
        "Urlaub, der nicht der Jahresanspruch ist — ein Tag für lange Betriebszugehörigkeit, ein Tag für den ersten Schultag eines Kindes, was immer die Vereinbarung hier vorsieht. Eine Art zu definieren gewährt sie noch niemandem: sie wird im Vertrag jeder Person gewährt, und genau das macht es möglich, sie manchen anzubieten und anderen nicht.",
    "A full week gets": "Eine volle Woche bekommt",
    "Granted to": "Gewährt an",
    "%(days)s days a week → %(gets)s": "%(days)s Tage pro Woche → %(gets)s",
    "Delete this leave type?": "Diese Urlaubsart löschen?",
    "If leave has already been taken against it the app will refuse, because the record of it would lose its name. Switching it off is the version that always works.":
        "Wurde bereits Urlaub darauf genommen, verweigert die App den Vorgang, weil dessen Nachweis seinen Namen verlöre. Das Abschalten ist die Variante, die immer funktioniert.",
    "No special leave types yet.": "Noch keine Sonderurlaubsarten.",

    # -- the working time rules -------------------------------------------
    "The rules everything else in the app computes against. Changing one of these moves every employee’s figures at once, which is why this page is separate from the roster and why managing the roster does not open it.":
        "Die Regeln, gegen die alles andere in der App rechnet. Eine davon zu ändern verschiebt die Zahlen aller Beschäftigten auf einmal; deshalb ist diese Seite vom Dienstplan getrennt, und deshalb öffnet das Führen des Dienstplans sie nicht.",
    "What a full week is": "Was eine volle Woche ist",
    "Breaks": "Pausen",
    "Each row says: once the day’s working time would go over this long, a break of this many minutes is required. The app takes whichever row asks for the most.":
        "Jede Zeile sagt: sobald die Arbeitszeit des Tages darüber hinausginge, ist eine Pause von so vielen Minuten vorgeschrieben. Die App nimmt die Zeile, die am meisten verlangt.",
    "Working time over (hours)": "Arbeitszeit über (Stunden)",
    "Break (minutes)": "Pause (Minuten)",
    "Another tier": "Weitere Stufe",
    "Save the rules": "Regeln speichern",
    "There are no break rules yet": "Es gibt noch keine Pausenregeln",
    "Until there are, the app computes against the usual German ones anyway — so adding them here changes nothing except that you can then see and edit them.":
        "Solange es keine gibt, rechnet die App ohnehin gegen die üblichen deutschen — sie hier anzulegen ändert also nichts, außer dass Sie sie danach sehen und bearbeiten können.",
    "Over %(over)s hours of work: %(minutes)s minutes": "Über %(over)s Stunden Arbeit: %(minutes)s Minuten",
    "Add these": "Diese hinzufügen",
    "What that comes to": "Was dabei herauskommt",
    "Time at work": "Anwesenheit",
    "Counted as worked": "Als Arbeitszeit gezählt",

    # -- the roster --------------------------------------------------------
    "Draft this week from the contracts?": "Diese Woche aus den Verträgen entwerfen?",
    "Everybody who works a day this week and is not already rostered on it gets a shift starting at %(start)s, as long as their contract says. Days that already have somebody on them are left alone. It is a first draft — drag the cards where they belong.":
        "Alle, die diese Woche an einem Tag arbeiten und dort noch nicht eingeteilt sind, bekommen eine Schicht ab %(start)s, so lang wie ihr Vertrag es vorsieht. Tage, an denen bereits jemand eingeteilt ist, bleiben unangetastet. Es ist ein erster Entwurf — ziehen Sie die Karten dorthin, wo sie hingehören.",
    "Draft the week": "Woche entwerfen",
    "Fill from contracts": "Aus Verträgen füllen",
    "Copy that week here": "Diese Woche hierher kopieren",
    "Move to the previous day": "Auf den vorherigen Tag verschieben",
    "Move to the next day": "Auf den nächsten Tag verschieben",
    "Save the roster": "Dienstplan speichern",
    "Planning the week": "Die Woche planen",
    "Each column is a day. A card is one person’s shift on that day, and somebody can have more than one — a split shift is two cards.":
        "Jede Spalte ist ein Tag. Eine Karte ist die Schicht einer Person an diesem Tag, und es können mehrere sein — ein geteilter Dienst sind zwei Karten.",
    "Drag a card to another column to move the shift, or use the ‹ and › buttons on it. Nothing is written until you press Save.":
        "Ziehen Sie eine Karte in eine andere Spalte, um die Schicht zu verschieben, oder benutzen Sie die Schaltflächen ‹ und › darauf. Geschrieben wird nichts, bis Sie speichern.",
    "“Fill from contracts” drafts a whole week from everybody’s contracted hours, starting at the time set under Working time. It adds the break the day needs on top, because a contract counts working time and a shift is clock-in to clock-out.":
        "„Aus Verträgen füllen“ entwirft eine ganze Woche aus den vertraglichen Stunden aller, beginnend zu der unter „Arbeitszeit“ gesetzten Uhrzeit. Die für den Tag nötige Pause wird obendrauf gerechnet, denn ein Vertrag zählt Arbeitszeit und eine Schicht geht von Kommen bis Gehen.",
    "The pale bands are people who are already away. A band marked “asked for” is a request nobody has decided yet — deciding it and planning around it are the same job.":
        "Die blassen Balken sind Personen, die bereits abwesend sind. Ein mit „beantragt“ markierter Balken ist ein noch nicht entschiedener Antrag — ihn zu entscheiden und um ihn herum zu planen ist dieselbe Aufgabe.",

    # -- the day form ------------------------------------------------------
    "Hours for this day": "Stunden für diesen Tag",
    "What was rostered": "Was eingeteilt war",
    "I worked exactly this": "Genau so habe ich gearbeitet",
    "Nothing was rostered on this day, so enter the hours below.":
        "An diesem Tag war nichts eingeteilt; tragen Sie die Stunden unten ein.",
    "When you worked": "Wann Sie gearbeitet haben",
    "One row per stretch of work. A split shift — in for the morning, back in the afternoon — is two rows, and the break between them is not a break you enter below: it is simply time you were not here.":
        "Eine Zeile je Arbeitsabschnitt. Ein geteilter Dienst — vormittags da, nachmittags wieder — sind zwei Zeilen, und die Lücke dazwischen ist keine Pause, die Sie unten eintragen: es ist schlicht Zeit, in der Sie nicht da waren.",
    "Remove this stretch": "Diesen Abschnitt entfernen",
    "Another stretch": "Weiterer Abschnitt",
    "Time here": "Anwesenheit",
    "Break the rules require": "Vorgeschriebene Pause",
    "This day is confirmed. Saving a change here withdraws that confirmation, so the record never says somebody agreed to figures they have not seen.":
        "Dieser Tag ist bestätigt. Eine Änderung hier zu speichern zieht die Bestätigung zurück, damit der Nachweis nie behauptet, jemand habe Zahlen zugestimmt, die er nie gesehen hat.",
    "Save the day": "Tag speichern",

    # -- the start page ----------------------------------------------------
    "Hello %(name)s": "Hallo %(name)s",
    "You have no contract in this app yet": "Zu Ihrem Konto gehört noch kein Vertrag",
    "That is normal for an account that administers the app rather than working shifts. If you should have a timesheet, ask whoever manages the roster to add you as an employee — they can link this account to you on the Employees page.":
        "Das ist normal für ein Konto, das die App verwaltet und keine Schichten arbeitet. Falls Sie einen Stundenzettel haben sollten, bitten Sie die Person, die den Dienstplan führt, Sie anzulegen — sie kann dieses Konto unter „Mitarbeitende“ mit Ihnen verknüpfen.",
    "Open my timesheet": "Meinen Stundenzettel öffnen",
    "Worked so far": "Bisher gearbeitet",
    "Leave days left": "Resturlaub",
    "Days waiting for approval": "Tage, die auf Genehmigung warten",
    "You were rostered on these days and have not said what you worked. If it was exactly as planned, one press confirms them all.":
        "An diesen Tagen waren Sie eingeteilt und haben noch nicht gesagt, was Sie gearbeitet haben. War es genau wie geplant, bestätigt ein Druck alle auf einmal.",
    "Confirm the rostered days?": "Die eingeteilten Tage bestätigen?",
    "Every day you were rostered this week and have not answered for is recorded as worked exactly as planned. Days you have already entered hours on are left exactly as they are.":
        "Jeder Tag dieser Woche, an dem Sie eingeteilt waren und für den Sie noch nichts eingetragen haben, wird als genau wie geplant gearbeitet erfasst. Tage, an denen Sie bereits Stunden eingetragen haben, bleiben unverändert.",
    "Confirm them": "Bestätigen",
    "waiting for you": "wartet auf Sie",
    "For you to deal with": "Für Sie zu erledigen",
    "Open the roster": "Dienstplan öffnen",
    "Decide them": "Entscheiden",
    "Nothing is waiting.": "Es wartet nichts.",
    "Hours nobody has confirmed": "Stunden, die niemand bestätigt hat",
    "See the team’s week": "Die Woche des Teams ansehen",
    "Everything from the last fortnight is confirmed.":
        "Alles aus den letzten zwei Wochen ist bestätigt.",

    # -- the team week -----------------------------------------------------
    "Team timesheets": "Stundenzettel des Teams",
    "Worked, everybody": "Gearbeitet, alle",
    "Contracted, everybody": "Vertraglich, alle",
    "Days nobody has answered for": "Tage, für die niemand geantwortet hat",
    "Rostered, but nobody has said what was worked":
        "Eingeteilt, aber niemand hat gesagt, was gearbeitet wurde",
    "Nobody is employed yet.": "Es ist noch niemand beschäftigt.",
    "entered, not confirmed": "eingetragen, nicht bestätigt",
    "rostered, nothing entered": "eingeteilt, nichts eingetragen",
    "different from the roster": "abweichend vom Dienstplan",

    # -- my timesheet ------------------------------------------------------
    "My timesheet": "Mein Stundenzettel",
    "Entered by hand. The rules would give %(computed)s minutes.":
        "Von Hand eingetragen. Die Regeln ergäben %(computed)s Minuten.",
    "The hours entered are not the hours rostered.":
        "Die eingetragenen Stunden sind nicht die eingeteilten.",

    # -- the monthly timesheet -------------------------------------------
    #
    # "Saldo" rather than "Differenz": it is the word on every German time
    # account anybody in this business has seen, and the column is read against
    # the one their last employer showed them.
    "Back to the timesheet": "Zurück zum Stundenzettel",
    "The month before": "Vorheriger Monat",
    "The month after": "Nächster Monat",
    "Month": "Monat",
    "This month": "Dieser Monat",
    "Status": "Status",
    "Bookings": "Buchungen",
    "Actual": "Ist",
    "Supposed": "Soll",
    "Saldo": "Saldo",
    "Running": "Laufend",
    "Comment": "Bemerkung",
    "Brought forward": "Übertrag",
    "So far": "Bis heute",
    "The whole month": "Ganzer Monat",
    # -- the timesheet saves itself ---------------------------------------
    "Saving": "Speichern",
    "There is no Save button. A comment is written when you leave the box; bookings and a correction are written when you accept the pop-up. Everything the change moves — the running column and the totals — is worked out again by the server and redrawn.":
        "Es gibt keine Schaltfläche „Speichern“. Eine Bemerkung wird geschrieben, sobald Sie das Feld verlassen; Buchungen und eine Korrektur werden geschrieben, sobald Sie das Fenster bestätigen. Alles, was sich dadurch ändert — die laufende Spalte und die Summen — wird vom Server neu berechnet und neu gezeichnet.",
    "A day is a column of comings and goings, in the order they happened. Click the cell to enter them. The cell shows the first four and counts the rest; the pop-up has all of them. A coming with no going yet is a shift still running: it is worth nothing until it has an end, because a figure that changes on every refresh is not one anybody can sign off.":
        "Ein Tag ist eine Spalte aus Kommen und Gehen, in der Reihenfolge, in der sie stattgefunden haben. Zum Eintragen auf die Zelle klicken. Die Zelle zeigt die ersten vier und zählt den Rest; im Fenster stehen alle. Ein Kommen ohne Gehen ist eine noch laufende Schicht: Sie zählt null, solange sie kein Ende hat — eine Zahl, die sich bei jedem Neuladen ändert, kann niemand abzeichnen.",
    "The month": "Der Monat",

    "add": "eintragen",
    "Bookings for %(date)s": "Buchungen für %(date)s",
    "Comment for %(date)s": "Bemerkung zu %(date)s",
    "Correction for %(date)s": "Korrektur für %(date)s",
    "Take the rostered times": "Geplante Zeiten übernehmen",
    "Take the rostered times for %(date)s": "Geplante Zeiten für %(date)s übernehmen",
    "Another booking": "Weitere Buchung",

    "Clear the day": "Tag leeren",

    "Remove the correction": "Korrektur entfernen",
    "Includes %(amount)s brought from a previous contract, as at %(date)s.":
        "Enthält %(amount)s aus einem früheren Vertrag, Stand %(date)s.",
    "A holiday, a day of leave or a sick day is credited at the contracted hours, so the month comes out level and the reason is named on the row. Time off in lieu is the exception and is credited nothing — that shortfall is the overtime being taken back.":
        "Ein Feiertag, ein Urlaubstag oder ein Krankheitstag wird mit den vertraglichen Stunden gutgeschrieben; der Monat geht damit auf und der Grund steht in der Zeile. Der Freizeitausgleich ist die Ausnahme und wird nicht gutgeschrieben — genau dieses Minus ist die Überstunde, die zurückgenommen wird.",

    # The letters in this sentence are the keyboard shortcut, and they come from
    # the first letter of „Kommen“ und „Gehen“ — see the JAVASCRIPT table below.
    # An English "C and G" here would name keys that do nothing in German.
    "One line per booking. Type the time, then say whether it is a coming or a going — the keyboard does it too: press C for coming or G for going and the line is entered.":
        "Eine Zeile je Buchung. Zeit eintippen und dann angeben, ob es ein Kommen oder ein Gehen ist — über die Tastatur geht das auch: K für Kommen oder G für Gehen, und die Zeile ist eingetragen.",
    "Time that belongs on this day and was never read off a clock — a forgotten going, a drive to a second site, an afternoon that was paid. Minutes, or 0:30. A minus takes time off.":
        "Zeit, die zu diesem Tag gehört und nie von einer Uhr abgelesen wurde — ein vergessenes Gehen, eine Fahrt zu einem zweiten Einsatzort, ein bezahlter Nachmittag. Minuten oder 0:30. Ein Minus zieht Zeit ab.",
    "Time that belongs on this day and was never read off a clock — a forgotten going, a drive to a second site, an afternoon that was paid. It is added after the break, so it can never push the day over a break threshold and deduct a break nobody took. A minus takes time off.":
        "Zeit, die zu diesem Tag gehört und nie von einer Uhr abgelesen wurde — ein vergessenes Gehen, eine Fahrt zu einem zweiten Einsatzort, ein bezahlter Nachmittag. Sie wird nach der Pause aufgeschlagen und kann den Tag deshalb nie über eine Pausenschwelle heben und eine Pause abziehen, die niemand genommen hat. Ein Minus zieht Zeit ab.",

    "Reading the timesheet": "Den Stundenzettel lesen",

    "Worked out from the break rules and deducted from the bookings. A break somebody typed by hand is drawn in amber, because a break of 30 the rules produced and a break of 30 somebody entered are the same number and mean different things.":
        "Wird aus den Pausenregeln berechnet und von den Buchungen abgezogen. Eine von Hand eingetragene Pause steht in Bernstein, denn eine Pause von 30 Minuten aus der Regel und eine von Hand eingetragene Pause von 30 Minuten sind dieselbe Zahl und bedeuten Verschiedenes.",
    "Time that belongs on the day and was never read off a clock. It always needs a reason, and it is added after the break — so a correction can never push a day over a break threshold and deduct a break nobody took.":
        "Zeit, die zum Tag gehört und nie von einer Uhr abgelesen wurde. Sie braucht immer eine Begründung und wird nach der Pause aufgeschlagen — eine Korrektur kann einen Tag also nie über eine Pausenschwelle heben und eine Pause abziehen, die niemand genommen hat.",
    "Actual less supposed. Green is time over the contract, red is time under it. The running column carries on from the balance brought into the month, so the last row of the month is the balance to date.":
        "Ist minus Soll. Grün ist Zeit über dem Vertrag, Rot ist Zeit darunter. Die laufende Spalte setzt den Übertrag in den Monat fort, die letzte Zeile des Monats ist also der Saldo bis heute.",

    # -- the status pop-up -------------------------------------------------
    "Status for %(date)s": "Status für %(date)s",
    # What a clipped pill says on hover. The status column is nine and a half
    # rems and a day can carry three pills, so every one of them names itself.
    "Reported, and not yet acknowledged by a manager. It counts either way.":
        "Gemeldet und von der Leitung noch nicht zur Kenntnis genommen. Es zählt so oder so.",
    "Waiting for a decision. The days are not taken off a balance until it is approved.":
        "Wartet auf eine Entscheidung. Die Tage werden erst bei Genehmigung vom Konto abgezogen.",
    # The word in an empty status cell. Lower case and quiet: it is an
    # invitation, not a heading, and it sits in a column of pills.
    #
    # **Not "eintragen".** That is what the bookings cell beside it says, and two
    # adjacent columns offering the same word is two columns nobody can tell
    # apart at a glance — which on a grid read down a column is the whole
    # problem.
    "set": "festlegen",
    "Which": "Welcher",
    "Half a day": "Ein halber Tag",
    "Nothing — an ordinary working day": "Nichts — ein normaler Arbeitstag",
    "What was true of this day. Time off is asked for and waits for a decision; sickness is stated and counts from the moment it is entered — your manager acknowledges it rather than allows it.":
        "Was an diesem Tag war. Abwesenheit wird beantragt und wartet auf eine Entscheidung; Krankheit wird gemeldet und zählt ab dem Eintragen — Ihre Leitung nimmt sie zur Kenntnis, sie genehmigt sie nicht.",
    "This day is part of something that was booked elsewhere — a workplace closure, or an absence covering several days. Change it on the Time off page.":
        "Dieser Tag gehört zu etwas, das an anderer Stelle eingetragen wurde — einer Betriebsschließung oder einer Abwesenheit über mehrere Tage. Bitte auf der Seite „Abwesenheit“ ändern.",

    # -- the break table's worked examples ---------------------------------
    "Deducted": "Abgezogen",
    "The day": "Der Tag",
    "Three things this table is here to show. A day only a little over a tier gets only as much break as it takes to bring it back under, not the whole tier — reading the rules the other way costs somebody break they were entitled to. A break somebody already took counts: clocking out for half an hour and back in is half an hour off the day already. But it only counts if it broke the work up — the last row is six and a half hours worked straight through with the hour off afterwards, which is still six and a half hours without a break, and a pause under fifteen minutes is not a break at all.":
        "Drei Dinge zeigt diese Tabelle. Ein Tag, der nur knapp über einer Stufe liegt, bekommt nur so viel Pause, wie ihn wieder darunter bringt, nicht die ganze Stufe — die Regeln andersherum zu lesen kostet jemanden Pause, die ihm zusteht. Eine bereits genommene Pause zählt: wer sich für eine halbe Stunde ausbucht und wieder einbucht, hat diese halbe Stunde schon nicht gearbeitet. Sie zählt aber nur, wenn sie die Arbeit unterbrochen hat — die letzte Zeile sind sechseinhalb Stunden am Stück und die Stunde frei danach, das bleiben sechseinhalb Stunden ohne Pause. Und eine Unterbrechung unter fünfzehn Minuten ist gar keine Pause.",

    # -- closing a month ---------------------------------------------------
    #
    # "Sperren" and never "abschließen": ein Monatsabschluss ist das, was eine
    # Buchhaltung mit dem Hauptbuch macht, und das hier ist enger — es schließt
    # den *Stundenzettel* für Änderungen und sagt nichts über die Lohnabrechnung.
    "Month end": "Monatsende",
    "Closing a month": "Monat abschließen",
    "Lock the month": "Monat sperren",
    "Unlock the month": "Monat entsperren",
    "Lock the month?": "Monat sperren?",
    "Unlock the month?": "Monat entsperren?",
    "Lock or unlock the month?": "Monat sperren oder entsperren?",
    "Go ahead": "Weiter",
    "Everything in this month becomes changeable again.":
        "Alles in diesem Monat kann wieder geändert werden.",
    "Nothing in this month can be changed afterwards — not the bookings, not a status, not a correction, not a comment. A single day can be unlocked again from its own row.":
        "Danach kann nichts mehr in diesem Monat geändert werden — weder Buchungen noch ein Status noch eine Korrektur noch eine Bemerkung. Ein einzelner Tag kann über seine eigene Zeile wieder entsperrt werden.",
    "Locking closes that month for everybody you have ticked: nothing in it can be changed afterwards. A single day can be unlocked again on their own timesheet.":
        "Das Sperren schließt den Monat für alle Angehakten: danach kann nichts mehr darin geändert werden. Ein einzelner Tag kann auf dem jeweiligen Stundenzettel wieder entsperrt werden.",
    "Locking a month closes it: nothing in it can be changed afterwards — not the bookings, not a status, not a correction, not a comment. A single day can be unlocked again on that person's timesheet when something has to be put right.":
        "Das Sperren schließt den Monat: danach kann nichts mehr darin geändert werden — weder Buchungen noch ein Status noch eine Korrektur noch eine Bemerkung. Muss etwas berichtigt werden, kann ein einzelner Tag auf dem Stundenzettel der Person wieder entsperrt werden.",
    "Open the requests": "Zu den Anträgen",
    "Everybody": "Alle",
    "Still open": "Noch offen",
    "Locked": "Gesperrt",
    "locked": "gesperrt",
    "open": "offen",
    "%(locked)s of %(total)s days": "%(locked)s von %(total)s Tagen",
    "Nobody is employed at the moment.": "Zurzeit ist niemand beschäftigt.",

    # -- a locked day, on the timesheet ------------------------------------
    "Unlock this day so it can be changed": "Diesen Tag entsperren, um ihn zu ändern",
    "Lock this day again": "Diesen Tag wieder sperren",
    "Unlock %(date)s": "%(date)s entsperren",
    "Lock %(date)s": "%(date)s sperren",
    "This day is locked. Ask a manager to unlock it.":
        "Dieser Tag ist gesperrt. Bitten Sie Ihre Leitung, ihn zu entsperren.",
    "Locked days": "Gesperrte Tage",
    "A manager closes a month when its hours are agreed. Nothing in a locked day can be changed after that — not the bookings, not the status, not the correction, not the comment. If something has to be put right, a manager unlocks that one day with the padlock on its row, and locks it again afterwards.":
        "Ihre Leitung schließt einen Monat ab, wenn die Stunden darin vereinbart sind. Danach kann an einem gesperrten Tag nichts mehr geändert werden — weder die Buchungen noch der Status noch die Korrektur noch die Bemerkung. Muss etwas berichtigt werden, entsperrt die Leitung genau diesen einen Tag über das Schloss in seiner Zeile und sperrt ihn danach wieder.",
}

# Plural entries: msgid -> (singular msgstr, plural msgstr). German has the same
# two-form plural rule as English (n != 1), so the mapping is one to one — which
# is not true of every language and is the reason gettext asks rather than
# assuming.
PLURALS = {
    "%(counter)s working day": ("%(counter)s Arbeitstag", "%(counter)s Arbeitstage"),
    "Too many failed attempts. Please wait a minute and try again.": (
        "Zu viele Fehlversuche. Bitte warten Sie eine Minute und versuchen Sie es erneut.",
        "Zu viele Fehlversuche. Bitte warten Sie %(minutes)s Minuten und versuchen Sie es erneut.",
    ),
    "%(n)s account can sign in": (
        "%(n)s Konto kann sich anmelden", "%(n)s Konten können sich anmelden",
    ),
    "%(n)s of these signs in through SSO. Their name and e-mail come from the identity provider and are refreshed at every sign-in.": (
        "%(n)s davon meldet sich über SSO an. Name und E-Mail kommen vom Identitätsanbieter und werden bei jeder Anmeldung erneuert.",
        "%(n)s davon melden sich über SSO an. Namen und E-Mail-Adressen kommen vom Identitätsanbieter und werden bei jeder Anmeldung erneuert.",
    ),
    "%(counter)s employee has no account yet. That is normal — the link is made by itself the first time they sign in, matched on their sign-in name.": (
        "%(counter)s Person hat noch kein Konto. Das ist normal — die Verknüpfung entsteht bei der ersten Anmeldung von selbst, anhand ihres Anmeldenamens.",
        "%(counter)s Personen haben noch kein Konto. Das ist normal — die Verknüpfung entsteht bei der ersten Anmeldung von selbst, anhand ihres Anmeldenamens.",
    ),
    "%(counter)s day is waiting for you": (
        "%(counter)s Tag wartet auf Sie", "%(counter)s Tage warten auf Sie",
    ),
    "%(counter)s day": ("%(counter)s Tag", "%(counter)s Tage"),
    "%(counter)s more booking — open the day to see it": (
        "%(counter)s weitere Buchung — Tag öffnen, um sie zu sehen",
        "%(counter)s weitere Buchungen — Tag öffnen, um sie zu sehen",
    ),

    # The month's save. Two messages rather than one carrying both counts —
    # German inflects on the number and a single string cannot be right for
    # both, which is how a save of one day announced itself as "1 Tage".

    "%(count)s day was locked.": (
        "%(count)s Tag wurde gesperrt.", "%(count)s Tage wurden gesperrt.",
    ),
    "%(count)s day was unlocked.": (
        "%(count)s Tag wurde entsperrt.", "%(count)s Tage wurden entsperrt.",
    ),
    "%(counter)s day unanswered": (
        "%(counter)s Tag offen", "%(counter)s Tage offen",
    ),
    "%(counter)s waiting for a decision": (
        "%(counter)s wartet auf Entscheidung", "%(counter)s warten auf Entscheidung",
    ),
    "%(counter)s absence in this month is still waiting for a decision. A month cannot be locked over it — decide it first.": (
        "%(counter)s Abwesenheit in diesem Monat wartet noch auf eine Entscheidung. Darüber lässt sich kein Monat sperren — bitte zuerst entscheiden.",
        "%(counter)s Abwesenheiten in diesem Monat warten noch auf eine Entscheidung. Darüber lässt sich kein Monat sperren — bitte zuerst entscheiden.",
    ),
}

# Added when the sign-in name replaced the e-mail address, when the time parser
# arrived, and when time off in lieu became a thing somebody can ask for.
LATER = {
    "You are not due to work on any of those days, so there is nothing to book off. Public holidays and days your contract gives no hours are not counted.":
        "An keinem dieser Tage sind Sie zur Arbeit eingeteilt, es gibt also nichts freizunehmen. Feiertage und Tage, für die Ihr Vertrag keine Stunden vorsieht, werden nicht gezählt.",
    "Time off in lieu": "Überstundenausgleich",

    # -- the sign-in name --------------------------------------------------
    "directory name": "Verzeichnisname",
    "sign-in name": "Anmeldename",
    "The name from the directory — usually firstname.surname. This is what recognises them the first time they sign in.":
        "Der Name aus dem Verzeichnis — üblicherweise vorname.nachname. Daran wird die Person bei der ersten Anmeldung erkannt.",
    "Usually left alone: the link is made by itself the first time they sign in, matched on the sign-in name above. Set it by hand only when somebody signed in before they were added here, or when the directory calls them something other than what is on this contract.":
        "Meist unangetastet zu lassen: die Verknüpfung entsteht bei der ersten Anmeldung von selbst, anhand des Anmeldenamens oben. Nur von Hand setzen, wenn sich jemand angemeldet hat, bevor er hier angelegt wurde, oder wenn das Verzeichnis ihn anders nennt als dieser Vertrag.",
    "Ask whoever manages the roster to add you on the Employees page. If they have already added you, the link is usually made by itself the first time you sign in — it is matched on your sign-in name, so it only fails when the directory calls you something other than what is on your record. They can also link this account to you by hand.":
        "Bitten Sie die Person, die den Dienstplan führt, Sie unter „Mitarbeitende“ anzulegen. Sind Sie bereits angelegt, entsteht die Verknüpfung bei der ersten Anmeldung meist von selbst — sie erfolgt über Ihren Anmeldenamen und schlägt nur fehl, wenn das Verzeichnis Sie anders nennt als Ihr Datensatz. Die Verknüpfung lässt sich auch von Hand setzen.",

    # -- reading a time ----------------------------------------------------
    "That is longer than %(cap)s.": "Das ist länger als %(cap)s.",
    "A day only has 24 hours.": "Ein Tag hat nur 24 Stunden.",
    "A break cannot be longer than a day.": "Eine Pause kann nicht länger als ein Tag sein.",
    "“%(value)s” is not a time this app can read. Try 8:30, 8,5 or 830.":
        "„%(value)s“ ist keine Zeitangabe, die diese App lesen kann. Versuchen Sie 8:30, 8,5 oder 830.",

    # -- overlapping stretches ---------------------------------------------
    "Two of those stretches overlap — %(first)s and %(second)s. The overlapping time would be counted twice.":
        "Zwei dieser Abschnitte überschneiden sich — %(first)s und %(second)s. Die überlappende Zeit würde doppelt gezählt.",
    "Two of those stretches overlap. The overlapping time would be counted twice, so this cannot be saved until one of them is corrected.":
        "Zwei dieser Abschnitte überschneiden sich. Die überlappende Zeit würde doppelt gezählt; es lässt sich erst speichern, wenn einer davon korrigiert ist.",
}

PAGES.update(LATER)

# The djangojs catalogue — the strings the browser says for itself.
JAVASCRIPT = {
    "That is not a time this app can read. Try 8:30, 8,5 or 830.":
        "Das ist keine Zeitangabe, die diese App lesen kann. Versuchen Sie 8:30, 8,5 oder 830.",
    "This overlaps another stretch on the same day.":
        "Das überschneidet sich mit einem anderen Abschnitt am selben Tag.",
    "OK": "OK",
    "Continue": "Weiter",
    "Dismiss": "Schließen",
    "Copied": "Kopiert",
    "Press Ctrl-C": "Strg-C drücken",

    # -- the bookings pop-up ---------------------------------------------
    #
    # **These two carry the keyboard shortcut.** timesheet_month.js takes the
    # key from the first letter of each label rather than hard-coding C and G,
    # so „Kommen“ binds K and „Gehen“ binds G. Renaming either word here moves
    # the shortcut with it, which is the only way the two can stay in step.
    "Coming": "Kommen",
    "Going": "Gehen",
    "Time": "Zeit",
    "add": "eintragen",
    "Remove this booking": "Diese Buchung entfernen",

    # The month writes as it goes, so these are the sentences that replace a
    # page reload: what was saved, and what stopped it being saved.
    "Saved.": "Gespeichert.",
    "That could not be saved.": "Das konnte nicht gespeichert werden.",
    "The change did not reach the server, so nothing was saved.":
        "Die Änderung hat den Server nicht erreicht, es wurde also nichts gespeichert.",
    # Redrawn into the row after a save, so they have to exist in both
    # catalogues — the same words the template renders on first load.
    "still running": "läuft noch",
    "differs": "weicht ab",
    "The hours entered are not the hours rostered.":
        "Die eingetragenen Zeiten sind nicht die geplanten Zeiten.",
    "Credited, not worked — an absence the hours are paid for.":
        "Gutgeschrieben, nicht gearbeitet — eine Abwesenheit, die bezahlt wird.",
    "Every booking has to say whether it is a coming or a going.":
        "Bei jeder Buchung muss angegeben sein, ob sie ein Kommen oder ein Gehen ist.",
    "There is a booking with no time on it.": "Es gibt eine Buchung ohne Uhrzeit.",
    "There are two comings in a row with no going between them.":
        "Es stehen zwei Kommen hintereinander, ohne ein Gehen dazwischen.",
    "There is a going with no coming before it. A day starts with a coming.":
        "Es gibt ein Gehen, vor dem kein Kommen steht. Ein Tag beginnt mit einem Kommen.",
    "A coming and a going at the same moment is a stretch with no length.":
        "Ein Kommen und ein Gehen zum selben Zeitpunkt ist ein Abschnitt ohne Länge.",
    "That is not a length this app can read. Try 30, 0:30 or -15.":
        "Das ist keine Dauer, die diese App lesen kann. Zum Beispiel 30, 0:30 oder -15.",
    "Say why the day was corrected. A correction nobody can account for is the one entry on a timesheet that cannot be defended.":
        "Bitte angeben, warum der Tag korrigiert wurde. Eine Korrektur, die niemand begründen kann, ist der eine Eintrag auf einem Stundenzettel, der sich nicht verteidigen lässt.",
}
