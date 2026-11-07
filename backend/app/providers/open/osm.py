"""OpenStreetMap (Overpass) query building and tag parsing.

Data (c) OpenStreetMap contributors, ODbL 1.0. Only tags that exist in OSM are
used; missing information (hours, fees, diet) stays unknown.
"""
from __future__ import annotations

import re

from app.schemas.common import DataSource, LatLng, Money
from app.schemas.place import DietInfo, OpeningHours, Place, PlaceKind, TimeRange

SRC = DataSource.OSM

ATTRACTION_FILTERS = [
    'nwr["tourism"~"^(museum|gallery|attraction|viewpoint|zoo|aquarium|theme_park)$"]["name"]',
    'nwr["tourism"="artwork"]["name"]["wikidata"]',
    'nwr["historic"~"^(castle|fort|monument|memorial|ruins|archaeological_site|palace|city_gate|tower|manor|monastery|citywalls)$"]["name"]',
    'nwr["leisure"~"^(park|garden|nature_reserve)$"]["name"]',
    'nwr["amenity"="place_of_worship"]["name"]["wikidata"]',
    'nwr["amenity"~"^(marketplace|arts_centre|theatre)$"]["name"]',
    'nwr["shop"="mall"]["name"]',
    'nwr["natural"="beach"]["name"]',
]
FOOD_FILTER = 'nwr["amenity"~"^(restaurant|cafe|fast_food|food_court|ice_cream)$"]["name"]'
STATION_FILTERS = ['node["railway"="station"]', 'node["station"~"^(subway|light_rail|monorail)$"]']


def _bbox(lat: float, lng: float, radius_km: float) -> str:
    import math

    dlat = radius_km / 111.0
    dlng = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return f"{lat - dlat:.5f},{lng - dlng:.5f},{lat + dlat:.5f},{lng + dlng:.5f}"


def build_queries(lat: float, lng: float, radius_km: float, food_radius_km: float) -> dict[str, str]:
    """Three small bbox queries (bbox filters are much cheaper than `around` on public servers)."""
    head = "[out:json][timeout:55][bbox:{bb}];"
    big, small = _bbox(lat, lng, radius_km), _bbox(lat, lng, food_radius_km)
    return {
        "attractions": head.format(bb=big) + "(" + "".join(f"{f};" for f in ATTRACTION_FILTERS) + ");out center tags qt 3000;",
        "food": head.format(bb=small) + f"{FOOD_FILTER};out center tags qt 3000;",
        "stations": head.format(bb=big) + "(" + "".join(f"{f};" for f in STATION_FILTERS) + ");out tags qt 1500;",
    }


# --------------------------------------------------------------------------- hours
_DAYS = {"mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6}
_DAY_TOKEN = re.compile(r"^(mo|tu|we|th|fr|sa|su)(-(mo|tu|we|th|fr|sa|su))?$")
_TIME_RANGE = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\+?$")


def _day_set(spec: str) -> set[int] | None:
    days: set[int] = set()
    for tok in spec.split(","):
        tok = tok.strip().lower()
        if tok in ("ph", "sh"):
            continue
        m = _DAY_TOKEN.match(tok)
        if not m:
            return None
        a = _DAYS[m.group(1)]
        b = _DAYS[m.group(3)] if m.group(3) else a
        d = a
        while True:
            days.add(d)
            if d == b:
                break
            d = (d + 1) % 7
    return days


def _hm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _time_ranges(spec: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]] | None:
    """Returns (ranges on the same day, ranges spilling past midnight into the next day)."""
    same: list[tuple[str, str]] = []
    spill: list[tuple[str, str]] = []
    for tok in spec.split(","):
        m = _TIME_RANGE.match(tok.strip())
        if not m:
            return None
        h1, m1, h2, m2 = (int(x) for x in m.groups())
        start, end = h1 * 60 + m1, h2 * 60 + m2
        if end == 0 or end == 24 * 60:
            same.append((_hm(start), "24:00"))
        elif end <= start or end > 24 * 60:      # e.g. 18:00-02:00 or 18:00-26:00
            same.append((_hm(start), "24:00"))
            spill.append(("00:00", _hm(end % (24 * 60))))
        else:
            same.append((_hm(start), _hm(end)))
    return same, spill


