# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

"Brief" is a single-page web app for looking up German Bundestag representatives (MdBs) by postal code (PLZ). It combines static election district data with live scraping of bundestag.de member profiles for current contact info.

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

The production image uses the `runtime` stage:

```bash
docker build --target runtime -t brief .
docker run -p 8000:8000 brief
```

## Architecture

**Backend** (`app.py`): Python `ThreadingHTTPServer` with two routes:
- `GET /` → serves `static/index.html`
- `GET /api/search?zip=XXXXX` → returns JSON array of matching representatives

**Frontend** (`static/`): Vanilla JS/HTML/CSS — no frameworks, no bundler.

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
- `data/stammdaten/MDB_STAMMDATEN.XML` — the original XML source (15.2 MB) from the Bundestag open data export
- The JSON parser uses flexible key matching (multiple possible key names for states, constituencies, members, zip codes) to be robust against format variations in the source data
