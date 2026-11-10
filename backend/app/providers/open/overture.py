"""Overture Maps places read straight from the public parquet release (DuckDB over S3).

Overture Places: CDLA-Permissive-2.0, some records from Foursquare (Apache-2.0).
This is the primary worldwide source for restaurants, cafes, museums, parks,
historic sites and stations in open mode. Overture has no ratings, opening
hours or fees; those stay unknown unless OSM or Google supply them.
"""
from __future__ import annotations

import logging
import math
import re
import threading

import httpx

from app.core.urls import safe_http_url
from app.schemas.common import DataSource, LatLng, Money
from app.schemas.place import DietInfo, OpeningHours, Place, PlaceKind

log = logging.getLogger(__name__)
STAC_CATALOG = "https://stac.overturemaps.org/catalog.json"
S3_PATH = "s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"
SRC = DataSource.OVERTURE

FOOD = {"restaurant", "cafe", "coffee_shop", "fast_food_restaurant", "bakery", "food_court", "food_truck",
        "ice_cream_shop", "tea_room", "dessert_shop", "street_food"}
CAFE = {"cafe", "coffee_shop", "tea_room", "bakery", "ice_cream_shop", "dessert_shop"}
STREET = {"fast_food_restaurant", "food_court", "food_truck", "street_food"}
# basic_category -> (interest tags, visit minutes, kind)
ATTRACTIONS: dict[str, tuple[list[str], int, PlaceKind]] = {
    "museum": (["museums", "history"], 90, PlaceKind.ATTRACTION),
    "art_gallery": (["art", "museums"], 45, PlaceKind.ATTRACTION),
    "historic_site": (["history", "monuments", "architecture"], 60, PlaceKind.ATTRACTION),
    "monument": (["monuments", "history"], 25, PlaceKind.ATTRACTION),
    "castle": (["monuments", "history", "architecture"], 120, PlaceKind.ATTRACTION),
    "landmark_and_historical_building": (["architecture", "history"], 45, PlaceKind.ATTRACTION),
    "public_plaza": (["architecture", "photography"], 25, PlaceKind.ATTRACTION),
    "religious_organization": (["religious_sites", "architecture"], 35, PlaceKind.ATTRACTION),
    "theatre_venue": (["cultural_centres", "art"], 60, PlaceKind.ATTRACTION),
    "beach": (["nature", "adventure"], 120, PlaceKind.ATTRACTION),
    "amusement_park": (["adventure"], 180, PlaceKind.ATTRACTION),
    "animal_attraction": (["wildlife"], 120, PlaceKind.ATTRACTION),
    "science_attraction": (["museums"], 90, PlaceKind.ATTRACTION),
    "farmers_market": (["markets", "shopping"], 60, PlaceKind.ATTRACTION),
    "market": (["markets", "shopping"], 60, PlaceKind.ATTRACTION),
    "shopping_center": (["shopping"], 90, PlaceKind.ATTRACTION),
    "park": (["parks", "nature"], 45, PlaceKind.PARK),
    "garden": (["parks", "nature"], 45, PlaceKind.PARK),
    "national_park": (["nature", "wildlife"], 120, PlaceKind.PARK),
}
USUALLY_FREE = {"public_plaza", "monument", "park", "garden", "beach", "market", "farmers_market",
                "shopping_center", "religious_organization"}
STATIONS = {"train_station", "metro_station", "subway_station", "light_rail_station"}
_LATEST: dict[str, str] = {}


# The release name and memory limit are interpolated into the DuckDB SQL text (table-function path and
# SET statement), so both are validated against strict patterns; coordinates are bound parameters
# and the category lists are module constants checked below.
_RELEASE = re.compile(r"^\d{4}-\d{2}-\d{2}(\.\d{1,3})?$")
_MEMORY = re.compile(r"^\d{1,6}(\.\d{1,2})?\s?(KB|MB|GB|KiB|MiB|GiB)$", re.I)
_CATEGORY = re.compile(r"^[a-z_]+$")


def safe_release(release: str) -> str:
    if not isinstance(release, str) or not _RELEASE.match(release):
        raise ValueError(f"unexpected Overture release name {release!r}")
    return release


def safe_memory_limit(value: str) -> str:
    if not isinstance(value, str) or not _MEMORY.match(value.strip()):
        raise ValueError(f"unexpected DUCKDB_MEMORY_LIMIT {value!r}")
    return value.strip()


def latest_release(user_agent: str) -> str:
    if "v" not in _LATEST:
        r = httpx.get(STAC_CATALOG, timeout=20, headers={"User-Agent": user_agent})
        r.raise_for_status()
        data = r.json()
        latest = data.get("latest")
        if not latest:
            titles = [l["href"].rstrip("/").split("/")[-2] for l in data.get("links", []) if l.get("rel") == "child"]
            latest = sorted(titles)[-1]
        _LATEST["v"] = safe_release(latest)   # comes from a remote catalog: never trusted as SQL text
    return _LATEST["v"]


def bbox(lat: float, lng: float, radius_km: float) -> tuple[float, float, float, float]:
    dlat = radius_km / 111.0
    dlng = radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    return lng - dlng, lng + dlng, lat - dlat, lat + dlat


