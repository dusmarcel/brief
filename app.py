from __future__ import annotations

import http.server
import io
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "wks.json"
STATIC_DIR = BASE_DIR / "static"
BUNDESTAG_BASE = "https://www.bundestag.de"
LETTER_BODY = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.\n\n"
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. "
    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.\n\n"
    "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."
)


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
    text = _normalize_name_spacing(value)
    if not text:
        return ""

    title_pattern = re.compile(
        r"^(?:(?:"
        r"prof(?:essor)?|"
        r"dr(?:\s*[-./]?\s*(?:ing|jur|med|med dent|med vet|phil|rer nat|rer pol|theol))?|"
        r"habil|"
        r"frhr|freiherr|"
        r"dipl(?:\s*[-./]?\s*(?:ing|jur|kfm|volksw|pol|soz))?|"
        r"m\.?a|"
        r"b\.?a|"
        r"m\.?sc|"
        r"b\.?sc|"
        r"ll\.?m"
        r")\.?\s+)+",
        flags=re.I,
    )
    return re.sub(title_pattern, "", text).strip(" ,")


def _normalize_name_spacing(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).strip()


def _merge_name_particles(first: str, last: str) -> Tuple[str, str]:
    particles = {"von", "van", "de", "del", "den", "der", "zu", "zur", "zum", "di", "du", "la", "le"}
    first_tokens = [token for token in re.split(r"\s+", _normalize_name_spacing(first)) if token]
    last_tokens = [token for token in re.split(r"\s+", _normalize_name_spacing(last)) if token]

    while len(first_tokens) > 1 and first_tokens[-1].lower() in particles:
        last_tokens.insert(0, first_tokens.pop())

    return " ".join(first_tokens), " ".join(last_tokens)


def _format_member_display_name(raw_name: str, first: str, last: str) -> str:
    normalized_raw = _normalize_name_spacing(raw_name)
    normalized_first = _normalize_name_spacing(first)
    normalized_last = _normalize_name_spacing(last)

    if "," in normalized_raw and normalized_last:
        return f"{normalized_last}, {normalized_first}" if normalized_first else normalized_last
    if normalized_first and normalized_last:
        return f"{normalized_first} {normalized_last}"
    return normalized_raw or normalized_first or normalized_last


def _slugify_filename(value: str) -> str:
    slug = _slugify_email_part(value).replace("-", "_")
    return slug or "dokument"


