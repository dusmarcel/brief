# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

"Brief" is a single-page web app for a letter/e-mail campaign to German Bundestag representatives (MdBs). Users look up MdBs by place, county, state or postal code (PLZ), select recipients, fill in their sender details, and then download personalized RTF letters (ZIP) or open prefilled e-mails to send from their own mailbox. It combines static election district data with live scraping of bundestag.de member profiles for contact info. The UI and all letter text are German.

## Running the Application

```bash
python app.py
```

Serves on `http://127.0.0.1:8000`. Override with `PORT` and `HOST` environment variables.

No build step, no dependencies — pure Python standard library.

## Docker (Development with Hot Reload)

```bash
docker compose up
```

Uses the `dev` stage of the `Dockerfile`, which installs `watchdog` and runs `watchmedo auto-restart`. File changes to `*.py`, `*.html`, `*.js`, `*.css`, and `*.json` trigger an automatic server restart. The project directory is mounted as a volume, so edits on the host are reflected immediately.

The production image uses the `prod` stage (non-root user, no hot reload), also available via `docker compose -f docker-compose.prod.yml up --build -d`:

```bash
docker build --target prod -t brief .
docker run -p 8000:8000 brief
```

## Architecture

**Backend** (`app.py`): Python `ThreadingHTTPServer` with these routes:
- `GET /` and other paths → static files from `static/`
- `GET /api/suggest?q=…` → autocomplete suggestions (places, counties, states, PLZ)
- `GET /api/search?q=…|target=…|zip=…` → the resolved search target plus matching representatives (or suggestions if ambiguous)
- `POST /api/letters` → ZIP of RTF letters for `{memberIds, sender, salutations}`

**Frontend** (`static/`): Vanilla JS/HTML/CSS — no frameworks, no bundler. Three steps: search/select recipients → sender details, per-recipient salutation and letter preview → ZIP download or e-mail links. The letter text exists twice, as `LETTER_BODY` in `app.py` (RTF letters) and in `static/app.js` (preview and e-mails); keep both in sync.

**Salutation and address**: each search result carries `gender`, `academicTitle`, `addressName` ("Herrn Prof. Dr. …") and a default `salutation` computed in `_default_salutation()` (highest degree only, "Professor/Professorin" spelled out, noble rank replaces "Herr/Frau", non-binary/unknown → "Guten Tag, Vorname Nachname,"). The first sentence's "als Abgeordnete*r" is gendered by the recipient, "Als Rechtsanwält*in" by the sender. Users can override the salutation per recipient; overrides are sent as `salutations` to `/api/letters`.

**E-mail**: there is deliberately no server-side sending (decided against SMTP: From-address/SPF issues, sender authenticity, spam risk). In step 3 the user picks their provider once (`MAIL_PROVIDERS` in `static/app.js`, remembered in `localStorage`); each recipient then gets one button (`mailto:` or a Gmail/Outlook.com/Microsoft 365/Yahoo compose deep link) plus copy buttons for address, subject and text. Only providers whose compose link prefills recipient, subject and body are listed; GMX/WEB.DE/t-online have none and fall under "other" (copy buttons only). For providers with a prefilled variant, an "open all" button opens every e-mail at once (`mailto:` sequentially every 500 ms; webmail via `window.open`, stopping at the first tab the pop-up blocker refuses and resuming from there on the next click via `state.pendingBulkIds`). During development `MAIL_TEST_RECIPIENT` in `static/app.js` redirects all e-mails to a test address; do not clear it until asked.

**Data flow**:
1. `data/wks.json` (826 KB, pre-processed) is loaded into memory at startup inside `BundestagData`
2. On search, `find_by_zip()` does recursive tree traversal through the nested state → constituency → member hierarchy
3. Results are deduplicated by `(name, constituency, profile_url)` tuple
4. For each member, the server fetches their bundestag.de profile page (8s timeout) to extract email, office address, and contact form URL — results are cached in-memory to avoid repeat fetches

**Key classes in `app.py`**:
- `BundestagData` — loads `wks.json`, searches by zip, fetches/caches profile data
- `RequestHandler` — HTTP request routing and static file serving

## Data

- `data/wks.json` — the working data file used at runtime (states → constituencies → members with PLZ arrays)
- `data/emails.json` — MdB e-mail addresses keyed by bundestag.de profile id (or `name:<Name>` for members without a profile link); takes precedence over scraped addresses. Regenerate with `python scripts/collect_emails.py` (scrapes the Fraktion websites; entries with `"manual": true` were researched by hand and are preserved). bundestag.de itself sits behind a rate-limit challenge ("enodia"), so live profile scraping often returns nothing
- `data/genders.json` — MdB gender (`m`/`w`/`d`), keyed like `emails.json`; determines the default salutation ("Sehr geehrter Herr …" / "Sehr geehrte Frau …" / "Guten Tag, Vorname Nachname,"; academic degrees and noble ranks are taken from the name in `wks.json`), which users can override per recipient in step 2. Regenerate with `python scripts/collect_genders.py` (reads the Stammdaten XML; `"manual": true` entries are preserved)
- `data/stammdaten/MDB_STAMMDATEN.XML` — the original XML source (15.2 MB) from the Bundestag open data export
- The JSON parser uses flexible key matching (multiple possible key names for states, constituencies, members, zip codes) to be robust against format variations in the source data
