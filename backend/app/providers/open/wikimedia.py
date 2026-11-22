"""Wikidata (prominence, descriptions, photos), Wikipedia (how many people read about a place) and Wikivoyage
(local dishes, the sights its guide recommends) helpers.

Wikidata is CC0. Wikivoyage text is CC BY-SA 4.0: dish names are shown with a short quoted snippet and an
attribution link. Page-view counts are open Wikimedia statistics. All of it is fetched once when a city is built
and kept with the city's cached data, never per plan.
"""
from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.core.text import fold
from app.core.urls import wikidata_qid
from app.providers.open.http import OpenHttp
from app.schemas.common import DataSource, LatLng, Money
from app.schemas.itinerary import DishSuggestion
from app.schemas.place import OpeningHours, Place, PlaceKind

WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
READER_DAYS = 30      # Wikipedia readers are counted over this many days
_TITLES_PER_CALL = 50   # the most titles the Wikipedia API takes in one query
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
    # Only validated numbers are interpolated into the SPARQL text; nothing user-typed reaches it.
    lat, lng, radius_km = float(lat), float(lng), float(radius_km)
    if not all(math.isfinite(v) for v in (lat, lng, radius_km)):
        raise ValueError("non-finite coordinate")
    min_links, limit = int(min_links), int(limit)
    query = f"""
SELECT ?item ?itemLabel ?desc ?lat ?lon ?links (GROUP_CONCAT(DISTINCT ?typeLabel; separator="|") AS ?types)
       (SAMPLE(?img) AS ?image) (SAMPLE(?enwiki) AS ?article) WHERE {{
  SERVICE wikibase:around {{ ?item wdt:P625 ?loc . bd:serviceParam wikibase:center "Point({lng} {lat})"^^geo:wktLiteral .
                            bd:serviceParam wikibase:radius "{radius_km:.1f}" . }}
  ?item wikibase:sitelinks ?links . FILTER(?links >= {min_links})
  ?item wdt:P31 ?t . ?t rdfs:label ?typeLabel . FILTER(LANG(?typeLabel) = "en")
  BIND(geof:latitude(?loc) AS ?lat) BIND(geof:longitude(?loc) AS ?lon)
  OPTIONAL {{ ?item schema:description ?desc . FILTER(LANG(?desc) = "en") }}
  OPTIONAL {{ ?item wdt:P18 ?img . }}
  OPTIONAL {{ ?wp schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?enwiki . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
}} GROUP BY ?item ?itemLabel ?desc ?lat ?lon ?links ORDER BY DESC(?links) LIMIT {limit}"""
    data = http.get_json(SPARQL_URL, {"query": query, "format": "json"}, what="Wikidata query service")
    out: list[Place] = []
    seen: set[str] = set()
    for b in (data.get("results") or {}).get("bindings", []):
        qid = wikidata_qid(b["item"]["value"].rsplit("/", 1)[-1])
        name = b.get("itemLabel", {}).get("value", "")
        if not qid or qid in seen or not name or name == qid:
            continue
        seen.add(qid)
        types = b.get("types", {}).get("value", "")
        cls = _classify(types.split("|"))
        if cls is None:
            continue
        tags, minutes = cls
        labels = types.lower()
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
            external_ids={"wikidata": qid} | ({"enwiki": article} if (article := wiki_title(b)) else {}),
            prominence=int(b["links"]["value"]), source=DataSource.WIKIDATA,
            image=b.get("image", {}).get("value"),
        ))
    return out


def wiki_title(binding: dict) -> str | None:
    """The English Wikipedia article title from a SPARQL binding, or None when it is missing or odd."""
    title = (binding.get("article") or {}).get("value", "").strip()
    return title if 0 < len(title) <= 250 and not re.search(r"[\x00-\x1f\x7f|#<>\[\]{}]", title) else None


def add_wikipedia_readers(http: OpenHttp, places: list[Place]) -> int:
    """Sets `readers` (people who read the place's English Wikipedia article in the last READER_DAYS days) on the
    places that have an article, asking about up to 50 articles per call. Returns how many got a count. A day
    Wikipedia has no figure for counts as nothing, so a count is never made up."""
    by_title: dict[str, list[Place]] = {}
    for p in places:
        title = p.external_ids.get("enwiki")
        if title:
            by_title.setdefault(title, []).append(p)
    titles = list(by_title)
    batches = [titles[i:i + _TITLES_PER_CALL] for i in range(0, len(titles), _TITLES_PER_CALL)]
    # a few batches at once: a big city has a hundred or more articles, and this runs while the city first loads
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="wiki-views") as pool:
        answers = list(pool.map(lambda batch: _page_views(http, batch, set(by_title)), batches))
    counted = 0
    for views in answers:
        for title, total in views.items():
            for p in by_title.get(title, []):
                p.readers = total
                counted += 1
    return counted