def parse_opening_hours(value: str | None) -> OpeningHours:
    """Parse the common subset of OSM opening_hours. Anything else -> known=False."""
    if not value:
        return OpeningHours(known=False, weekly={}, source=SRC)
    v = value.strip()
    if v == "24/7":
        return OpeningHours(known=True, weekly={d: [TimeRange(open="00:00", close="24:00")] for d in range(7)}, source=SRC)
    # split rules on ';' or '||', and on ', ' between a time and a new weekday ("... 18:00, Sa 10:00-14:00")
    rules = re.split(r"\s*(?:;|\|\|)\s*|(?<=\d),\s*(?=(?:Mo|Tu|We|Th|Fr|Sa|Su)\b)", v)
    weekly: dict[int, list[TimeRange]] = {}
    overflow: dict[int, list[TimeRange]] = {}
    for rule in filter(None, (r.strip() for r in rules)):
        parts = rule.split(None, 1)
        days: set[int] | None
        if _day_set(parts[0]) is not None and re.match(r"^[A-Za-z]", parts[0]):
            days = _day_set(parts[0])
            rest = parts[1].strip() if len(parts) > 1 else ""
        else:
            days, rest = set(range(7)), rule
        if days is None:
            return OpeningHours(known=False, weekly={}, source=SRC)
        if rest.lower() in ("off", "closed"):
            for d in days:
                weekly[d] = []
            continue
        if rest == "" or rest == "24/7":
            parsed = ([("00:00", "24:00")], [])
        else:
            parsed = _time_ranges(rest)
            if parsed is None:  # seasons, sunrise, week numbers... not supported -> unknown
                return OpeningHours(known=False, weekly={}, source=SRC)
        same, spill = parsed
        for d in days:
            weekly[d] = [TimeRange(open=o, close=c) for o, c in same]  # later rules override earlier ones
            for o, c in spill:
                overflow.setdefault((d + 1) % 7, []).append(TimeRange(open=o, close=c))
    for d, extra in overflow.items():
        weekly.setdefault(d, [])
        weekly[d] = sorted(weekly[d] + extra, key=lambda r: r.open)
    return OpeningHours(known=True, weekly=weekly, source=SRC)


# ----------------------------------------------------------------------------- fees
_SYMBOLS = {"€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY", "$": "USD", "฿": "THB",
            "₺": "TRY", "₩": "KRW", "r$": "BRL", "kc": "CZK", "zł": "PLN"}
_CHARGE = re.compile(r"(?P<cur1>[A-Z]{3}|[€£₹¥$฿₺₩])?\s*(?P<num>\d+(?:[.,]\d+)?)\s*(?P<cur2>[A-Z]{3}|[€£₹¥$฿₺₩])?")
USUALLY_FREE = {("tourism", "viewpoint"), ("tourism", "artwork"), ("historic", "monument"), ("historic", "memorial"),
                ("amenity", "place_of_worship"), ("amenity", "marketplace"), ("shop", "mall"), ("natural", "beach")}


def parse_fee(tags: dict[str, str]) -> Money | None:
    fee = tags.get("fee", "").lower()
    if fee == "no":
        return Money(amount=0, currency="USD", verified=False, source=SRC, note="Free entry (OpenStreetMap fee=no)")
    charge = tags.get("charge")
    if charge:
        m = _CHARGE.search(charge)
        cur = (m.group("cur1") or m.group("cur2")) if m else None
        if m and cur:
            code = _SYMBOLS.get(cur, cur)
            return Money(amount=float(m.group("num").replace(",", ".")), currency=code, verified=False, source=SRC,
                         note=f"From OpenStreetMap charge tag '{charge}' - may be out of date")
    if not fee and any(tags.get(k) == v for k, v in USUALLY_FREE):
        return Money(amount=0, currency="USD", verified=False, source=DataSource.ESTIMATE,
                     note="Usually free for this type of place (no fee recorded in OpenStreetMap)")
    return None


# ------------------------------------------------------------------------ categories
def interest_tags(tags: dict[str, str]) -> list[str]:
    t = tags
    out: list[str] = []

    def add(*xs: str) -> None:
        for x in xs:
            if x not in out:
                out.append(x)

    tourism, historic, leisure, amenity = t.get("tourism"), t.get("historic"), t.get("leisure"), t.get("amenity")
    if tourism == "museum":
        add("museums", "history")
        kind = t.get("museum", "")
        if kind in ("art",):
            add("art")
    if tourism == "gallery":
        add("art", "museums")
    if tourism == "artwork":
        add("art", "photography")
    if tourism == "viewpoint":
        add("photography", "nature")
    if tourism in ("zoo", "aquarium"):
        add("wildlife")
    if tourism == "theme_park":
        add("adventure")
    if historic in ("castle", "fort", "palace", "manor", "citywalls", "city_gate", "tower"):
        add("monuments", "history", "architecture")
    if historic in ("monument", "memorial"):
        add("monuments", "history")
    if historic in ("ruins", "archaeological_site"):
        add("history", "monuments")
    if historic == "monastery":
        add("religious_sites", "history", "architecture")
    if amenity == "place_of_worship":
        add("religious_sites", "architecture")
    if leisure in ("park", "garden"):
        add("parks", "nature")
    if leisure == "nature_reserve":
        add("nature", "wildlife")
    if amenity == "marketplace":
        add("markets", "shopping")
    if t.get("shop") == "mall":
        add("shopping")
    if amenity in ("arts_centre", "theatre"):
        add("cultural_centres", "art")
    if t.get("natural") == "beach":
        add("nature", "adventure")
    if tourism == "attraction" and not out:
        add("photography")
    if t.get("building") in ("cathedral", "church", "temple", "mosque") or t.get("heritage"):
        add("architecture")
    return out


