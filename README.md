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

Die Datenquelle liefert nicht immer öffentliche E-Mail-Adressen. Wenn keine Adresse auf Profil- oder Kontaktseiten gefunden wird, versucht die Anwendung, eine plausible Adresse zu ergänzen. Für bekannte Ausnahmen können feste Korrekturen im Backend hinterlegt werden.

## Datenquelle

- `data/wks.json` (Wahlkreise, PLZ-Zuordnung, Basis-Informationen zu Abgeordneten)
- Zusätzliche Profilinformationen werden zur Laufzeit direkt von den Bundestag-Profilseiten geholt.