EMAIL_OVERRIDES = {
    ("andreas", "jung"): "andreas.jung.wk@bundestag.de",
    ("anja", "troff-schaffarzyk"): "anja.troffschaffarzyk@bundestag.de",
    ("anna", "aeikens"): "info@annaaeikens.de",
    ("anne-mieke", "bremer"): "annemieke.bremer@bundestag.de",
    ("annika", "klose"): "info@klose-annika.de",
    ("armand", "zorn"): "mail@armandzorn.de",
    ("astrid", "timmermann-fechter"): "astrid.timmermannfechter@bundestag.de",
    ("awet", "tesfaiesus"): "awet.tesfaiesus@bundestag.de",
    ("bastian", "ernst"): "kontakt@bastianernst.de",
    ("beatrix", "von-storch"): "info@beatrixvonstorch.de",
    ("birgit", "bessin"): "info@birgitbessin.de",
    ("bodo", "ramelow"): "wahlkreisbuero@bodoramelow.de",
    ("cansin", "koektuerk"): "kontakt@cansinkoektuerk.de",
    ("caroline", "bosbach"): "info@caroline-bosbach.de",
    ("carsten", "schneider"): "carsten.schneider@bundestag.de",
    ("carsten", "schneider-erfurt"): "carsten.schneider@bundestag.de",
    ("christian", "reck"): "post@christian-reck.de",
    ("christiane", "schenderlein"): "kontakt@christiane-schenderlein.de",
    ("christina", "baum"): "webmaster@christina-baum.berlin",
    ("christoph", "birghan"): "christoph.birghan@afdbayern.de",
    ("christoph", "de-vries"): "christoph.devries@bundestag.de",
    ("christoph", "frauenpreiss"): "kontakt@christoph-frauenpreiss.de",
    ("claudia", "moll"): "claudia.moll.wk@bundestag.de",
    ("claudia", "weiss"): "info@claudiaweiss-bernburg.de",
    ("daniel", "baldy"): "daniel.baldy.wk@bundestag.de",
    ("daniel", "koelbl"): "kontakt@daniel-koelbl.de",
    ("daniela", "rump"): "info@danielarump.de",
    ("dario", "seifert"): "dario.seifert@afdfraktion-vr.de",
    ("david", "gregosz"): "hallo@david-gregosz.de",
    ("david", "preisendanz"): "mail@davidpreisendanz.de",
    ("david", "schliesing"): "mail@davidschliesing.de",
    ("derya", "tuerk-nachbaur"): "derya.tuerknachbaur@bundestag.de",
    ("diana", "zimmer"): "diana.zimmer@afd-bw.de",
    ("doris", "achelwilm"): "doris.achelwilm@dielinke-bremen.de",
    ("elisabeth", "winkelmeier-becker"): "elisabeth.winkelmeierbecker@bundestag.de",
    ("ellen", "demuth"): "info@ellendemuth.de",
    ("erhard", "brucker"): "erhard.brucker@afdbayern.de",
    ("esther", "dilcher"): "esther.dilcher.wk@bundestag.de",
    ("felix", "banaszak"): "felix.banaszak@gruene.de",
    ("florian", "bilic"): "kontakt@florianbilic.de",
    ("georg", "guenther"): "info@georgguenther.de",
    ("gregor", "gysi"): "gregor.gysi.wk@bundestag.de",
    ("hans", "theiss"): "info@hanstheiss.de",
    ("harald", "orthey"): "info@harald-orthey.de",
    ("heiko", "hain"): "kontakt@heikohain.de",
    ("helmut", "kleebank"): "helmut.kleebank.wk@bundestag.de",
    ("hendrik", "bollmann"): "hendrik.bollmann@spdherne.de",
    ("hendrik", "streeck"): "kontakt@hendrikstreeck.de",
    ("inge", "graessle"): "post@inge-graessle.de",
    ("ingo", "hahn"): "info@ingo-hahnafd.de",
    ("iris", "nieland"): "info@irisnieland.de",
    ("isabel", "cademartori"): "isabel.cademartori.wk@bundestag.de",
    ("isabel", "mackensen-geis"): "isabel.mackensengeis@bundestag.de",
    ("isabelle", "vandre"): "isabelle.vandre@dielinkepotsdam.de",
    ("jan", "koestering"): "kontakt@jan-koestering.de",
    ("jan", "van-aken"): "jan.vanaken@bundestag.de",
    ("jan-marco", "luczak"): "janmarco.luczak@bundestag.de",
    ("jan-wenzel", "schmidt"): "buero@jan-wenzel-schmidt.de",
    ("janina", "boettger"): "janina.boettger@dielinke-lsa.de",
    ("jeanne", "dillschneider"): "jeanne.dillschneider@gruene-saar.de",
    ("jens", "behrens"): "info@jens-behrens.de",
    ("jens", "peick"): "jens.peick.wk@bundestag.de",
    ("johann", "martel"): "johann.martel@afd-bw.de",
    ("johannes", "rothenberger"): "post@johannesrothenberger.de",
    ("johannes", "wiegelmann"): "post@johanneswiegelmann.de",
    ("johannes", "winkel"): "info@johanneswinkel.de",
    ("jorrit", "bosch"): "jorrit.bosch@die-linkebs.de",
    ("juergen", "cosse"): "juergen.cosse.wk@bundestag.de",
    ("kassem", "taher-saleh"): "kassem.tahersaleh@bundestag.de",
    ("katja", "strauss-koester"): "katja.strausskoester@bundestag.de",
    ("katrin", "fey"): "katrin.fey@die-linke-siegen-wittgenstein.de",
    ("kay-uwe", "ziegler"): "kayuwe.ziegler@bundestag.de",
    ("kirsten", "kappert-gonther"): "kirsten.kappertgonther@bundestag.de",
    ("klaus-peter", "willsch"): "klauspeter.willsch.wk@bundestag.de",
    ("konrad", "koerner"): "konrad.koerner@ju-mittelfranken.de",
    ("kurt", "kleinschmidt"): "kontakt@kleinschmidt-kurt.de",
    ("lars", "schieske"): "kontakt@lars-schieske.de",
    ("leif-erik", "holm"): "leiferik.holm@bundestag.de",
    ("lena", "gumnior"): "lena.gumnior@gruene-kv-verden.de",
    ("marcel", "queckemeyer"): "marcelqueckemeyer@icloud.com",
    ("martin", "kroeber"): "martin.kroeber.wk@bundestag.de",
    ("mathias", "weiser"): "mathias.weiser@afdvogtland.de",
    ("matthias", "rentzsch"): "matthias.rentzsch@afddd.de",
    ("maximilian", "krah"): "maximilian.krah@europarl.europa.eu",
    ("michael", "hose"): "kontakt@michaelhose.de",
    ("michael", "kaufmann"): "michael.kaufmann@bundestag.de",
    ("michael", "thews"): "spd@michaelthews.de",
    ("mirze", "edis"): "mirze.edis@dielinke-du.de",
    ("nicolas", "zippelius"): "mail@nicolas-zippelius.de",
    ("nils", "schmid"): "wahlkreis@nilsschmid.de",
    ("oliver", "poepsel"): "info@oliverpoepsel.de",
    ("omid", "nouripour"): "omid.nouripour.wk@bundestag.de",
    ("pascal", "reddig"): "kontakt@pascalreddig.de",
    ("paul", "schmidt"): "info@drpaulschmidt.de",
    ("philipp", "amthor"): "kontakt@philipp-amthor.de",
    ("philipp", "rottwilm"): "kontakt@philipprottwilm.de",
    ("raimond", "scheirich"): "raimond.scheirich@afdbayern.de",
    ("rainer", "galla"): "presse@rainer-galla.de",
    ("ralph", "edelhaeusser"): "kontakt@ralphedelhaeusser.de",
    ("rebecca", "lenhard"): "rebecca.lenhard@gruene-nbg.de",
    ("reinhard", "brandl"): "reinhard.brandl.wk@bundestag.de",
    ("rene", "bochmann"): "rene.bochmann@afdnordsachsen.de",
    ("rita", "schwarzeluehr-sutter"): "rita.schwarzeluehrsutter@bundestag.de",
    ("ronja", "kemmer"): "ronja.kemmer.wk@bundestag.de",
    ("ruben", "rupp"): "ruben.rupp@afd-bw.de",
    ("sabine", "dittmar"): "sabine.dittmar.wk@bundestag.de",
    ("sahra", "mirow"): "sahra.mirow@dielinke-bw.de",
    ("sandra", "carstensen"): "mail@sandra-carstensen.de",
    ("sascha", "van-beek"): "info@saschavanbeek.de",
    ("sascha", "wagner"): "sascha.wagner@dielinke-nrw.de",
    ("saskia", "ludwig"): "buero@saskia-ludwig.de",
    ("sebastian", "maack"): "sebastian@maack.net",
    ("sebastian", "muenzenmaier"): "info@sebastianmuenzenmaier.de",
    ("sebastian", "steineke"): "info@sebastian-steineke.de",
    ("simone", "fischer"): "simone.fischer@gruene-stuttgart.de",
    ("stefan", "seidler"): "stefan.seidler.wk@bundestag.de",
    ("stella", "merendino"): "info@stella-merendino.de",
    ("stephan", "albani"): "info@stephan-albani.de",
    ("tarek", "al-wazir"): "tarek.alwazir.wk@bundestag.de",
    ("thomas", "ladzinski"): "thomas.ladzinski@afd-dd.de",
    ("thomas", "silberhorn"): "thomas.silberhorn.wk@bundestag.de",
    ("thomas", "stephan"): "info@afd-thomas-stephan.de",
    ("ulrich", "von-zons"): "ulrich.vonzons@bundestag.de",
    ("ulrike", "schielke-ziesing"): "ulrike.schielkeziesing@bundestag.de",
    ("uwe", "feiler"): "team@uwe-feiler.de",
    ("victoria", "brossart"): "info@victoria-brossart.de",
    ("vivian", "tauschwitz"): "vivian.tauschwitz@cduheidekreis.de",
    ("volker", "mayer-lay"): "volker.mayerlay@bundestag.de",
    ("volker", "scheurell"): "volker.scheurell@afd-wb.de",
    ("wiebke", "esdar"): "wiebke.esdar.wk@bundestag.de",
    ("wilhelm", "gebhard"): "info@wilhelmgebhard.de",
    ("wolfgang", "stefinger"): "info@wolfgang-stefinger.de",
    ("wolfgang", "wiehle"): "kontakt@wolfgang-wiehle.de",
}