VISIT_MIN = [
    (("tourism", "museum"), 90), (("tourism", "gallery"), 60), (("tourism", "zoo"), 150), (("tourism", "aquarium"), 120),
    (("tourism", "theme_park"), 240), (("historic", "castle"), 120), (("historic", "fort"), 90), (("historic", "palace"), 90),
    (("historic", "archaeological_site"), 75), (("historic", "ruins"), 45), (("historic", "monastery"), 60),
    (("leisure", "nature_reserve"), 90), (("leisure", "park"), 45), (("leisure", "garden"), 45),
    (("natural", "beach"), 120), (("amenity", "marketplace"), 60), (("shop", "mall"), 90),
    (("amenity", "theatre"), 60), (("amenity", "arts_centre"), 60), (("amenity", "place_of_worship"), 35),
    (("tourism", "viewpoint"), 30), (("tourism", "artwork"), 20), (("historic", "monument"), 25),
    (("historic", "memorial"), 20),
]

NONVEG_CUISINE = {"steak_house", "burger", "chicken", "seafood", "fish", "kebab", "bbq", "barbecue", "fish_and_chips",
                  "wings", "sausage", "korean_bbq", "churrascaria"}
STREET_CUISINE = {"street_food", "kebab", "sandwich", "hot_dog", "crepe", "taco", "noodle", "dumpling"}


def _cuisines(tags: dict[str, str]) -> list[str]:
    return [c.strip().lower() for c in tags.get("cuisine", "").replace(",", ";").split(";") if c.strip()]


def diet_from_tags(tags: dict[str, str], cuisines: list[str]) -> DietInfo:
    def flag(key: str) -> str:
        return tags.get(f"diet:{key}", "").lower()

    veg, vegan, jain = flag("vegetarian"), flag("vegan"), flag("jain")
    known = bool(veg or vegan or jain) or "vegetarian" in cuisines or "vegan" in cuisines
    return DietInfo(
        vegetarian_only=veg == "only" or vegan == "only" or cuisines == ["vegetarian"] or cuisines == ["vegan"],
        vegetarian_options=veg in ("yes", "only", "limited") or vegan in ("yes", "only") or "vegetarian" in cuisines,
        vegan_options=vegan in ("yes", "only", "limited") or "vegan" in cuisines,
        jain_options=jain in ("yes", "only"),
        egg_options=False,
        non_veg=bool(set(cuisines) & NONVEG_CUISINE) or veg == "no",
        known=known,
        source=SRC,
    )


def _name(tags: dict[str, str]) -> str:
    en, local = tags.get("name:en"), tags.get("name", "")
    return f"{en} ({local})" if en and local and en != local and len(local) < 40 else (en or local)


def _address(tags: dict[str, str]) -> str | None:
    parts = [" ".join(p for p in (tags.get("addr:housenumber"), tags.get("addr:street")) if p),
             tags.get("addr:city")]
    s = ", ".join(p for p in parts if p)
    return s or None


