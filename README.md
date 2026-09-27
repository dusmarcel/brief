# Briefaktion der Rechtsberater*innenkonferenz

Diese Webapp unterstützt eine Brief- und E-Mail-Aktion an Bundestagsabgeordnete zum Erhalt der unabhängigen Asylverfahrensberatung. Sie sucht Abgeordnete nach Ort, Landkreis, Bundesland oder Postleitzahl, erlaubt die Auswahl passender Empfänger*innen und erzeugt anschließend Schreiben als ZIP-Datei oder fertig ausgefüllte E-Mails, die die Anwender*innen aus ihrem eigenen Postfach versenden.

## Schnellstart

```bash
cd brief
python app.py
```

Danach im Browser öffnen:

- `http://127.0.0.1:8000`

## Docker

### Entwicklung

```bash
docker compose up --build
```

Im Dev-Container läuft `watchmedo` mit Polling, damit Änderungen an `*.py`, `*.html`, `*.js`, `*.css` und `*.json` auf gemounteten Host-Dateien auch unter Docker Desktop zuverlässig erkannt werden. Danach sollte ein Neuladen im Browser genügen.

### Produktion

Für den produktiven Betrieb gibt es eine separate Compose-Datei ohne Bind-Mounts und ohne Hot-Reload:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

Die Produktionskonfiguration:

- baut den `prod`-Target aus dem `Dockerfile`
- startet die App ohne `watchmedo`
- läuft als nicht-root Benutzer `appuser`
- setzt `restart: unless-stopped`
- veröffentlicht standardmäßig Port `8000`

Einen anderen Host-Port kannst du beim Start über `PORT` setzen:

```bash
PORT=8080 docker compose -f docker-compose.prod.yml up --build -d
```

Zum Stoppen:

```bash
docker compose -f docker-compose.prod.yml down
```

## Funktion

Die Anwendung führt durch drei Schritte:

1. Abgeordnete suchen und auswählen
   - Suche nach Ort, Landkreis, Bundesland oder PLZ
   - Anzeige von Name, Fraktion, Postanschrift, E-Mail, Profil und Kontaktformular
   - Alle nicht zur AfD gehörenden Abgeordneten werden standardmäßig vorausgewählt
