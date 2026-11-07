"""Wikidata (prominence, descriptions) and Wikivoyage (local dishes) helpers.

Wikidata is CC0. Wikivoyage text is CC BY-SA 4.0: dish names are shown with a
short quoted snippet and an attribution link.
"""
from __future__ import annotations

import logging
import re

from app.providers.open.http import OpenHttp
from app.schemas.common import DataSource
from app.schemas.itinerary import DishSuggestion

log = logging.getLogger(__name__)
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"


def wikidata_details(http: OpenHttp, qids: list[str]) -> dict[str, dict]:
    """{qid: {"sitelinks": int (Wikipedia editions), "description": str|None, "label": str|None}}"""
    out: dict[str, dict] = {}
    unique = list(dict.fromkeys(q for q in qids if q.startswith("Q")))
    for i in range(0, len(unique), 50):
        batch = unique[i:i + 50]
        data = http.get_json(WIKIDATA_API, {"action": "wbgetentities", "ids": "|".join(batch), "format": "json",
                                            "props": "sitelinks|descriptions|labels", "languages": "en"},
                             what="Wikidata")
        for qid, ent in (data.get("entities") or {}).items():
            links = ent.get("sitelinks") or {}
            wikipedias = sum(1 for k in links if k.endswith("wiki") and k not in ("commonswiki", "specieswiki",
                                                                                     "wikidatawiki", "metawiki"))
            out[qid] = {
                "sitelinks": wikipedias,
                "description": ((ent.get("descriptions") or {}).get("en") or {}).get("value"),
                "label": ((ent.get("labels") or {}).get("en") or {}).get("value"),
            }
    return out


SPARQL_URL = "https://query.wikidata.org/sparql"
# Wikidata "instance of" label keywords -> interest tags. Items whose types match none are skipped.
TYPE_TAGS: list[tuple[tuple[str, ...], list[str], int]] = [
    (("museum",), ["museums", "history"], 90),
    (("art gallery", "art museum"), ["art", "museums"], 75),
    (("castle", "fortress", "fort", "citadel"), ["monuments", "history", "architecture"], 120),
    (("palace",), ["monuments", "architecture", "history"], 90),
    (("cathedral", "basilica", "church", "chapel", "monastery", "convent", "abbey", "temple", "mosque",
      "synagogue", "shrine", "pagoda", "gurdwara"), ["religious_sites", "architecture"], 40),
    (("monument", "memorial", "statue", "triumphal arch", "obelisk", "column"), ["monuments", "history"], 25),
    (("archaeological site", "ruins", "roman", "ancient"), ["history", "monuments"], 75),
    (("tower", "lighthouse", "bridge", "aqueduct", "gate", "city gate"), ["architecture", "photography"], 30),
    (("square", "plaza", "piazza"), ["architecture", "photography"], 25),
    (("park", "garden", "botanical"), ["parks", "nature"], 45),
    (("viewpoint", "lookout", "belvedere"), ["photography", "nature"], 30),
    (("zoo", "aquarium", "nature reserve", "national park"), ["wildlife", "nature"], 120),
    (("beach",), ["nature", "adventure"], 120),
    (("market", "bazaar"), ["markets", "shopping"], 60),
    (("theatre", "opera house", "concert hall", "cultural center", "arts centre"), ["cultural_centres", "art"], 60),
    (("amusement park", "theme park"), ["adventure"], 180),
    (("tourist attraction", "landmark", "heritage", "historic building", "building", "mansion"), ["architecture"], 40),
]
FREE_KEYS = ("square", "plaza", "piazza", "monument", "memorial", "statue", "obelisk", "column", "park",
             "garden", "viewpoint", "lookout", "bridge", "beach", "market")
# Types that usually charge admission; they override FREE_KEYS ("national monument" is often a ticketed site)
CHARGED_KEYS = ("museum", "palace", "castle", "fortress", "fort", "citadel", "monastery", "abbey", "convent",
                "tower", "zoo", "aquarium", "archaeological", "gallery", "theatre", "amusement", "botanical")
SKIP_TYPES = ("human settlement", "neighbourhood", "neighborhood", "district", "parish", "municipality",
              "street", "avenue", "road", "station", "university", "school", "hospital", "company", "hotel",
              "stadium", "airport", "embassy", "ministry", "government", "office", "bank", "residential",
              "railway", "metro", "bus", "port", "river", "hill", "mountain", "lake", "island", "fountain")