def element_to_place(el: dict, local_cuisines: set[str]) -> Place | None:
    tags = el.get("tags") or {}
    name = _name(tags)
    lat = el.get("lat", (el.get("center") or {}).get("lat"))
    lon = el.get("lon", (el.get("center") or {}).get("lon"))
    if not name or lat is None or lon is None:
        return None
    osm_id = f"{el['type'][0]}{el['id']}"
    ext = {"osm": osm_id}
    if tags.get("wikidata", "").startswith("Q"):
        ext["wikidata"] = tags["wikidata"].split(";")[0]
    amenity = tags.get("amenity")
    hours = parse_opening_hours(tags.get("opening_hours"))
    website = tags.get("website") or tags.get("contact:website")

    if amenity in ("restaurant", "cafe", "fast_food", "food_court", "ice_cream"):
        cuisines = _cuisines(tags)
        cats: list[str] = []
        if amenity in ("cafe", "ice_cream"):
            cats.append("cafes")
        if amenity in ("fast_food", "food_court") or set(cuisines) & STREET_CUISINE:
            cats += ["street_food", "budget_restaurants"]
        if amenity == "restaurant" and (set(cuisines) & local_cuisines or "regional" in cuisines or "local" in cuisines):
            cats.append("local_cuisine")
        level = {"cafe": 1, "ice_cream": 1, "fast_food": 1, "food_court": 1}.get(amenity, 2)
        meals = ["breakfast", "lunch"] if amenity == "cafe" else ["lunch", "dinner"]
        if amenity == "fast_food":
            meals = ["lunch", "dinner"]
        if hours.known and any(r.open <= "08:30" for rs in hours.weekly.values() for r in rs) and amenity != "cafe":
            meals = ["breakfast"] + meals
        return Place(
            id=f"osm:{osm_id}", name=name, kind=PlaceKind.CAFE if amenity in ("cafe", "ice_cream") else PlaceKind.RESTAURANT,
            categories=["food"] + cats, location=LatLng(lat=lat, lng=lon), address=_address(tags),
            description=(website or None), price_level=level, price_level_estimated=True,
            typical_visit_minutes=60, opening_hours=hours, best_time=meals,
            diet=diet_from_tags(tags, cuisines), food_categories=cats, cuisines=cuisines,
            external_ids=ext, source=SRC,
        )

    cats = interest_tags(tags)
    if not cats:
        return None
    # skip generic small items unless notable
    if tags.get("tourism") == "attraction" and not (ext.get("wikidata") or tags.get("wikipedia") or tags.get("historic")):
        return None
    if tags.get("historic") in ("memorial", "monument") and not ext.get("wikidata"):
        return None
    visit = next((m for (k, v), m in VISIT_MIN if tags.get(k) == v), 60)
    kind = PlaceKind.PARK if tags.get("leisure") in ("park", "garden", "nature_reserve") else PlaceKind.ATTRACTION
    best = ["evening"] if tags.get("tourism") == "viewpoint" else (
        ["morning", "afternoon"] if kind == PlaceKind.PARK else [])
    return Place(
        id=f"osm:{osm_id}", name=name, kind=kind, categories=cats, location=LatLng(lat=lat, lng=lon),
        address=_address(tags), description=tags.get("description") or (website or None),
        entry_fee=parse_fee(tags), typical_visit_minutes=visit, opening_hours=hours, best_time=best,
        external_ids=ext, source=SRC,
    )


def parse_elements(elements: list[dict], local_cuisines: set[str]) -> tuple[list[Place], list[dict]]:
    places: dict[str, Place] = {}
    stations: list[dict] = []
    for el in elements:
        tags = el.get("tags") or {}
        if tags.get("railway") == "station" or tags.get("station") in ("subway", "light_rail", "monorail"):
            if el.get("lat") is None:
                continue
            kind = "metro" if (tags.get("station") in ("subway", "light_rail", "monorail") or tags.get("subway") == "yes"
                               or tags.get("light_rail") == "yes") else "train"
            stations.append({"name": tags.get("name", "station"), "lat": el["lat"], "lng": el["lon"], "kind": kind})
            continue
        p = element_to_place(el, local_cuisines)
        if p and p.id not in places:
            places[p.id] = p
    return list(places.values()), stations


# cuisine tags that count as "local cuisine" for a country (OSM cuisine values)
LOCAL_CUISINES: dict[str, set[str]] = {
    "IN": {"indian", "north_indian", "south_indian", "rajasthani", "punjabi", "gujarati", "bengali", "kerala", "thali",
           "biryani", "regional"},
    "PT": {"portuguese"}, "ES": {"spanish", "tapas", "catalan", "basque"}, "IT": {"italian", "pizza", "pasta"},
    "FR": {"french", "crepe", "bistro"}, "DE": {"german", "bavarian"}, "GB": {"british", "fish_and_chips", "english"},
    "JP": {"japanese", "sushi", "ramen", "udon", "izakaya"}, "CN": {"chinese", "cantonese", "sichuan", "dim_sum"},
    "TH": {"thai"}, "VN": {"vietnamese", "pho"}, "KR": {"korean", "korean_bbq"}, "MX": {"mexican", "taco"},
    "TR": {"turkish", "kebab"}, "GR": {"greek"}, "US": {"american", "burger", "bbq", "diner"},
    "LB": {"lebanese"}, "MA": {"moroccan"}, "ID": {"indonesian"}, "MY": {"malaysian"}, "SG": {"singaporean", "hawker"},
    "PE": {"peruvian"}, "BR": {"brazilian", "churrascaria"}, "AR": {"argentinian"}, "ET": {"ethiopian"},
    "NL": {"dutch"}, "BE": {"belgian"}, "AT": {"austrian"}, "CZ": {"czech"}, "HU": {"hungarian"}, "PL": {"polish"},
    "RU": {"russian"}, "EG": {"egyptian"}, "IL": {"israeli"}, "AU": {"australian"}, "PH": {"filipino"},
    "LK": {"sri_lankan"}, "NP": {"nepalese", "nepali"}, "PK": {"pakistani"}, "BD": {"bangladeshi"},
}
