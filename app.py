from __future__ import annotations

import http.server
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Set


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "wks.json"
STATIC_DIR = BASE_DIR / "static"
BUNDESTAG_BASE = "https://www.bundestag.de"


def _normalize_zip(code: str) -> str:
    return re.sub(r"\D", "", (code or "").strip())


def _pick_first(obj: dict, keys: List[str], default=None):
    for key in keys:
        if key in obj and obj[key]:
            return obj[key]
    return default


def _to_absolute(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if not url.startswith("/"):
        return f"{BUNDESTAG_BASE}/{url}"
    return f"{BUNDESTAG_BASE}{url}"


def _to_member_list(value) -> List[dict]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _to_child_list(value) -> List[dict]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _load_data() -> dict:
    with DATA_FILE.open("r", encoding="utf-8") as fp:
        return json.load(fp)


class BundestagData:
    state_keys = (
        "federalStates",
        "federal_states",
        "states",
        "bundeslaender",
        "länder",
        "laender",
    )
    constituency_keys = (
        "constituencies",
        "wahlkreise",
        "constituency",
        "districts",
    )
    member_keys = ("mdbs", "members", "abgeordnete", "parlamentarianen")
    zip_keys = (
        "zipCodes",
        "zipcodes",
        "zip",
        "zipCode",
        "plz",
        "plzCode",
        "plzCodes",
        "postleitzahlen",
        "postalCodes",
    )

    def __init__(self, data: dict):
        self.data = data
        self.profile_cache: Dict[str, dict] = {}

    def find_by_zip(self, zip_code: str) -> List[dict]:
        target = _normalize_zip(zip_code)
        if len(target) != 5:
            return []

        results: List[dict] = []
        seen: Set[tuple] = set()
        self._scan(self.data, target, None, None, results, seen)
        return results

    def _scan(
        self,
        node,
        target: str,
        state_name: Optional[str],
        constituency_name: Optional[str],
        results: List[dict],
        seen: Set[tuple],
    ) -> None:
        if isinstance(node, list):
            for item in node:
                self._scan(item, target, state_name, constituency_name, results, seen)
            return

        if not isinstance(node, dict):
            return

        local_state = state_name
        local_const = constituency_name

        if any(key in node for key in self.state_keys) and isinstance(node.get("name"), str):
            local_state = node.get("name")

        if any(key in node for key in self.constituency_keys) and isinstance(node.get("name"), str):
            local_const = node.get("name")

        members = _to_member_list(_pick_first(node, list(self.member_keys), []))
        if members and self._contains_zip(node, target, set()):
            for member in members:
                if not isinstance(member, dict):
                    continue
                first = member.get("firstName", "")
                last = member.get("lastName", "")
                name = member.get("name") or f"{first} {last}".strip()

                profile_url = _pick_first(
                    member, ["link", "profile", "profileUrl", "url", "bio", "detail"]
                )
                profile_url = _to_absolute(profile_url) if profile_url else None

                faction = _pick_first(
                    member, ["party", "faction", "fraktion", "fraktional", "group"]
                ) or "Unbekannt"

                key = (name, local_const, profile_url)
                if key in seen:
                    continue
                seen.add(key)

                result = {
                    "name": name or "Unbekannte Person",
                    "faction": faction,
                    "constituency": local_const,
                    "state": local_state,
                    "profileUrl": profile_url,
                }
                result.update(self._get_profile_info(profile_url))
                results.append(result)

        for key, value in node.items():
            if isinstance(value, (dict, list)):
                next_const = local_const
                if key in self.constituency_keys and isinstance(value, dict) and isinstance(value.get("name"), str):
                    next_const = value.get("name")
                self._scan(value, target, local_state, next_const, results, seen)

    def _contains_zip(self, node, target: str, seen: Set[int]) -> bool:
        if id(node) in seen:
            return False
        if isinstance(node, dict):
            seen.add(id(node))
            for key, value in node.items():
                lower = str(key).lower()
                if "zip" in lower or "plz" in lower:
                    if self._value_has_zip(value, target):
                        return True

                if isinstance(value, (dict, list)):
                    if self._contains_zip(value, target, seen):
                        return True
            return False

        if isinstance(node, list):
            seen.add(id(node))
            for item in node:
                if isinstance(item, (dict, list)) and self._contains_zip(item, target, seen):
                    return True
            return False

        return False

    def _value_has_zip(self, value, target: str) -> bool:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                if _normalize_zip(str(item)) == target:
                    return True
            return False
        return _normalize_zip(str(value)) == target

    def _fetch_html(self, url: str) -> Optional[str]:
        if not url:
            return None
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; BundestagLookup/1.0)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                raw = response.read()
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw.decode("latin1", errors="ignore")
        except Exception:
            return None

    def _extract_contact_data(self, html: str, base_url: str) -> dict:
        data: dict = {"email": None}
        if not html:
            return data

        emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html)
        data["email"] = emails[0] if emails else None

        contact_match = re.search(
            r'href="([^"]*?/services/form(?:ul)?aro/contactform[^"]*?)"',
            html,
            flags=re.I,
        )
        if contact_match:
            data["contactFormUrl"] = _to_absolute(contact_match.group(1))
        else:
            contact_match = re.search(r'href="([^"]*?contactform[^"]*?)"', html, flags=re.I)
            if contact_match:
                data["contactFormUrl"] = _to_absolute(contact_match.group(1))

        office_match = re.search(
            r"(?is)<h3[^>]*>\s*Abgeordnetenbüro\s*</h3>(.*?)(?:<h3|</section>|</article>|<footer|<aside)",
            html,
        )
        if not office_match:
            office_match = re.search(
                r"(?is)<h2[^>]*>\s*Abgeordnetenbüro\s*</h2>(.*?)(?:<h2|</section>|</article>|<footer|<aside)",
                html,
            )

        address = None
        if office_match:
            block = office_match.group(1)
            block = re.sub(r"</?(?:p|li|ul|ol|div|h[1-6])[^>]*>", "\n", block, flags=re.I)
            block = re.sub(r"<br\s*/?>", "\n", block, flags=re.I)
            block = re.sub(r"<[^>]+>", "", block)
            block = block.replace("&nbsp;", " ")
            lines = [line.strip() for line in block.splitlines()]
            clean_lines = [line for line in lines if line and len(line) > 3]
            if clean_lines:
                address = ", ".join(clean_lines[:4]).strip(", ")

        if not address:
            text = re.sub(r"<[^>]+>", " ", html)
            text = text.replace("&nbsp;", " ")
            match = re.search(
                r"([A-Za-zÀ-ÖØ-öø-ÿ\.\-\s']+\d{5}\s+[A-Za-zÀ-ÖØ-öø-ÿ\-. \s]+)",
                text,
            )
            if match:
                address = match.group(1).strip()

        data["officeAddress"] = address or "Nicht verfügbar"
        if data.get("contactFormUrl"):
            data["contact"] = data["contactFormUrl"]
        elif base_url:
            data["contact"] = base_url
        else:
            data["contact"] = None
        return data

    def _get_profile_info(self, profile_url: Optional[str]) -> dict:
        if not profile_url:
            return {
                "officeAddress": "Nicht verfügbar",
                "email": None,
                "contactFormUrl": None,
                "contact": None,
            }

        if profile_url in self.profile_cache:
            return self.profile_cache[profile_url]

        html = self._fetch_html(profile_url)
        info = self._extract_contact_data(html or "", profile_url)
        self.profile_cache[profile_url] = info
        return info


class RequestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "MDB-PLZ-Search/1.0"

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/search":
            self._handle_api_search(parsed)
            return

        if parsed.path == "/":
            file_path = STATIC_DIR / "index.html"
        else:
            file_path = STATIC_DIR / parsed.path.lstrip("/")

        if not file_path.exists() or not file_path.is_file():
            self._not_found()
            return

        with file_path.open("rb") as fp:
            content = fp.read()

        self.send_response(200)
        self.send_header("Content-Type", self._content_type(file_path.suffix.lower()))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_api_search(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        zip_code = (query.get("zip", [""])[0] or "").strip()
        response = {"zip": zip_code, "results": self.server.store.find_by_zip(zip_code)}
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _not_found(self):
        body = b"Not found"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: N802
        return

    @staticmethod
    def _content_type(suffix: str) -> str:
        if suffix == ".html":
            return "text/html; charset=utf-8"
        if suffix == ".js":
            return "application/javascript; charset=utf-8"
        if suffix == ".css":
            return "text/css; charset=utf-8"
        return "application/octet-stream"


def run(host="127.0.0.1", port=8000) -> None:
    data = _load_data()
    store = BundestagData(data)

    class _Server(http.server.ThreadingHTTPServer):
        pass

    server = _Server((host, port), RequestHandler)
    server.store = store
    try:
        print(f"Server läuft auf http://{host}:{port}")
        print("Beenden mit Strg+C")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    port_env = os.getenv("PORT")
    port = int(port_env) if port_env and port_env.isdigit() else 8000
    host = os.getenv("HOST", "127.0.0.1")
    run(host=host, port=port)
