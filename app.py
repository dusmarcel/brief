from __future__ import annotations

import http.server
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "wks.json"
STATIC_DIR = BASE_DIR / "static"
BUNDESTAG_BASE = "https://www.bundestag.de"


def _normalize_zip(code: str) -> str:
    return re.sub(r"\D", "", (code or "").strip())


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip_admin_suffix(name: str) -> str:
    value = (name or "").strip()
    value = re.sub(
        r",\s*(landeshauptstadt|kreisfreie\s+stadt|stadt|st\.?|gemeinde|markt|flecken|dorf)$",
        "",
        value,
        flags=re.I,
    )
    return value.strip()


def _format_county_label(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return value
    if "," in value:
        left, right = [part.strip() for part in value.split(",", 1)]
        if right:
            return f"{left} ({right})"
    lower = value.lower()
    if any(token in lower for token in ("kreis", "landkreis", "stadtkreis", "kreisfreie stadt")):
        return value
    return f"Kreis {value}"


def _slugify_email_part(value: str) -> str:
    text = (value or "").strip().lower()
    text = (
        text.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def _strip_leading_titles(value: str) -> str:
    title_pattern = r"^(?:(?:dr|prof|professor|frhr|freiherr)\.?\s+)+"
    return re.sub(title_pattern, "", (value or "").strip(), flags=re.I).strip()


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


def _extract_office_address(html: str, heading: str) -> Optional[str]:
    section_match = re.search(
        rf"(?is)<h[23][^>]*>\s*{re.escape(heading)}\s*</h[23]>(.*?)(?:<h[23]|</section>|</article>|<footer|<aside|$)",
        html,
    )
    if not section_match:
        return None

    block = section_match.group(1)
    block = re.sub(r"</?(?:p|li|ul|ol|div|h[1-6])[^>]*>", "\n", block, flags=re.I)
    block = re.sub(r"<br\s*/?>", "\n", block, flags=re.I)
    block = re.sub(r"<[^>]+>", "", block)
    block = block.replace("&nbsp;", " ")

    lines = [line.strip(" ,") for line in block.splitlines()]
    clean_lines = [line for line in lines if line and len(line) > 2]
    if not clean_lines:
        return None

    address_lines: List[str] = []
    for line in clean_lines:
        if line.lower().startswith("kontakt"):
            break
        address_lines.append(line)
        if re.search(r"\b\d{5}\b", line):
            break

    if not address_lines:
        return None

    return ", ".join(address_lines).strip(", ")


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
        self.constituency_map: Dict[str, dict] = {}
        self.search_targets: Dict[str, dict] = {}
        self._build_search_index()

    def find_by_zip(self, zip_code: str) -> List[dict]:
        target = self._find_unique_zip_target(zip_code)
        if not target:
            return []
        return self.search_by_target(target["id"])

    def suggest(self, query: str, limit: int = 8) -> List[dict]:
        normalized = _normalize_text(query)
        if not normalized:
            return []

        matches: List[Tuple[Tuple[int, int, int, str], dict]] = []
        for target in self.search_targets.values():
            alias_scores = []
            for alias in target["aliases"]:
                if alias == normalized:
                    alias_scores.append((0, len(alias)))
                elif alias.startswith(normalized):
                    alias_scores.append((1, len(alias)))
                elif normalized in alias:
                    alias_scores.append((2, len(alias)))
            if not alias_scores:
                continue
            alias_rank, alias_length = min(alias_scores)
            kind_rank = {"zip": 0, "community": 1, "county": 2, "state": 3}.get(target["kind"], 9)
            matches.append(((alias_rank, kind_rank, alias_length, target["label"]), target))

        matches.sort(key=lambda item: item[0])
        return [self._serialize_target(match[1]) for match in matches[:limit]]

    def resolve_query(self, query: str) -> Tuple[Optional[dict], List[dict]]:
        suggestions = self.suggest(query, limit=8)
        if not suggestions:
            return None, []

        normalized = _normalize_text(query)
        exact = [item for item in suggestions if normalized in item.get("exactTerms", [])]
        if len(exact) == 1:
            return self.search_targets.get(exact[0]["id"]), suggestions
        if len(suggestions) == 1:
            return self.search_targets.get(suggestions[0]["id"]), suggestions
        return None, suggestions

    def search_by_target(self, target_id: str) -> List[dict]:
        target = self.search_targets.get(target_id)
        if not target:
            return []

        results: List[dict] = []
        seen: Set[tuple] = set()
        for constituency_id in target["constituencies"]:
            constituency = self.constituency_map.get(constituency_id)
            if not constituency:
                continue
            for member in constituency["members"]:
                if not isinstance(member, dict):
                    continue
                result = self._build_member_result(
                    member,
                    constituency["state"],
                    constituency["name"],
                )
                key = (
                    result["name"],
                    result["constituency"],
                    result["profileUrl"],
                )
                if key in seen:
                    continue
                seen.add(key)
                results.append(result)
        return results

    def get_target(self, target_id: str) -> Optional[dict]:
        target = self.search_targets.get(target_id)
        if not target:
            return None
        return self._serialize_target(target)

    def _build_search_index(self) -> None:
        federal_states = self.data.get("federalStates") or self.data.get("federal_states") or []
        for state in federal_states:
            if not isinstance(state, dict):
                continue
            state_name = (state.get("name") or "").strip()
            if not state_name:
                continue

            state_constituencies: Set[str] = set()
            for constituency in state.get("constituencies") or []:
                if not self._is_constituency_node(constituency):
                    continue

                const_id = self._register_constituency(state_name, constituency)
                state_constituencies.add(const_id)

                zip_codes = self._collect_zip_codes(constituency)
                for zip_code in zip_codes:
                    self._register_target(
                        target_id=f"zip:{zip_code}",
                        kind="zip",
                        label=zip_code,
                        subtitle=f"Postleitzahl in {state_name}",
                        aliases=[zip_code],
                        constituency_id=const_id,
                    )

                counties = constituency.get("counties") or []
                for county in counties:
                    if not isinstance(county, dict):
                        continue
                    county_name = (county.get("headline") or "").strip()
                    if county_name:
                        county_aliases = {
                            county_name,
                            _strip_admin_suffix(county_name),
                            _format_county_label(county_name),
                        }
                        if "," not in county_name and "kreis" not in county_name.lower():
                            county_aliases.add(f"Kreis {county_name}")
                        self._register_target(
                            target_id=f"county:{state_name}:{county_name}",
                            kind="county",
                            label=_format_county_label(county_name),
                            subtitle=state_name,
                            aliases=list(county_aliases),
                            constituency_id=const_id,
                        )

                    communities = county.get("communities") or []
                    for community in communities:
                        if not isinstance(community, dict):
                            continue
                        community_name = (community.get("name") or "").strip()
                        if not community_name:
                            continue
                        community_label = _strip_admin_suffix(community_name) or community_name
                        community_aliases = {
                            community_name,
                            community_label,
                        }
                        self._register_target(
                            target_id=f"community:{state_name}:{county_name}:{community_name}",
                            kind="community",
                            label=community_label,
                            subtitle=f"{_format_county_label(county_name)}, {state_name}" if county_name else state_name,
                            aliases=list(community_aliases),
                            constituency_id=const_id,
                        )

            self._register_target(
                target_id=f"state:{state_name}",
                kind="state",
                label=state_name,
                subtitle="Bundesland",
                aliases=[state_name],
                constituency_ids=state_constituencies,
            )

    def _register_constituency(self, state_name: str, constituency: dict) -> str:
        const_id = f"{state_name}:{constituency.get('number')}:{constituency.get('name')}"
        self.constituency_map[const_id] = {
            "id": const_id,
            "state": state_name,
            "name": constituency.get("name") or "Unbekannter Wahlkreis",
            "number": constituency.get("number"),
            "members": _to_member_list(_pick_first(constituency, list(self.member_keys), [])),
        }
        return const_id

    def _register_target(
        self,
        target_id: str,
        kind: str,
        label: str,
        subtitle: str,
        aliases: List[str],
        constituency_id: Optional[str] = None,
        constituency_ids: Optional[Set[str]] = None,
    ) -> None:
        if not label:
            return

        target = self.search_targets.get(target_id)
        if not target:
            target = {
                "id": target_id,
                "kind": kind,
                "label": label,
                "subtitle": subtitle,
                "aliases": set(),
                "constituencies": set(),
            }
            self.search_targets[target_id] = target

        for alias in aliases:
            normalized = _normalize_text(alias)
            if normalized:
                target["aliases"].add(normalized)

        if constituency_id:
            target["constituencies"].add(constituency_id)
        if constituency_ids:
            target["constituencies"].update(constituency_ids)

    def _serialize_target(self, target: dict) -> dict:
        return {
            "id": target["id"],
            "kind": target["kind"],
            "label": target["label"],
            "subtitle": target["subtitle"],
            "exactTerms": sorted(target["aliases"]),
            "constituencyCount": len(target["constituencies"]),
        }

    def _find_unique_zip_target(self, zip_code: str) -> Optional[dict]:
        normalized = _normalize_zip(zip_code)
        if len(normalized) != 5:
            return None
        return self.search_targets.get(f"zip:{normalized}")

    def _collect_zip_codes(self, node, seen: Optional[Set[int]] = None) -> Set[str]:
        if seen is None:
            seen = set()
        if id(node) in seen:
            return set()
        seen.add(id(node))

        found: Set[str] = set()
        if isinstance(node, dict):
            for key, value in node.items():
                lower = str(key).lower()
                if "zip" in lower or "plz" in lower:
                    found.update(self._extract_zip_values(value))
                elif isinstance(value, (dict, list)):
                    found.update(self._collect_zip_codes(value, seen))
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    found.update(self._collect_zip_codes(item, seen))
        return found

    def _extract_zip_values(self, value) -> Set[str]:
        found: Set[str] = set()
        if isinstance(value, (list, tuple, set)):
            for item in value:
                normalized = _normalize_zip(str(item))
                if len(normalized) == 5:
                    found.add(normalized)
            return found
        normalized = _normalize_zip(str(value))
        if len(normalized) == 5:
            found.add(normalized)
        return found

    def _build_member_result(self, member: dict, state_name: str, constituency_name: str) -> dict:
        first, last = self._extract_member_name_parts(member)
        name = member.get("name") or f"{first} {last}".strip()

        profile_url = _pick_first(
            member, ["link", "profile", "profileUrl", "url", "bio", "detail"]
        )
        profile_url = _to_absolute(profile_url) if profile_url else None

        faction = _pick_first(
            member, ["party", "faction", "fraktion", "fraktional", "group"]
        ) or "Unbekannt"

        result = {
            "name": name or "Unbekannte Person",
            "faction": faction,
            "constituency": constituency_name,
            "state": state_name,
            "profileUrl": profile_url,
        }
        result.update(self._get_profile_info(profile_url))
        if not result.get("email"):
            guessed_email = self._guess_bundestag_email(first, last)
            if guessed_email:
                result["email"] = guessed_email
                result["emailGuessed"] = True
        else:
            result["emailGuessed"] = False
        return result

    def _extract_member_name_parts(self, member: dict) -> Tuple[str, str]:
        first = (member.get("firstName") or "").strip()
        last = (member.get("lastName") or "").strip()
        if first and last:
            return first, last

        full_name = (member.get("name") or "").strip()
        if "," in full_name:
            last_part, first_part = [part.strip() for part in full_name.split(",", 1)]
            if first_part:
                first = first_part
            last = last_part
        else:
            tokens = [token for token in re.split(r"\s+", full_name) if token]
            if len(tokens) >= 2:
                first = " ".join(tokens[:-1])
                last = tokens[-1]

        last = _strip_leading_titles(last)
        first = _strip_leading_titles(first)
        return first.strip(), last.strip()

    def _guess_bundestag_email(self, first_name: str, last_name: str) -> Optional[str]:
        first = _slugify_email_part(_strip_leading_titles(first_name))
        last = _slugify_email_part(_strip_leading_titles(last_name))
        if not first or not last:
            return None
        return f"{first}.{last}@bundestag.de"

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

        if (
            not self._is_constituency_node(node)
            and any(key in node for key in self.constituency_keys)
            and isinstance(node.get("name"), str)
        ):
            local_state = node.get("name")

        if self._is_constituency_node(node) and isinstance(node.get("name"), str):
            local_const = node.get("name")

        members = _to_member_list(_pick_first(node, list(self.member_keys), []))
        if members and self._is_constituency_node(node) and self._contains_zip(node, target, set()):
            for member in members:
                if not isinstance(member, dict):
                    continue
                result = self._build_member_result(member, local_state, local_const)
                key = (result["name"], local_const, result["profileUrl"])
                if key in seen:
                    continue
                seen.add(key)
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

    def _is_constituency_node(self, node) -> bool:
        if not isinstance(node, dict):
            return False
        return "number" in node and ("counties" in node or any(key in node for key in self.member_keys))

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

        address = _extract_office_address(html, "Wahlkreisbüro")
        if not address:
            address = _extract_office_address(html, "Abgeordnetenbüro")

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
        if parsed.path == "/api/suggest":
            self._handle_api_suggest(parsed)
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
        target_id = (query.get("target", [""])[0] or "").strip()
        text_query = (query.get("q", [""])[0] or "").strip()
        zip_code = (query.get("zip", [""])[0] or "").strip()

        target = None
        suggestions: List[dict] = []
        if target_id:
            target = self.server.store.get_target(target_id)
        elif text_query:
            resolved, suggestions = self.server.store.resolve_query(text_query)
            if resolved:
                target = self.server.store.get_target(resolved["id"])
        elif zip_code:
            normalized = _normalize_zip(zip_code)
            if normalized:
                target = self.server.store.get_target(f"zip:{normalized}")

        results = self.server.store.search_by_target(target["id"]) if target else []
        response = {
            "query": text_query or zip_code,
            "target": target,
            "results": results,
            "suggestions": [] if target else suggestions,
            "ambiguous": bool((text_query or zip_code) and not target and suggestions),
        }
        payload = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_api_suggest(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        text_query = (query.get("q", [""])[0] or "").strip()
        response = {
            "query": text_query,
            "suggestions": self.server.store.suggest(text_query),
        }
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
