"""Collect MdB e-mail addresses from the parliamentary group (Fraktion) websites.

bundestag.de profile pages rarely list e-mail addresses and are protected by a
rate-limit challenge, so the addresses are collected once from the Fraktion
websites and stored in ``data/emails.json`` (keyed by bundestag.de profile id, or "name:<Name>" for members without a profile link).

Entries marked ``"manual": true`` (researched by hand for members whose
Fraktion page lists no usable address) are kept when the script is re-run.

Usage: python scripts/collect_emails.py
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Iterable, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
WKS_FILE = BASE_DIR / "data" / "wks.json"
OUT_FILE = BASE_DIR / "data" / "emails.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
EMAIL_RE = re.compile(r"(?<![\w.%+\\-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PROFILE_ID_RE = re.compile(r"biografien/[A-Z]/[^\"'\s?#]*?-(\d+)")
GENERIC_LOCALPARTS = {"name", "vorname.nachname", "info", "presse", "pressestelle", "buerger", "dialog", "direktkommunikation", "kontakt", "post"}


def fetch(url: str, retries: int = 2) -> str:
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as response:
                return response.read().decode("utf-8", errors="ignore")
        except Exception:
            if attempt == retries:
                return ""
            time.sleep(2)
    return ""


def normalize_name(value: str) -> str:
    text = (value or "").lower()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b(dr|prof|med|jur|phil|rer|nat|pol|ing|h\s*c|dipl)\b\.?", " ", text)
    return " ".join(sorted(re.findall(r"[a-z]+", text)))


def decode_page(raw: str) -> str:
    # CDU/CSU obfuscates mailto links with HTML entities and percent-encoding.
    text = html.unescape(raw)
    return re.sub(r"mailto:[^\"'\s>]+", lambda m: urllib.parse.unquote(m.group(0)), text)


def personal_emails(page: str) -> List[str]:
    found: List[str] = []
    for email in EMAIL_RE.findall(decode_page(page)):
        email = email.strip(".").lower()
        local, _, domain = email.partition("@")
        if local in GENERIC_LOCALPARTS or domain in {"bla.de", "example.com"} or domain.endswith((".png", ".jpg", ".svg", ".webp")):
            continue
        if email not in found:
            found.append(email)
    # Prefer the Berlin office address over the constituency (".wk") address.
    found.sort(key=lambda e: (not e.endswith("@bundestag.de"), ".wk@" in e))
    return found


def page_title_name(page: str) -> str:
    match = re.search(r"<title>(.*?)</title>", page, flags=re.S | re.I)
    title = html.unescape(match.group(1)) if match else ""
    return re.split(r"\s[|\-–]\s", title)[0].strip()


def links(page: str, pattern: str, base: str) -> List[str]:
    out: List[str] = []
    for href in re.findall(r'href="([^"]+)"', page):
        href = html.unescape(href)
        if re.search(pattern, href):
            url = urllib.parse.urljoin(base, href)
            if url not in out:
                out.append(url)
    return out


def cducsu_profiles() -> List[str]:
    urls: List[str] = []
    for page_no in range(0, 60):
        page = fetch(f"https://www.cducsu.de/abgeordnete?page={page_no}")
        new = [u for u in links(page, r"^/abgeordnete/[a-z0-9-]+$", "https://www.cducsu.de") if u not in urls]
        if not new:
            break
        urls.extend(new)
    return urls


def spd_profiles() -> List[str]:
    page = fetch("https://www.spdfraktion.de/abgeordnete/alle?wp=21&view=grid&old=21")
    return [u.split("?")[0] for u in links(page, r"^/abgeordnete/[a-z0-9-]+\?wp=21$", "https://www.spdfraktion.de")]


def gruene_profiles() -> List[str]:
    page = fetch("https://www.gruene-bundestag.de/abgeordnete")
    return links(page, r"/abgeordnete/details/[a-z0-9-]+/?$", "https://www.gruene-bundestag.de")


def linke_profiles() -> List[str]:
    page = fetch("https://www.linksfraktion.de/abgeordnete/")
    return links(page, r"^/abgeordnete/profil/[^/]+/?$", "https://www.linksfraktion.de")


def afd_profiles() -> List[str]:
    urls: List[str] = []
    # The alphabetical pages are incomplete, so the per-state pages are crawled as well.
    groups = ("abc", "def", "ghi", "jkl", "mno", "pqr", "stu", "vwz")
    states = ("bb", "be", "bw", "by", "hb", "hh", "hs", "mv", "ni", "nw", "rp", "sh", "sl", "st", "sx", "th")
    for group in groups + states:
        page = fetch(f"https://afdbundestag.de/abgeordnete-{group}/")
        found = links(page, r"^(https://afdbundestag\.de)?/abgeordnete/[a-z0-9-]+/?$", "https://afdbundestag.de")
        # State pages link profiles at the site root, e.g. "/ronald-glaeser/".
        found += [
            f"https://afdbundestag.de/abgeordnete/{slug}/"
            for slug in re.findall(r'href="/([a-z0-9]+-[a-z0-9-]+)/"', page)
            if not slug.startswith("abgeordnete")
        ]
        for url in found:
            if url not in urls:
                urls.append(url)
    return urls


SOURCES = {
    "CDU/CSU": cducsu_profiles,
    "SPD": spd_profiles,
    "Bündnis 90/Die Grünen": gruene_profiles,
    "Die Linke": linke_profiles,
    "AfD": afd_profiles,
}


def scrape_profile(url: str) -> dict:
    page = fetch(url)
    time.sleep(0.3)
    ids = PROFILE_ID_RE.findall(html.unescape(page))
    return {
        "url": url,
        "names": [page_title_name(page), url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")]
        + [e.split("@")[0].replace(".", " ") for e in personal_emails(page)[:1]],
        "profileId": ids[0] if ids else None,
        "emails": personal_emails(page),
    }


def iter_members(node) -> Iterable[dict]:
    if isinstance(node, dict):
        for member in node.get("mdbs") or []:
            if isinstance(member, dict) and member.get("name"):
                yield member
        for value in node.values():
            yield from iter_members(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_members(value)


def match_name(names: List[str], by_name: Dict[str, str]) -> Optional[str]:
    keys = [normalize_name(name) for name in names if normalize_name(name)]
    for key in keys:
        if key in by_name:
            return by_name[key]
    for key in keys:
        words = set(key.split())
        hits = [pid for n, pid in by_name.items() if len(words) >= 2 and (words <= set(n.split()) or set(n.split()) <= words)]
        if len(hits) == 1:
            return hits[0]
    return None


def profile_id(link: str) -> Optional[str]:
    match = re.search(r"-(\d+)/?$", link or "")
    return match.group(1) if match else None


def member_key(member: dict) -> str:
    # Members without a bundestag.de profile link are keyed by name (see app.py).
    return profile_id(member.get("link") or "") or f"name:{member['name']}"


def main() -> None:
    members: Dict[str, dict] = {}
    for member in iter_members(json.loads(WKS_FILE.read_text(encoding="utf-8"))):
        members[member_key(member)] = member

    by_name = {normalize_name(m["name"]): pid for pid, m in members.items()}
    scraped: List[dict] = []
    for faction, collect in SOURCES.items():
        urls = collect()
        print(f"{faction}: {len(urls)} profiles", file=sys.stderr)
        with ThreadPoolExecutor(4) as pool:
            scraped.extend(pool.map(scrape_profile, urls))

    result: Dict[str, dict] = {}
    if OUT_FILE.exists():
        previous = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        result = {pid: entry for pid, entry in previous.items() if entry.get("manual")}

    for entry in scraped:
        if not entry["emails"]:
            continue
        pid = entry["profileId"] if entry["profileId"] in members else None
        if not pid:
            pid = match_name(entry["names"], by_name)
        if not pid or result.get(pid, {}).get("manual"):
            continue
        result[pid] = {"name": members[pid]["name"], "email": entry["emails"][0], "source": entry["url"]}

    OUT_FILE.write_text(json.dumps(dict(sorted(result.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    missing = [m["name"] + " (" + m.get("party", "") + ")" for pid, m in members.items() if pid not in result]
    print(f"{len(result)}/{len(members)} with e-mail; missing:", *missing, sep="\n  ", file=sys.stderr)


if __name__ == "__main__":
    main()
