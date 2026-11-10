"""Google Places API (New) provider.

Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
Ratings returned here are real Google ratings (verified=True). Fields Google does
not provide (entry fees, Jain/vegan menus) are left empty or marked unknown;
they are never invented here.
"""
from __future__ import annotations

import logging
import re

from app.core.errors import NotFoundError
from app.providers.base import CityContext, PlaceQuery
from app.providers.google.client import GoogleClient
from app.schemas.common import DataSource, LatLng, Money
from app.schemas.place import DietInfo, ExternalRating, OpeningHours, Place, PlaceKind, Review, TimeRange

log = logging.getLogger(__name__)
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{id}"

_FIELDS = [
    "id", "displayName", "formattedAddress", "location", "rating", "userRatingCount", "priceLevel",
    "priceRange", "types", "primaryType", "regularOpeningHours", "googleMapsUri", "editorialSummary",
    "reviews", "servesVegetarianFood", "servesBreakfast", "servesLunch", "servesDinner", "servesCoffee",
]
SEARCH_MASK = ",".join(f"places.{f}" for f in _FIELDS)
DETAILS_MASK = ",".join(_FIELDS)

PRICE_LEVELS = {
    "PRICE_LEVEL_FREE": 0, "PRICE_LEVEL_INEXPENSIVE": 1, "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3, "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}

# Google place types -> our interest tags
TYPE_TAGS: dict[str, list[str]] = {
    "museum": ["museums", "history"], "art_gallery": ["art", "museums"], "art_museum": ["art", "museums"],
    "history_museum": ["museums", "history"], "historical_landmark": ["monuments", "history"],
    "historical_place": ["monuments", "history"], "monument": ["monuments", "history"],
    "castle": ["monuments", "architecture", "history"], "palace": ["monuments", "architecture"],
    "fort": ["monuments", "history"], "tourist_attraction": [], "cultural_landmark": ["cultural_centres"],
    "cultural_center": ["cultural_centres"], "performing_arts_theater": ["cultural_centres", "art"],
    "park": ["parks", "nature"], "national_park": ["nature", "wildlife"], "botanical_garden": ["parks", "nature"],
    "garden": ["parks", "nature"], "hiking_area": ["nature", "adventure"], "zoo": ["wildlife"],
    "wildlife_park": ["wildlife", "nature"], "amusement_park": ["adventure"], "adventure_sports_center": ["adventure"],
    "shopping_mall": ["shopping"], "market": ["markets", "shopping"], "store": ["shopping"],
    "hindu_temple": ["religious_sites", "architecture"], "church": ["religious_sites", "architecture"],
    "mosque": ["religious_sites", "architecture"], "synagogue": ["religious_sites"], "place_of_worship": ["religious_sites"],
    "night_club": ["nightlife"], "bar": ["nightlife"], "observation_deck": ["photography"], "plaza": ["architecture"],
}
PARK_TYPES = {"park", "national_park", "botanical_garden", "garden", "hiking_area", "dog_park"}
CAFE_TYPES = {"cafe", "coffee_shop", "tea_house", "bakery", "dessert_shop"}
NONVEG_TYPES = {"steak_house", "seafood_restaurant", "barbecue_restaurant", "hamburger_restaurant", "chicken_restaurant"}
VEG_TYPES = {"vegetarian_restaurant", "vegan_restaurant"}
VISIT_MINUTES = {"museum": 90, "art_gallery": 60, "park": 45, "shopping_mall": 90, "market": 60,
                 "hindu_temple": 40, "church": 30, "mosque": 30, "zoo": 120, "amusement_park": 180, "castle": 120}


def _hours(raw: dict | None) -> OpeningHours:
    if not raw or "periods" not in raw:
        return OpeningHours(known=False, weekly={}, source=DataSource.GOOGLE)
    weekly: dict[int, list[TimeRange]] = {d: [] for d in range(7)}
    for p in raw["periods"]:
        o = p.get("open")
        c = p.get("close")
        if o is None:
            continue
        if c is None:  # open 24 hours
            for d in range(7):
                weekly[d] = [TimeRange(open="00:00", close="24:00")]
            break
        od = (o["day"] + 6) % 7  # Google: 0=Sunday -> ours: 0=Monday
        cd = (c["day"] + 6) % 7
        ot = f"{o.get('hour', 0):02d}:{o.get('minute', 0):02d}"
        ct = f"{c.get('hour', 0):02d}:{c.get('minute', 0):02d}"
        if od == cd and ct > ot:
            weekly[od].append(TimeRange(open=ot, close=ct))
        else:  # crosses midnight
            weekly[od].append(TimeRange(open=ot, close="24:00"))
            if ct != "00:00":
                weekly[cd].append(TimeRange(open="00:00", close=ct))
    return OpeningHours(known=True, weekly=weekly, source=DataSource.GOOGLE)


def _price_range(raw: dict | None) -> Money | None:
    if not raw or "startPrice" not in raw:
        return None
    start = raw["startPrice"]
    lo = float(start.get("units", 0)) + start.get("nanos", 0) / 1e9
    end = raw.get("endPrice")
    hi = float(end.get("units", 0)) + end.get("nanos", 0) / 1e9 if end else lo
    return Money(amount=round((lo + hi) / 2, 2), currency=start.get("currencyCode", ""), verified=False,
                 source=DataSource.GOOGLE, note=f"Midpoint of Google-reported price range {lo:g}-{hi:g} per person")