def row_to_place(row: tuple, local_cuisines: set[str]) -> Place | dict | None:
    """Returns a Place, a station dict, or None."""
    pid, local_name, basic, primary, hierarchy, confidence, lng, lat, website, license_, en_name, brand = row
    if not local_name or lat is None:
        return None
    name = f"{en_name} ({local_name})" if en_name and en_name != local_name else local_name
    if basic in STATIONS:
        # Overture files most urban rail stops as train_station; without OSM we cannot tell metro from
        # mainline, so they are kept as generic "rail" stations usable for both (labelled in route notes).
        kind = "rail" if basic == "train_station" else "metro"
        return {"name": name, "lat": lat, "lng": lng, "kind": kind}
    ext = {"overture": pid, **({"license": license_} if license_ else {})}
    if basic in FOOD:
        tax = [t for t in (hierarchy or []) if t] + ([primary] if primary else [])
        cuisines = sorted({t.removesuffix("_restaurant") for t in tax if t.endswith("_restaurant")
                           and t != "fast_food_restaurant"})
        is_cafe = basic in CAFE
        cats: list[str] = []
        if is_cafe:
            cats.append("cafes")
        if basic in STREET:
            cats += ["street_food", "budget_restaurants"]
        if set(cuisines) & local_cuisines:
            cats.append("local_cuisine")
        if brand:
            ext["brand"] = brand
        veg = "vegetarian" in cuisines or "vegan" in cuisines
        return Place(
            id=f"ovt:{pid}", name=name, kind=PlaceKind.CAFE if is_cafe else PlaceKind.RESTAURANT,
            categories=["food"] + cats, location=LatLng(lat=lat, lng=lng), description=safe_http_url(website),
            price_level=1 if is_cafe or basic in STREET else 2, price_level_estimated=True,
            opening_hours=OpeningHours(known=False, weekly={}, source=SRC),
            best_time=["breakfast", "lunch"] if is_cafe else ["lunch", "dinner"],
            diet=DietInfo(vegetarian_only=cuisines in (["vegetarian"], ["vegan"]), vegetarian_options=veg,
                          vegan_options="vegan" in cuisines, known=veg, source=SRC),
            food_categories=cats, cuisines=cuisines, external_ids=ext, source=SRC,
        )
    if basic in ATTRACTIONS:
        tags, minutes, kind = ATTRACTIONS[basic]
        return Place(
            id=f"ovt:{pid}", name=name, kind=kind, categories=list(tags), location=LatLng(lat=lat, lng=lng),
            description=safe_http_url(website), typical_visit_minutes=minutes,
            entry_fee=(Money(amount=0, currency="USD", source=DataSource.ESTIMATE, note="Usually free for this type of place (no fee data) - assumption")
                       if basic in USUALLY_FREE else None),
            opening_hours=OpeningHours(known=False, weekly={}, source=SRC),
            best_time=["morning", "afternoon"] if kind == PlaceKind.PARK else [], external_ids=ext, source=SRC,
        )
    return None


_DB = None
_DB_LOCK = threading.Lock()


def _database(memory_limit: str, threads: int):
    """One in-process DuckDB database for the app's lifetime. Its HTTP metadata and object caches
    make later city loads much faster than opening a fresh connection each time."""
    global _DB
    with _DB_LOCK:
        if _DB is None:
            import duckdb  # optional dependency

            db = duckdb.connect()
            db.execute(f"SET memory_limit='{safe_memory_limit(memory_limit)}'; SET threads={int(threads)};")
            db.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2'; SET enable_progress_bar=false; "
                       "SET enable_http_metadata_cache=true; SET enable_object_cache=true;")
            _DB = db
        return _DB


def fetch(lat: float, lng: float, radius_km: float, food_radius_km: float, release: str,
          local_cuisines: set[str], memory_limit: str = "256MB", threads: int = 2) -> tuple[list[Place], list[dict]]:
    xmin, xmax, ymin, ymax = bbox(lat, lng, radius_km)
    fx0, fx1, fy0, fy1 = bbox(lat, lng, food_radius_km)
    release = safe_release(release)
    categories = sorted(FOOD) + sorted(set(ATTRACTIONS) | STATIONS)
    if not all(_CATEGORY.match(c) for c in categories):   # constants, but they become SQL literals
        raise ValueError("invalid Overture category constant")
    food = ",".join(f"'{c}'" for c in sorted(FOOD))
    other = ",".join(f"'{c}'" for c in sorted(set(ATTRACTIONS) | STATIONS))
    xmin, xmax, ymin, ymax, fx0, fx1, fy0, fy1 = (float(v) for v in (xmin, xmax, ymin, ymax, fx0, fx1, fy0, fy1))
    con = _database(memory_limit, threads).cursor()   # cursor = own connection, shared caches
    try:
        # Only light columns are read: websites, sources and the full taxonomy tree made the
        # first S3 read ~40% slower (measured 83 s -> 49 s for central Rome) and were barely used.
        rows = con.execute(f"""
            SELECT id, names.primary, basic_category, taxonomy.primary, NULL AS hierarchy, confidence,
                   (bbox.xmin + bbox.xmax) / 2 AS lng, (bbox.ymin + bbox.ymax) / 2 AS lat,
                   NULL AS website, NULL AS license, names.common['en'], brand.names.primary
            FROM read_parquet('{S3_PATH.format(release=release)}', hive_partitioning=1)
            WHERE bbox.xmin BETWEEN ? AND ? AND bbox.ymin BETWEEN ? AND ?
              AND (operating_status IS NULL OR operating_status = 'open')
              AND ((basic_category IN ({food}) AND confidence >= 0.75
                    AND bbox.xmin BETWEEN ? AND ? AND bbox.ymin BETWEEN ? AND ?)
                   OR (basic_category IN ({other}) AND confidence >= 0.6))
            ORDER BY confidence DESC LIMIT 8000""",
                           [xmin, xmax, ymin, ymax, fx0, fx1, fy0, fy1]).fetchall()
    finally:
        con.close()
    places: list[Place] = []
    stations: list[dict] = []
    for r in rows:
        x = row_to_place(r, local_cuisines)
        if isinstance(x, Place):
            places.append(x)
        elif isinstance(x, dict):
            stations.append(x)
    log.info("Overture %s: %d places, %d stations", release, len(places), len(stations))
    return places, stations