def _classify(type_labels: list[str]) -> tuple[list[str], int] | None:
    labels = [t.lower() for t in type_labels]
    tags: list[str] = []
    minutes = 0
    for keys, tg, mins in TYPE_TAGS:
        if any(k in lab for lab in labels for k in keys):
            tags += [t for t in tg if t not in tags]
            minutes = max(minutes, mins)
    if not tags:
        return None
    # keep only if at least one matching type label is not an obviously non-visitable type
    matched = [lab for lab in labels if any(k in lab for keys, _, _ in TYPE_TAGS for k in keys)]
    if not any(not any(s in lab for s in SKIP_TYPES) for lab in matched):
        return None
    return tags, minutes


def wikidata_notable_places(http: OpenHttp, lat: float, lng: float, radius_km: float,
                            min_links: int = 5, limit: int = 400) -> list[Place]:
    """Notable visitable places near a point, ranked by Wikipedia coverage (prominence)."""
    from app.schemas.common import LatLng, Money
    from app.schemas.place import OpeningHours, Place, PlaceKind

    query = f"""
SELECT ?item ?itemLabel ?desc ?lat ?lon ?links (GROUP_CONCAT(DISTINCT ?typeLabel; separator="|") AS ?types) WHERE {{
  SERVICE wikibase:around {{ ?item wdt:P625 ?loc . bd:serviceParam wikibase:center "Point({lng} {lat})"^^geo:wktLiteral .
                            bd:serviceParam wikibase:radius "{radius_km:.1f}" . }}
  ?item wikibase:sitelinks ?links . FILTER(?links >= {min_links})
  ?item wdt:P31 ?t . ?t rdfs:label ?typeLabel . FILTER(LANG(?typeLabel) = "en")
  BIND(geof:latitude(?loc) AS ?lat) BIND(geof:longitude(?loc) AS ?lon)
  OPTIONAL {{ ?item schema:description ?desc . FILTER(LANG(?desc) = "en") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
}} GROUP BY ?item ?itemLabel ?desc ?lat ?lon ?links ORDER BY DESC(?links) LIMIT {limit}"""
    data = http.get_json(SPARQL_URL, {"query": query, "format": "json"}, what="Wikidata query service")
    out: list[Place] = []
    seen: set[str] = set()
    for b in (data.get("results") or {}).get("bindings", []):
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        name = b.get("itemLabel", {}).get("value", "")
        if qid in seen or not name or name == qid:
            continue
        seen.add(qid)
        cls = _classify(b.get("types", {}).get("value", "").split("|"))
        if cls is None:
            continue
        tags, minutes = cls
        labels = b.get("types", {}).get("value", "").lower()
        free = any(k in labels for k in FREE_KEYS) and not any(k in labels for k in CHARGED_KEYS)
        kind = PlaceKind.PARK if "parks" in tags and "museums" not in tags else PlaceKind.ATTRACTION
        out.append(Place(
            id=f"wd:{qid}", name=name, kind=kind, categories=tags,
            location=LatLng(lat=float(b["lat"]["value"]), lng=float(b["lon"]["value"])),
            description=b.get("desc", {}).get("value"), typical_visit_minutes=minutes or 45,
            entry_fee=(Money(amount=0, currency="USD", source=DataSource.ESTIMATE, note="Usually free for this type of place (no fee data) - assumption")
                       if free else None),
            opening_hours=OpeningHours(known=False, weekly={}, source=DataSource.WIKIDATA),
            best_time=["morning", "afternoon"] if kind == PlaceKind.PARK else [],
            external_ids={"wikidata": qid}, prominence=int(b["links"]["value"]), source=DataSource.WIKIDATA,
        ))
    return out


# ----------------------------------------------------------------------- Wikivoyage
_EAT_TITLES = ("eat", "eat and drink", "food", "food and drink", "cuisine")
_STOP_WORDS = {"restaurant", "restaurants", "street", "market", "budget", "mid-range", "splurge", "cafe", "cafes",
               "bar", "bars", "hotel", "eat", "drink", "breakfast", "lunch", "dinner", "note", "warning", "tip",
               "the", "food", "cuisine", "local", "vegetarian", "vegan", "halal", "kosher", "free", "price"}


def _strip_templates(text: str) -> str:
    prev = None
    while prev != text:  # remove nested {{...}} (listings, infoboxes)
        prev = text
        text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", " ", text, flags=re.I)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>|<[^>]+>", " ", text, flags=re.S)
    return text


def _sentence(text: str, term: str) -> str:
    plain = re.sub(r"'{2,}", "", text)
    for s in re.split(r"(?<=[.!?])\s+|\n+", plain):
        if term.lower() in s.lower():
            return s.strip()[:180]
    return ""


