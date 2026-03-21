# Bundestag nach PLZ

Diese Webapp sucht nach einer Postleitzahl und zeigt die Bundestagsabgeordneten an, deren Wahlkreis diese PLZ enthält.

## Schnellstart

```bash
cd C:\Users\marce\projects\brief
python app.py
```

Danach im Browser öffnen:

- `http://127.0.0.1:8000`

## Entwicklung mit Docker

```bash
docker compose up --build
```

Im Dev-Container läuft `watchmedo` mit Polling, damit Änderungen an `*.py`, `*.html`, `*.js`, `*.css` und `*.json` auf gemounteten Host-Dateien auch unter Docker Desktop zuverlässig erkannt werden. Danach sollte ein Neuladen im Browser genügen.

## Funktion

- Eingabe: PLZ (z. B. `10435`)
- Ergebnis:
  - Name
  - Fraktionszugehörigkeit
  - Postanschrift
  - E-Mail (sofern öffentlich vorhanden)
  - Link zum offiziellen Profil
  - Kontaktformular

## Hinweis zur E-Mail

Die Datenquelle liefert teilweise keine öffentlichen E-Mail-Adressen. Wenn keine E-Mail verfügbar ist, wird angezeigt:

- `Nicht öffentlich veröffentlicht`

## Datenquelle

- `data/wks.json` (Wahlkreise, PLZ-Zuordnung, Basis-Informationen zu Abgeordneten)
- Zusätzliche Profilinformationen werden zur Laufzeit direkt von den Bundestag-Profilseiten geholt.