def _diet(p: dict, reviews: list[Review]) -> DietInfo:
    types = set(p.get("types", []))
    text = " ".join(r.text.lower() for r in reviews)
    veg_only = bool(types & VEG_TYPES)
    serves_veg = p.get("servesVegetarianFood")
    return DietInfo(
        vegetarian_only=veg_only,
        vegetarian_options=bool(serves_veg) or veg_only,
        vegan_options="vegan_restaurant" in types or bool(re.search(r"\bvegan\b", text)),
        jain_options=bool(re.search(r"\bjain\b", text)),
        egg_options=bool(re.search(r"\begg", text)),
        non_veg=bool(types & NONVEG_TYPES) or bool(re.search(r"\b(chicken|mutton|fish|lamb|beef|pork|kebab)", text)),
        known=serves_veg is not None or veg_only,
        source=DataSource.GOOGLE,
    )


def to_place(p: dict, tag: str | None = None, kind_hint: str | None = None) -> Place:
    types = p.get("types", [])
    primary = p.get("primaryType")
    tags: list[str] = []
    for t in types:
        for tg in TYPE_TAGS.get(t, []):
            if tg not in tags:
                tags.append(tg)
    if tag and tag not in ("famous", "all", "restaurants") and tag not in tags:
        tags.append(tag)

    is_food = kind_hint == "food" or "restaurant" in (primary or "") or bool(set(types) & CAFE_TYPES)
    if is_food:
        kind = PlaceKind.CAFE if set(types) & CAFE_TYPES else PlaceKind.RESTAURANT
    elif set(types) & PARK_TYPES:
        kind = PlaceKind.PARK
    else:
        kind = PlaceKind.ATTRACTION

    reviews = [Review(text=(r.get("text") or {}).get("text", ""), rating=r.get("rating"), source=DataSource.GOOGLE)
               for r in p.get("reviews", []) if (r.get("text") or {}).get("text")]
    rating = p.get("rating")
    count = p.get("userRatingCount")
    ext = ExternalRating(provider=DataSource.GOOGLE, rating=rating, review_count=count, verified=rating is not None,
                         label="Google rating" if rating is not None else "No Google rating available")
    price_level = PRICE_LEVELS.get(p.get("priceLevel", ""), None)

    food_cats: list[str] = []
    meals: list[str] = []
    if is_food:
        if kind == PlaceKind.CAFE:
            food_cats.append("cafes")
        if price_level is not None and price_level <= 1:
            food_cats.append("budget_restaurants")
        if price_level is not None and price_level >= 3:
            food_cats.append("fine_dining")
        if tag in ("street_food", "local_cuisine") and tag not in food_cats:
            food_cats.append(tag)
        for key, meal in (("servesBreakfast", "breakfast"), ("servesLunch", "lunch"), ("servesDinner", "dinner")):
            if p.get(key):
                meals.append(meal)
        if not meals:
            meals = ["lunch", "dinner"] if kind == PlaceKind.RESTAURANT else ["breakfast", "lunch"]

    return Place(
        id=f"g:{p['id']}", name=(p.get("displayName") or {}).get("text", "Unnamed place"), kind=kind,
        # "search:<tag>" records which Google query returned the place (weak evidence for diet fit)
        categories=(["food"] + food_cats + ([f"search:{tag}"] if tag else [])) if is_food else tags,
        location=LatLng(lat=p["location"]["latitude"], lng=p["location"]["longitude"]),
        address=p.get("formattedAddress"), description=(p.get("editorialSummary") or {}).get("text"),
        external_rating=ext, price_level=price_level,
        entry_fee=None,  # Google does not publish entry fees; the budget engine estimates and labels them
        avg_cost_per_person=_price_range(p.get("priceRange")) if is_food else None,
        typical_visit_minutes=VISIT_MINUTES.get(primary or "", 60 if not is_food else 60),
        opening_hours=_hours(p.get("regularOpeningHours")),
        is_famous=tag == "famous" and (count or 0) >= 5000,
        best_time=meals if is_food else [],
        diet=_diet(p, reviews) if is_food else None,
        food_categories=food_cats, cuisines=[t.replace("_restaurant", "") for t in types if t.endswith("_restaurant")],
        reviews=reviews, google_maps_uri=p.get("googleMapsUri"), source=DataSource.GOOGLE,
    )


class GooglePlacesProvider:
    source = DataSource.GOOGLE

    def __init__(self, client: GoogleClient):
        self._c = client

    def search(self, city: CityContext, query: PlaceQuery) -> list[Place]:
        body = {
            "textQuery": query.text,
            "maxResultCount": min(query.max_results, 20),
            "locationBias": {"circle": {"center": {"latitude": city.center.lat, "longitude": city.center.lng},
                                        "radius": min(city.radius_km * 1000, 50000.0)}},
        }
        data = self._c.post(SEARCH_URL, body, SEARCH_MASK)
        places = []
        for raw in data.get("places", []):
            try:
                places.append(to_place(raw, tag=query.tag, kind_hint=query.kind))
            except (KeyError, ValueError) as exc:
                log.warning("Skipping malformed Google place %s: %s", raw.get("id"), exc)
        log.info("Google Places '%s' -> %d results", query.text, len(places))
        return places

    def get_place(self, place_id: str) -> Place:
        gid = place_id.removeprefix("g:")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,300}", gid):   # becomes part of the URL path
            raise NotFoundError(f"Place '{place_id}' not found")
        raw = self._c.get(DETAILS_URL.format(id=gid), {}, field_mask=DETAILS_MASK)
        return to_place(raw)