# Words that describe a dish itself (generic words like "eat", "food" or "try" are not enough)
_FOOD_WORDS = re.compile(
    r"\b(dish|dishes|sweet|sweets|pastry|pastries|tart|soup|stew|sandwich|dessert|cake|cakes|speciality|specialty|"
    r"specialities|specialties|grilled|fried|baked|roasted|snack|snacks|delicacy|delicacies|dumplings?|noodles?|"
    r"curry|sausage|pie|bun|buns|custard|fritters?|skewers?)\b", re.I)
_NOT_DISHES = {"couvert", "prato do dia", "pratos do dia", "menu", "menu do dia", "tasca", "tascas", "petiscos",
               "happy hour", "brunch", "buffet", "street food", "fast food", "set menu", "a la carte"}


def fold(s: str) -> str:
    """Lower-case, accent-stripped form for matching ('Pastéis' -> 'pasteis')."""
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def extract_dishes(wikitext: str, lexicon: set[str]) -> list[tuple[str, str]]:
    """(dish name, evidence sentence) pairs from an Eat section.

    Known dishes (lexicon) are matched anywhere, accent-insensitively. Other terms are kept only
    when italicised or lower-case (how guides mark foreign dish names) and their sentence talks about
    food, which filters out neighbourhood and venue names that guides set in bold.
    """
    text = _strip_templates(wikitext)
    text = re.sub(r"^=+.*?=+\s*$", " ", text, flags=re.M)  # headings
    found: dict[str, str] = {}
    folded = fold(text)
    for dish in lexicon:
        if re.search(rf"\b{re.escape(dish)}\b", folded):
            found.setdefault(dish, _sentence(text, dish) or _sentence(folded, dish))
    for m in re.finditer(r"(?<!')''([^'\n]{3,40}?)''(?!')|'''([^'\n]{3,40}?)'''", text):
        italic, bold = m.group(1), m.group(2)
        term = (italic or bold or "").strip(" ,.:;()")
        words = term.split()
        if not (1 <= len(words) <= 4) or any(ch.isdigit() for ch in term) or fold(term) in _STOP_WORDS \
                or fold(term) in _NOT_DISHES:
            continue
        if bold and term[:1].isupper():
            continue  # bold Title Case = usually a venue or district
        sentence = _sentence(text, term)
        if not sentence or not _FOOD_WORDS.search(sentence):
            continue
        found.setdefault(fold(term), sentence)
    # collapse plural/alias spellings onto one name ("pasteis de nata" -> "pastel de nata")
    out: dict[str, str] = {}
    for k, v in found.items():
        if v:
            out.setdefault(DISH_ALIASES.get(k, k), v)
    return list(out.items())[:12]


DISH_ALIASES = {"pasteis de nata": "pastel de nata", "pasteis de belem": "pastel de nata", "momos": "momo",
                "tacos": "tacos", "dumpling": "dumplings", "crepes": "crepe", "churro": "churros"}


def wikivoyage_dishes(http: OpenHttp, city_name: str, lexicon: set[str]) -> tuple[list[DishSuggestion], str | None]:
    """Returns dish suggestions and the Wikivoyage page title used (for attribution)."""
    q = http.get_json(WIKIVOYAGE_API, {"action": "query", "titles": city_name, "redirects": 1, "format": "json"},
                      what="Wikivoyage")
    pages = (q.get("query") or {}).get("pages") or {}
    page = next(iter(pages.values()), {})
    if not page or "missing" in page:
        return [], None
    title = page["title"]
    secs = http.get_json(WIKIVOYAGE_API, {"action": "parse", "page": title, "prop": "sections", "format": "json"},
                         what="Wikivoyage")
    index = next((s["index"] for s in (secs.get("parse") or {}).get("sections", [])
                  if s.get("line", "").strip().lower() in _EAT_TITLES and s.get("toclevel") == 1), None)
    if index is None:
        return [], title
    body = http.get_json(WIKIVOYAGE_API, {"action": "parse", "page": title, "section": index, "prop": "wikitext",
                                          "format": "json"}, what="Wikivoyage")
    wikitext = ((body.get("parse") or {}).get("wikitext") or {}).get("*", "")
    dishes = [DishSuggestion(name=name.title(), status="guide", evidence=[f'Wikivoyage ({title}): "{ev}"'],
                             evidence_source=DataSource.WIKIVOYAGE, mention_count=1)
              for name, ev in extract_dishes(wikitext, lexicon)]
    return dishes, title
