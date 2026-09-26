# Briefaktion der Rechtsberater*innenkonferenz

Diese Webapp unterstützt eine Brief- und E-Mail-Aktion an Bundestagsabgeordnete zum Erhalt der unabhängigen Asylverfahrensberatung. Sie sucht Abgeordnete nach Ort, Landkreis, Bundesland oder Postleitzahl, erlaubt die Auswahl passender Empfänger*innen und erzeugt anschließend Schreiben als ZIP-Datei oder einzelne E-Mail-Entwürfe.

## Schnellstart

```bash
cd C:\Users\marce\projects\brief
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
   - E-Mail-Adresse ist optional
   - Vorschau des Schreibens mit Anschrift, Betreff und Anrede
3. Versandart wählen
   - ZIP-Archiv mit personalisierten Schreiben herunterladen
   - Für jede ausgewählte Person einen eigenen E-Mail-Entwurf erzeugen
   - Optional alle verfügbaren E-Mail-Entwürfe gesammelt nacheinander vorbereiten

## E-Mail-Adressen

Für alle Abgeordneten ist nach Möglichkeit eine E-Mail-Adresse hinterlegt, damit Schreiben direkt per E-Mail statt über Kontaktformulare verschickt werden können. Die Adressen stehen in `data/emails.json` und haben Vorrang vor den zur Laufzeit von bundestag.de abgerufenen Daten.

- Die meisten Adressen stammen von den Abgeordnetenseiten der Fraktionen (CDU/CSU, SPD, Grüne, Linke, AfD) und werden mit `python scripts/collect_emails.py` aktualisiert.
- Einzelne Adressen wurden manuell recherchiert (persönliche Websites, Suchergebnisse). Sie sind mit `"manual": true` und Quelle gekennzeichnet und bleiben beim erneuten Sammeln erhalten. Wo eine Adresse nicht öffentlich bestätigt ist, sondern aus dem Standardschema `vorname.nachname@bundestag.de` abgeleitet wurde, steht ein Hinweis im Feld `note`.
- Nur wenn keine Adresse bekannt ist, wird auf das Kontaktformular verwiesen.

Bei Kontaktangaben werden zuerst die auf der Profilseite veröffentlichten Daten des Wahlkreisbüros verwendet. Kontaktdaten des Abgeordnetenbüros im Bundestag dienen als Rückfalloption.

## Datenquelle

- `data/wks.json` (Wahlkreise, PLZ-Zuordnung, Basis-Informationen zu Abgeordneten)
- Zusätzliche Profilinformationen werden zur Laufzeit direkt von den Bundestag-Profilseiten geholt.
- `data/stammdaten/MDB_STAMMDATEN.XML` und `data/MdB-Stammdaten.zip` (amtlicher Open-Data-Export des Bundestags; Stand 29.04.2026)

Quelle: [Open Data des Deutschen Bundestags](https://www.bundestag.de/services/opendata).

Die Mitgliederliste entspricht dem Stand vom 27.09.2026 (abgeglichen mit den Stammdaten, der Wikipedia-Liste der 21. Wahlperiode und den Fraktionsseiten; berücksichtigt sind u. a. die Nachrücker Stefan Glaser, Christoph Naser, Michael Breilmann und Katrin Zschau). Abgeordnete werden dem Wahlkreis zugeordnet, in dem sie kandidiert haben. Mitglieder ohne Wahlkreiskandidatur erscheinen bei der Suche nach ihrem Bundesland.