def _get_email_override(first_name: str, last_name: str) -> Optional[str]:
    first = _slugify_email_part(_strip_leading_titles(first_name))
    last = _slugify_email_part(_strip_leading_titles(last_name))
    if not first or not last:
        return None
    return EMAIL_OVERRIDES.get((first, last))


def _split_address_lines(value: str) -> List[str]:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    if "\n" in text:
        return [line.strip() for line in text.split("\n") if line.strip()]
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) <= 1:
        return parts
    if len(parts) == 2:
        return parts
    if re.search(r"\b\d{5}\b", parts[-1]):
        if len(parts) == 3:
            return [f"{parts[0]} {parts[1]}", parts[2]]
        return [parts[0], " ".join(parts[1:-1]), parts[-1]]
    return parts[:-2] + [f"{parts[-2]} {parts[-1]}"]


def _extract_city_from_address(value: str) -> str:
    lines = _split_address_lines(value)
    if not lines:
        return ""
    last_line = lines[-1]
    match = re.search(r"\b\d{5}\s+(.+)$", last_line)
    if match:
        return match.group(1).strip()
    return last_line.strip()


def _rtf_escape(value: str) -> str:
    escaped: List[str] = []
    for char in value or "":
        code = ord(char)
        if char == "\\":
            escaped.append(r"\\")
        elif char == "{":
            escaped.append(r"\{")
        elif char == "}":
            escaped.append(r"\}")
        elif char == "\n":
            escaped.append(r"\line ")
        elif 32 <= code <= 126:
            escaped.append(char)
        else:
            signed = code if code <= 32767 else code - 65536
            escaped.append(rf"\u{signed}?")
    return "".join(escaped)


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
        self.member_map: Dict[str, dict] = {}
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
            for member_meta in constituency["members"]:
                if not isinstance(member_meta, dict):
                    continue
                result = self._build_member_result(
                    member_meta["raw"],
                    constituency["state"],
                    constituency["name"],
                    member_meta["id"],
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

    def get_members_by_ids(self, member_ids: List[str]) -> List[dict]:
        results: List[dict] = []
        seen: Set[str] = set()
        for member_id in member_ids:
            if member_id in seen:
                continue
            seen.add(member_id)
            member_meta = self.member_map.get(member_id)
            if not member_meta:
                continue
            results.append(
                self._build_member_result(
                    member_meta["raw"],
                    member_meta["state"],
                    member_meta["constituency"],
                    member_id,
                )
            )
        return results

    def build_letter_archive(self, member_ids: List[str], sender: dict) -> bytes:
        recipients = self.get_members_by_ids(member_ids)
        if not recipients:
            raise ValueError("Bitte mindestens eine Empfängerin oder einen Empfänger auswählen.")

        sender_name = (sender.get("name") or "").strip()
        sender_extra = (sender.get("nameExtra") or "").strip()
        sender_address = (sender.get("address") or "").strip()
        sender_email = (sender.get("email") or "").strip()

        if not sender_name or not sender_address:
            raise ValueError("Bitte Name und Anschrift angeben.")

        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for index, recipient in enumerate(recipients, start=1):
                filename = self._build_letter_filename(index, recipient)
                document = self._render_letter_rtf(recipient, sender_name, sender_extra, sender_address, sender_email)
                zf.writestr(filename, document.encode("ascii"))

        archive.seek(0)
        return archive.read()

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
        raw_members = _to_member_list(_pick_first(constituency, list(self.member_keys), []))
        members: List[dict] = []
        for index, member in enumerate(raw_members, start=1):
            if not isinstance(member, dict):
                continue
            member_id = self._member_identifier(state_name, constituency, member, index)
            member_meta = {
                "id": member_id,
                "raw": member,
                "state": state_name,
                "constituency": constituency.get("name") or "Unbekannter Wahlkreis",
            }
            self.member_map[member_id] = member_meta
            members.append(member_meta)

        self.constituency_map[const_id] = {
            "id": const_id,
            "state": state_name,
            "name": constituency.get("name") or "Unbekannter Wahlkreis",
            "number": constituency.get("number"),
            "members": members,
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

    def _member_identifier(self, state_name: str, constituency: dict, member: dict, index: int) -> str:
        member_name = member.get("name") or f"{member.get('firstName', '')} {member.get('lastName', '')}".strip()
        number = constituency.get("number") or "xx"
        return f"member:{_slugify_filename(state_name)}:{number}:{_slugify_filename(member_name)}:{index}"

    def _build_letter_filename(self, index: int, recipient: dict) -> str:
        recipient_slug = _slugify_filename(recipient.get("name") or f"schreiben_{index}")
        constituency_slug = _slugify_filename(recipient.get("constituency") or "wahlkreis")
        return f"{index:02d}_{recipient_slug}_{constituency_slug}.rtf"

    def _render_letter_rtf(
        self,
        recipient: dict,
        sender_name: str,
        sender_extra: str,
        sender_address: str,
        sender_email: str,
    ) -> str:
        sender_lines = [sender_name]
        sender_lines.extend(_split_address_lines(sender_address))
        if sender_email:
            sender_lines.append(sender_email)

        recipient_lines = [recipient.get("fullName") or recipient.get("name") or "Bundestagsabgeordnete Person"]
        if recipient.get("officeAddress") and recipient["officeAddress"] != "Nicht verfügbar":
            recipient_lines.extend(_split_address_lines(recipient["officeAddress"]))
        else:
            recipient_lines.append(recipient.get("constituency") or "Bundestag")
            if recipient.get("state"):
                recipient_lines.append(recipient["state"])

        salutation_name = recipient.get("fullName") or recipient.get("name") or "Abgeordnete Person"
        salutation = f"Guten Tag, {salutation_name},"
        sender_city = _extract_city_from_address(sender_address)
        today = date.today().strftime("%d.%m.%Y")
        date_line = f"{sender_city}, den {today}" if sender_city else today

        lines = [
            r"{\rtf1\ansi\deff0",
            r"{\fonttbl{\f0 Arial;}}",
            r"\fs24 ",
            _rtf_escape("\n".join(sender_lines)),
            r"\par\par\par ",
            _rtf_escape("\n".join(recipient_lines)),
            r"\par\par\par ",
            _rtf_escape(date_line),
            r"\par\par ",
            r"\b " + _rtf_escape("Behördenunabhängige Asylverfahrensberatung gemäß § 12a AsylG") + r"\b0 ",
            r"\par\par\par ",
            _rtf_escape(salutation),
            r"\par\par ",
            _rtf_escape(LETTER_BODY),
            r"\par\par ",
            _rtf_escape("Mit freundlichen Grüßen"),
            r"\par\par ",
            _rtf_escape(sender_name),
            (r"\par " + _rtf_escape(sender_extra)) if sender_extra else "",
            r"}",
        ]
        return "".join(lines)

    def _build_member_result(
        self,
        member: dict,
        state_name: str,
        constituency_name: str,
        member_id: Optional[str] = None,
    ) -> dict:
        first, last = self._extract_member_name_parts(member)
        name = member.get("name") or f"{first} {last}".strip()
        display_name = _format_member_display_name(member.get("name") or "", first, last) or name
        full_name = _normalize_name_spacing(f"{first} {last}") or name

        profile_url = _pick_first(
            member, ["link", "profile", "profileUrl", "url", "bio", "detail"]
        )
        profile_url = _to_absolute(profile_url) if profile_url else None

        faction = _pick_first(
            member, ["party", "faction", "fraktion", "fraktional", "group"]
        ) or "Unbekannt"

        result = {
            "id": member_id,
            "name": name or "Unbekannte Person",
            "displayName": display_name or "Unbekannte Person",
            "fullName": full_name or "Unbekannte Person",
            "faction": faction,
            "constituency": constituency_name,
            "state": state_name,
            "profileUrl": profile_url,
        }
        result.update(self._get_profile_info(profile_url))
        override_email = _get_email_override(first, last)
        if override_email:
            result["email"] = override_email
            result["emailGuessed"] = False
        elif not result.get("email"):
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
        first, last = _merge_name_particles(first, last)
        return first.strip(), last.strip()

    def _guess_bundestag_email(self, first_name: str, last_name: str) -> Optional[str]:
        first = _slugify_email_part(_strip_leading_titles(first_name))
        last = _slugify_email_part(_strip_leading_titles(last_name))
        if not first or not last:
            return None
        override = EMAIL_OVERRIDES.get((first, last))
        if override:
            return override
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

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/letters":
            self._handle_api_letters()
            return
        self._not_found()

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

    def _handle_api_letters(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0

        raw = self.rfile.read(content_length) if content_length else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._json_error("Ungültige Anfragedaten.", status=400)
            return

        member_ids = payload.get("memberIds") or []
        sender = payload.get("sender") or {}

        try:
            archive = self.server.store.build_letter_archive(member_ids, sender)
        except ValueError as exc:
            self._json_error(str(exc), status=400)
            return

        filename = f"bundestag-schreiben-{date.today().isoformat()}.zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(archive)))
        self.end_headers()
        self.wfile.write(archive)

    def _json_error(self, message: str, status: int = 400):
        payload = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
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