2. Absenderangaben ergänzen
   - Name und Anschrift sind Pflichtfelder
   - E-Mail-Adresse und Geschlecht sind optional; das Geschlecht bestimmt „Als Rechtsanwalt/Rechtsanwältin/Rechtsanwält*in“ im Text und den vorgeschlagenen Zusatz zum Namen
   - Vorschau des Schreibens mit Anschrift, Betreff und Anrede; per Klick auf eine ausgewählte Person wechselt die Vorschau zu deren Schreiben
   - Die Anrede lässt sich für jede Person einzeln anpassen (siehe [Anrede und Anschrift](#anrede-und-anschrift))
3. Versandart wählen
   - ZIP-Archiv mit personalisierten Schreiben (RTF) herunterladen, zum Ausdrucken und postalischen Versand
   - E-Mails schreiben (siehe [E-Mail-Versand](#e-mail-versand))

## Anrede und Anschrift

Anrede, Anschrift und der erste Satz richten sich nach dem Geschlecht der Abgeordneten (`data/genders.json`):

| Geschlecht | Anschrift | Anrede | Erster Satz |
| --- | --- | --- | --- |
| männlich | Herrn Dr. Max Muster | Sehr geehrter Herr Dr. Muster, | als Abgeordneter meines Wahlkreises … |
| weiblich | Frau Dr. Erika Muster | Sehr geehrte Frau Dr. Muster, | als Abgeordnete meines Wahlkreises … |
| divers / unbekannt | Dr. Kim Muster | Guten Tag, Dr. Kim Muster, | als Abgeordnete*r meines Wahlkreises … |

Dabei gelten die in Briefen üblichen Regeln:

- In der Anschrift stehen alle akademischen Grade wie im Namen angegeben (z. B. „Prof. Dr.-Ing. habil.“, „Dr. med.“).
- In der Anrede wird nur der höchste Grad genannt: „Dr.“ ohne Fachzusatz, bei Professor*innen „Herr Professor …“ bzw. „Frau Professorin …“ (ausgeschrieben, ohne „Dr.“).
- Namenszusätze wie „von“, „van“, „de“ oder „dos“ gehören zum Nachnamen („Sehr geehrte Frau von Storch,“).
- Adelstitel ersetzen ohne akademischen Grad „Herr“/„Frau“ („Sehr geehrter Freiherr von Stetten,“); mit akademischem Grad heißt es „Sehr geehrter Herr Dr. von …“.

Die Geschlechtsangaben stammen aus den Stammdaten des Bundestags und werden mit `python scripts/collect_genders.py` erzeugt. Für Personen, die dort nicht (eindeutig) zu finden sind, sind die Einträge von Hand ergänzt und mit `"manual": true` gekennzeichnet; sie bleiben beim erneuten Erzeugen erhalten.

In Schritt 2 lässt sich die Anrede für jede ausgewählte Person individuell ändern. Die geänderte Anrede gilt für Vorschau, E-Mails und ZIP-Download; „Zurücksetzen“ stellt den Vorschlag wieder her.

## E-Mail-Versand

Die E-Mails werden nicht vom Server verschickt, sondern von den Anwender*innen aus ihrem eigenen Postfach. So kommen sie als persönliche Schreiben bei den Abgeordneten an, landen im eigenen Gesendet-Ordner, und Antworten gehen direkt an die absendende Person.

In Schritt 3 wählen die Anwender*innen einmal oben ihren E-Mail-Anbieter; jede Person in der Liste erhält dann eine passende Schaltfläche sowie „Adresse / Betreff / Text kopieren“. Die Auswahl wird im Browser gespeichert.

| Auswahl | Schaltfläche |
| --- | --- |
| Mailprogramm auf diesem Gerät | `mailto:`-Link, öffnet eine fertig ausgefüllte E-Mail |
| Gmail, Outlook.com, Outlook (Microsoft 365) | öffnet eine fertig ausgefüllte E-Mail im Webmailer (Anmeldung vorausgesetzt) |
| GMX, WEB.DE, t-online | öffnet nur den Webmailer; Adresse, Betreff und Text werden über die Kopier-Schaltflächen eingefügt |
| Anderer Anbieter | nur Kopier-Schaltflächen |

Für das Mailprogramm sowie Gmail und Outlook gibt es zusätzlich eine Schaltfläche, die die E-Mails an alle ausgewählten Personen auf einmal öffnet:

- **Mailprogramm:** Die E-Mails werden im Abstand von einer halben Sekunde nacheinander geöffnet. Je nach Browser muss jede einzeln bestätigt werden.
- **Gmail / Outlook:** Jede E-Mail öffnet sich in einem eigenen Tab. Browser lassen pro Klick meist nur einen neuen Tab zu und blockieren die übrigen als Pop-ups. Die Seite erkennt das und bietet dann „Restliche … E-Mails öffnen“ an; nachdem Pop-ups für die Seite erlaubt wurden, öffnet ein weiterer Klick den Rest.

GMX, WEB.DE und t-online bieten keinen öffentlich dokumentierten Link, der ein vorausgefülltes Mailfenster öffnet. Wer dort ein Postfach hat und die Mail trotzdem vorausgefüllt haben möchte, kann den Webmailer im Browser als Standard für E-Mail-Links einrichten (sofern der Anbieter das unterstützt) und „Mailprogramm auf diesem Gerät“ wählen. Weitere Anbieter lassen sich in `MAIL_PROVIDERS` in `static/app.js` ergänzen.

Einige Mailprogramme (insbesondere Outlook unter Windows) kürzen sehr lange `mailto:`-Links; dann hilft „Text kopieren“. Für Personen ohne E-Mail-Adresse wird, soweit vorhanden, auf das Kontaktformular verwiesen.

**Testbetrieb:** Während der Entwicklung sind alle E-Mails an eine Testadresse adressiert statt an die Abgeordneten. Die eigentliche Adresse steht im Betreff (`[Test, eigentlich an …]`), und Schritt 3 zeigt einen Hinweis. Die Testadresse ist die Konstante `MAIL_TEST_RECIPIENT` in `static/app.js`; ist sie leer (`""`), gehen die E-Mails an die Abgeordneten.

## E-Mail-Adressen

Für alle Abgeordneten ist nach Möglichkeit eine E-Mail-Adresse hinterlegt, damit Schreiben direkt per E-Mail statt über Kontaktformulare verschickt werden können. Die Adressen stehen in `data/emails.json` und haben Vorrang vor den zur Laufzeit von bundestag.de abgerufenen Daten.

- Die meisten Adressen stammen von den Abgeordnetenseiten der Fraktionen (CDU/CSU, SPD, Grüne, Linke, AfD) und werden mit `python scripts/collect_emails.py` aktualisiert.
- Einzelne Adressen wurden manuell recherchiert (persönliche Websites, Suchergebnisse). Sie sind mit `"manual": true` und Quelle gekennzeichnet und bleiben beim erneuten Sammeln erhalten. Wo eine Adresse nicht öffentlich bestätigt ist, sondern aus dem Standardschema `vorname.nachname@bundestag.de` abgeleitet wurde, steht ein Hinweis im Feld `note`.
- Nur wenn keine Adresse bekannt ist, wird auf das Kontaktformular verwiesen.

Bei Kontaktangaben werden zuerst die auf der Profilseite veröffentlichten Daten des Wahlkreisbüros verwendet. Kontaktdaten des Abgeordnetenbüros im Bundestag dienen als Rückfalloption.

## Datenquelle

- `data/wks.json` (Wahlkreise, PLZ-Zuordnung, Basis-Informationen zu Abgeordneten)
- Zusätzliche Profilinformationen werden zur Laufzeit direkt von den Bundestag-Profilseiten geholt.
- `data/emails.json` (E-Mail-Adressen, siehe oben) und `data/genders.json` (Geschlecht für Anrede und Anschrift, siehe oben)
- `data/stammdaten/MDB_STAMMDATEN.XML` und `data/MdB-Stammdaten.zip` (amtlicher Open-Data-Export des Bundestags; Stand 29.04.2026)

Quelle: [Open Data des Deutschen Bundestags](https://www.bundestag.de/services/opendata).

Die Mitgliederliste entspricht dem Stand vom 27.09.2026 (abgeglichen mit den Stammdaten, der Wikipedia-Liste der 21. Wahlperiode und den Fraktionsseiten; berücksichtigt sind u. a. die Nachrücker Stefan Glaser, Christoph Naser, Michael Breilmann und Katrin Zschau). Abgeordnete werden dem Wahlkreis zugeordnet, in dem sie kandidiert haben. Mitglieder ohne Wahlkreiskandidatur erscheinen bei der Suche nach ihrem Bundesland.
