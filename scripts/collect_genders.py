"""Collect the gender of each MdB from the Bundestag open data export.

The gender determines the default salutation of a letter ("Sehr geehrter Herr …",
"Sehr geehrte Frau …", or "Guten Tag, Vorname Nachname," for everyone else).
The result is stored in ``data/genders.json`` (keyed like ``data/emails.json``)
with ``"gender"`` being one of ``"m"``, ``"w"`` or ``"d"``.

Entries marked ``"manual": true`` (corrected by hand) are kept when the script
is re-run.

Usage: python scripts/collect_genders.py
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collect_emails import iter_members, match_name, member_key, normalize_name  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
WKS_FILE = BASE_DIR / "data" / "wks.json"
XML_FILE = BASE_DIR / "data" / "stammdaten" / "MDB_STAMMDATEN.XML"
OUT_FILE = BASE_DIR / "data" / "genders.json"
ELECTORAL_TERM = "21"
GENDER_CODES = {"männlich": "m", "weiblich": "w", "divers": "d"}


def stammdaten_genders(current_term_only: bool) -> Dict[str, str]:
    """Map the normalized names of all (or only current) members to a gender code."""
    genders: Dict[str, str] = {}
    for mdb in ET.parse(XML_FILE).getroot().iter("MDB"):
        terms = {term.findtext("WP") for term in mdb.iter("WAHLPERIODE")}
        if current_term_only and ELECTORAL_TERM not in terms:
            continue
        gender = GENDER_CODES.get((mdb.findtext("BIOGRAFISCHE_ANGABEN/GESCHLECHT") or "").strip())
        if not gender:
            continue
        for name in mdb.iter("NAME"):
            parts = [name.findtext(tag) or "" for tag in ("VORNAME", "PRAEFIX", "ADEL", "NACHNAME")]
            genders[normalize_name(" ".join(parts))] = gender
    return genders


def main() -> None:
    members: Dict[str, dict] = {}
    for member in iter_members(json.loads(WKS_FILE.read_text(encoding="utf-8"))):
        members[member_key(member)] = member

    # Prefer current members; fall back to former ones for candidates that are not (or no longer) MdB.
    current, former = stammdaten_genders(True), stammdaten_genders(False)
    result: Dict[str, dict] = {}
    if OUT_FILE.exists():
        previous = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        result = {key: entry for key, entry in previous.items() if entry.get("manual")}

    missing = []
    for key, member in members.items():
        if result.get(key, {}).get("manual"):
            continue
        gender = match_name([member["name"]], current) or match_name([member["name"]], former)
        if gender:
            result[key] = {"name": member["name"], "gender": gender}
        else:
            missing.append(member["name"])

    OUT_FILE.write_text(json.dumps(dict(sorted(result.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(result)}/{len(members)} with gender; missing:", *missing, sep="\n  ", file=sys.stderr)


if __name__ == "__main__":
    main()