def _page_views(http: OpenHttp, batch: list[str], asked: set[str]) -> dict[str, int]:
    """Readers in the last READER_DAYS days for up to 50 article titles, keyed by the title as asked."""
    params = {"action": "query", "prop": "pageviews", "titles": "|".join(batch), "pvipdays": READER_DAYS,
              "redirects": 1, "format": "json", "formatversion": 2}
    views: dict[str, int] = {}
    for _ in range(4):   # the API may answer a large batch in parts
        data = http.get_json(WIKIPEDIA_API, params, what="Wikipedia page views")
        query = data.get("query") or {}
        # a title that was normalised or redirected is reported under its new name: map it back to ours
        renamed = {r.get("to"): r.get("from") for key in ("redirects", "normalized") for r in query.get(key) or []}
        for page in query.get("pages") or []:
            daily = page.get("pageviews")
            if not isinstance(daily, dict) or not daily:
                continue
            title = page.get("title", "")
            while title in renamed and title not in asked:
                title = renamed.pop(title)
            views[title] = views.get(title, 0) + sum(v for v in daily.values() if isinstance(v, int) and v > 0)
        more = data.get("continue")
        if not more:
            break
        params = params | {k: v for k, v in more.items() if isinstance(v, (str, int))}
    return views


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
        key = fold(term)
        if not (1 <= len(term.split()) <= 4) or any(ch.isdigit() for ch in term) or key in _STOP_WORDS \
                or key in _NOT_DISHES:
            continue
        if bold and term[:1].isupper():
            continue  # bold Title Case = usually a venue or district
        sentence = _sentence(text, term)
        if not sentence or not _FOOD_WORDS.search(sentence):
            continue
        found.setdefault(key, sentence)
    # collapse plural/alias spellings onto one name ("pasteis de nata" -> "pastel de nata")
    out: dict[str, str] = {}
    for k, v in found.items():
        if v:
            out.setdefault(DISH_ALIASES.get(k, k), v)
    return list(out.items())[:12]


DISH_ALIASES = {"pasteis de nata": "pastel de nata", "pasteis de belem": "pastel de nata", "momos": "momo",
                "dumpling": "dumplings", "crepes": "crepe", "churro": "churros"}


@dataclass(frozen=True)
class GuidePick:
    """A sight listed under "See" in a Wikivoyage city guide."""
    name: str
    qid: str | None = None
    lat: float | None = None
    lng: float | None = None


_LISTING = re.compile(r"\{\{\s*(see|listing|marker)\s*\|", re.I)


def _template_body(text: str, start: int) -> str:
    """The text of the template opening at `start` ("{{"), up to its matching "}}"."""
    depth, i = 0, start
    while i < len(text) - 1:
        pair = text[i:i + 2]
        if pair == "{{":
            depth, i = depth + 1, i + 2
            continue
        if pair == "}}":
            depth, i = depth - 1, i + 2
            if depth == 0:
                return text[start + 2:i - 2]
            continue
        i += 1
    return text[start + 2:]


def _number(value: str | None, limit: float) -> float | None:
    try:
        v = float(value or "")
    except ValueError:
        return None
    return v if math.isfinite(v) and abs(v) <= limit else None


def extract_see_listings(wikitext: str) -> list[GuidePick]:
    """Sights from {{see|...}} listings (and {{listing|type=see|...}}) in a See section: name, Wikidata id and
    coordinates when the guide gives them."""
    picks: list[GuidePick] = []
    for m in _LISTING.finditer(wikitext):
        body = _template_body(wikitext, m.start())
        fields: dict[str, str] = {}
        for part in body.split("|")[1:]:
            key, eq, value = part.partition("=")
            if eq:
                fields[key.strip().lower()] = _strip_templates(value).strip()
        kind = m.group(1).lower()
        if kind != "see" and fields.get("type", "").lower() != "see":
            continue
        name = re.sub(r"'{2,}|\s+", " ", fields.get("name", "")).strip()
        if not (2 <= len(name) <= 120):
            continue
        picks.append(GuidePick(name=name, qid=wikidata_qid(fields.get("wikidata")),
                               lat=_number(fields.get("lat"), 90), lng=_number(fields.get("long") or fields.get("lon"),
                                                                                180)))
    return picks


def _section_wikitext(http: OpenHttp, title: str, sections: list[dict], names: tuple[str, ...]) -> str | None:
    index = next((s["index"] for s in sections if s.get("line", "").strip().lower() in names
                  and s.get("toclevel") == 1), None)
    if index is None:
        return None
    body = http.get_json(WIKIVOYAGE_API, {"action": "parse", "page": title, "section": index, "prop": "wikitext",
                                          "format": "json"}, what="Wikivoyage")
    return ((body.get("parse") or {}).get("wikitext") or {}).get("*", "")


def wikivoyage_guide(http: OpenHttp, city_name: str, lexicon: set[str]
                     ) -> tuple[list[DishSuggestion], str | None, list[GuidePick]]:
    """Dish suggestions from the city guide's Eat section, the page title used (for attribution) and the sights
    its See section lists."""
    q = http.get_json(WIKIVOYAGE_API, {"action": "query", "titles": city_name, "redirects": 1, "format": "json"},
                      what="Wikivoyage")
    pages = (q.get("query") or {}).get("pages") or {}
    page = next(iter(pages.values()), {})
    if not page or "missing" in page:
        return [], None, []
    title = page["title"]
    secs = http.get_json(WIKIVOYAGE_API, {"action": "parse", "page": title, "prop": "sections", "format": "json"},
                         what="Wikivoyage")
    sections = (secs.get("parse") or {}).get("sections", [])
    eat = _section_wikitext(http, title, sections, _EAT_TITLES)
    dishes = [DishSuggestion(name=name.title(), status="guide", evidence=[f'Wikivoyage ({title}): "{ev}"'],
                             evidence_source=DataSource.WIKIVOYAGE, mention_count=1)
              for name, ev in extract_dishes(eat or "", lexicon)]
    see = _section_wikitext(http, title, sections, ("see",))
    return dishes, title, extract_see_listings(see or "")
