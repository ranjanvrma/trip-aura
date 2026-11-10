"""On-demand city datasets built from open data and cached in SQLite.

First request for a city (later requests read the cache):
1. Overture Maps (primary): restaurants, cafes, museums, parks, historic sites, stations.
2. Wikidata: notable sights near the city with their Wikipedia coverage
   (prominence), which drives "famous" places outside the user's interests.
3. OpenStreetMap via Overpass (best effort, time-boxed): opening hours, entry
   fees, diet tags, metro/train stations. Public Overpass servers are often
   busy, so a failure here is reported as a warning, not an error.
4. Wikivoyage: local dishes named in the city's "Eat" section.

A city fails only when no source at all could be reached.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import Settings
from app.core.errors import ProviderRequestError
from app.core.geo import haversine_km
from app.core.text import fold
from app.providers.base import CityContext
from app.providers.open import osm
from app.providers.open.http import OpenHttp
from app.schemas.common import DataSource
from app.schemas.itinerary import DishSuggestion
from app.schemas.place import Place, PlaceKind

log = logging.getLogger(__name__)
DATASET_VERSION = 6
FAMOUS_SITELINKS = 20


@dataclass
class CityData:
    key: str
    name: str
    places: list[Place]
    stations: list[dict]
    guide_dishes: list[DishSuggestion]
    sources: list[str]
    warnings: list[str] = field(default_factory=list)
    built_at: dt.datetime | None = None
    wikivoyage_title: str | None = None

    def to_payload(self) -> dict:
        return {
            "places": [p.model_dump(mode="json") for p in self.places], "stations": self.stations,
            "guide_dishes": [d.model_dump(mode="json") for d in self.guide_dishes], "sources": self.sources,
            "warnings": self.warnings, "wikivoyage_title": self.wikivoyage_title,
        }

    @classmethod
    def from_payload(cls, key: str, name: str, built_at: dt.datetime, payload: dict) -> "CityData":
        return cls(key=key, name=name, places=[Place.model_validate(p) for p in payload["places"]],
                   stations=payload["stations"],
                   guide_dishes=[DishSuggestion.model_validate(d) for d in payload.get("guide_dishes", [])],
                   sources=payload.get("sources", []), warnings=payload.get("warnings", []), built_at=built_at,
                   wikivoyage_title=payload.get("wikivoyage_title"))


def city_key(city: CityContext) -> str:
    return f"{city.center.lat:.2f},{city.center.lng:.2f}"


# ------------------------------------------------------------------------- merging
_NON_ALNUM = re.compile(r"[^a-z0-9]")
_BILINGUAL = re.compile(r"^(.*?)\s*\((.*)\)$")


def _norm(name: str) -> str:
    return _NON_ALNUM.sub("", fold(name))


@lru_cache(maxsize=16384)   # merging compares each place with its neighbours, so names repeat a lot
def _keys(name: str) -> frozenset[str]:
    """Normalised name variants; 'English (Local)' yields both."""
    out = {_norm(name)}
    m = _BILINGUAL.match(name)
    if m:
        out |= {_norm(m.group(1)), _norm(m.group(2))}
    return frozenset(k for k in out if len(k) >= 3)


def _same(a: Place, b: Place, max_m: float) -> bool:
    if haversine_km(a.location.lat, a.location.lng, b.location.lat, b.location.lng) * 1000 > max_m:
        return False
    ka, kb = _keys(a.name), _keys(b.name)
    return bool(ka & kb) or any(x in y or y in x for x in ka for y in kb if min(len(x), len(y)) >= 6)


def _compatible(a: PlaceKind, b: PlaceKind) -> bool:
    groups = ({PlaceKind.ATTRACTION, PlaceKind.PARK}, {PlaceKind.RESTAURANT, PlaceKind.CAFE})
    return a == b or any(a in g and b in g for g in groups)


def _absorb(base: Place, extra: Place) -> None:
    """Fill gaps in `base` from `extra` without overwriting known values."""
    if (base.opening_hours is None or not base.opening_hours.known) and extra.opening_hours \
            and extra.opening_hours.known:
        base.opening_hours = extra.opening_hours
    base_assumed = base.entry_fee is not None and base.entry_fee.source == DataSource.ESTIMATE
    if extra.entry_fee is not None and (base.entry_fee is None or
                                        (base_assumed and extra.entry_fee.source != DataSource.ESTIMATE)):
        base.entry_fee = extra.entry_fee          # recorded fee beats a "usually free" assumption
    elif base_assumed and extra.entry_fee is None and extra.source == DataSource.WIKIDATA:
        base.entry_fee = None                     # Wikidata's type says this kind of site usually charges
    if extra.diet is not None and extra.diet.known and (base.diet is None or not base.diet.known):
        base.diet = extra.diet
    if not base.cuisines and extra.cuisines:
        base.cuisines = list(extra.cuisines)
    for c in extra.categories:
        if c not in base.categories:
            base.categories.append(c)
    for c in extra.food_categories:
        if c not in base.food_categories:
            base.food_categories.append(c)
    if extra.prominence and (base.prominence or 0) < extra.prominence:
        base.prominence = extra.prominence
    if extra.description and (not base.description or base.description.startswith("http")):
        base.description = extra.description
    if extra.address and not base.address:
        base.address = extra.address
    if extra.kind == PlaceKind.ATTRACTION and extra.source == DataSource.WIKIDATA:
        base.typical_visit_minutes = max(base.typical_visit_minutes, extra.typical_visit_minutes)
    for k, v in extra.external_ids.items():
        base.external_ids.setdefault(k, v)


def merge_places(base: list[Place], extra: list[Place], max_m: float = 150) -> list[Place]:
    """Matching name within max_m enriches the existing place; everything else is added."""
    grid: dict[tuple[int, int], list[Place]] = {}

    def cell(p: Place) -> tuple[int, int]:
        return int(p.location.lat * 200), int(p.location.lng * 200)   # ~500 m cells

    out = list(base)
    for p in out:
        grid.setdefault(cell(p), []).append(p)
    for e in extra:
        cx, cy = cell(e)
        match = next((b for dx in (-1, 0, 1) for dy in (-1, 0, 1) for b in grid.get((cx + dx, cy + dy), [])
                      if _compatible(b.kind, e.kind) and _same(b, e, max_m)), None)
        if match is not None:
            _absorb(match, e)
        else:
            out.append(e)
            grid.setdefault((cx, cy), []).append(e)
    return out


# ------------------------------------------------------------------------- service
class CityDataService:
    def __init__(self, settings: Settings, http: OpenHttp, session_factory=None):
        self.settings = settings
        self.http = http
        self._session_factory = session_factory
        self._memory: dict[str, CityData] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _sessions(self):
        if self._session_factory is None:
            from app.db import database
            if database._SessionLocal is None:
                database.init_engine()
            self._session_factory = database._SessionLocal
        return self._session_factory()

    def _load_cached(self, key: str) -> CityData | None:
        from app.db.models import CityDataset

        with self._sessions() as db:
            row = db.get(CityDataset, key)
            if row is None or row.version != DATASET_VERSION:
                return None
            built = row.built_at if row.built_at.tzinfo else row.built_at.replace(tzinfo=dt.timezone.utc)
            if dt.datetime.now(dt.timezone.utc) - built > dt.timedelta(days=self.settings.city_cache_days):
                return None
            return CityData.from_payload(row.key, row.name, built, row.payload)

    def _save(self, data: CityData) -> None:
        from app.db.models import CityDataset

        with self._sessions() as db:
            row = db.get(CityDataset, data.key)
            if row is None:
                row = CityDataset(key=data.key)
                db.add(row)
            row.name, row.version, row.payload = data.name, DATASET_VERSION, data.to_payload()
            row.built_at = data.built_at or dt.datetime.now(dt.timezone.utc)
            db.commit()

    def get(self, city: CityContext) -> CityData:
        key = city_key(city)
        if key in self._memory:
            return self._memory[key]
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:  # one build per city at a time
            if key in self._memory:
                return self._memory[key]
            data = self._load_cached(key)
            if data is None:
                data = self.build(city)
                self._save(data)
            self._memory[key] = data
            return data

    def stations(self, city: CityContext) -> list[dict]:
        return self.get(city).stations

    # ---------------------------------------------------------------------- build
    def build(self, city: CityContext) -> CityData:
        from app.engines.food import DISHES

        t0 = time.monotonic()
        radius_km = min(max(city.radius_km, 5.0), 12.0)
        food_km = min(radius_km, 5.0)
        local = osm.LOCAL_CUISINES.get((city.country_code or "").upper(), set())
        lat, lng = city.center.lat, city.center.lng
        log.info("Building open dataset for %s (r=%.1f km, food r=%.1f km)", city.name, radius_km, food_km)
        sources: list[str] = []
        warnings: list[str] = []
        timings: dict[str, float] = {}

        # All sources are fetched IN PARALLEL (they are independent network calls), so a new city
        # costs roughly the slowest source instead of the sum of all of them. Results are then
        # merged in a fixed order so the outcome does not depend on which call finished first.
        def timed(name, fn, *args):
            def run():
                t = time.monotonic()
                try:
                    return fn(*args)
                finally:
                    timings[name] = round(time.monotonic() - t, 1)
            return run

        def overture_layer():
            from app.providers.open import overture

            release = self.settings.overture_release or overture.latest_release(self.settings.open_user_agent)
            places, stations = overture.fetch(lat, lng, radius_km, food_km, release, local,
                                              self.settings.duckdb_memory_limit, self.settings.duckdb_threads)
            return release, places, stations

        def wikidata_layer():
            from app.providers.open.wikimedia import wikidata_notable_places

            return wikidata_notable_places(self.http, lat, lng, radius_km)

        def wikivoyage_layer():
            from app.providers.open.wikimedia import wikivoyage_dishes

            return wikivoyage_dishes(self.http, city.name.split(",")[0], set(DISHES))

        osm_deadline = time.monotonic() + self.settings.osm_time_budget_seconds

        def osm_layer(query: str):
            raw = self.http.overpass(query, deadline=osm_deadline)
            return osm.parse_elements(raw.get("elements", []), local)

        jobs = {}
        osm_queries = osm.build_queries(lat, lng, radius_km, food_km)
        with ThreadPoolExecutor(max_workers=7, thread_name_prefix="city-load") as pool:
            if self.settings.overture_enabled:
                jobs["overture"] = pool.submit(timed("overture", overture_layer))
            jobs["wikidata"] = pool.submit(timed("wikidata", wikidata_layer))
            if self.settings.wikivoyage_enabled:
                jobs["wikivoyage"] = pool.submit(timed("wikivoyage", wikivoyage_layer))
            for name, query in osm_queries.items():
                jobs[f"osm_{name}"] = pool.submit(timed(f"osm_{name}", osm_layer, query))
        results = {}
        for name, fut in jobs.items():
            try:
                results[name] = fut.result()
            except ImportError:
                warnings.append("Overture layer skipped: the optional 'duckdb' package is not installed.")
            except Exception as exc:
                log.warning("%s layer failed: %s", name, exc)
                results[name] = exc

        places: list[Place] = []
        stations: list[dict] = []
        layers_ok = 0

        # 1) Overture: primary worldwide POI layer
        ov = results.get("overture")
        if isinstance(ov, tuple):
            release, places, stations = ov
            sources.append(f"Overture Maps ({release})")
            layers_ok += 1
        elif isinstance(ov, Exception):
            warnings.append("Overture Maps was unavailable; place coverage is reduced.")

        # 2) Wikidata: notable sights with prominence (drives 'famous')
        wd = results.get("wikidata")
        if isinstance(wd, list):
            places = merge_places(places, wd, max_m=300)
            sources.append("Wikidata")
            layers_ok += 1
        else:
            warnings.append("Wikidata was unavailable, so 'famous place' detection is limited.")

        # 3) OpenStreetMap: opening hours, fees, diet tags, stations (best effort, time-boxed)
        osm_hits = 0
        for name in osm_queries:
            res = results.get(f"osm_{name}")
            if not isinstance(res, tuple):
                warnings.append(f"OpenStreetMap {name} data was unavailable (public servers busy); "
                                "opening hours, fees or diet tags may be missing.")
                continue
            osm_places, osm_stations = res
            places = merge_places(places, osm_places, max_m=150 if name == "food" else 300)
            if osm_stations:  # OSM distinguishes metro from mainline; prefer it over Overture's generic rail stops
                stations = osm_stations
            osm_hits += 1
        if osm_hits:
            sources.append("OpenStreetMap")
            layers_ok += 1
        if layers_ok == 0:
            raise ProviderRequestError("No open-data source could be reached for this city. Try again later.")

        # famous = widely covered on Wikipedia (absolute threshold or the city's top 12)
        ranked = sorted((p for p in places if p.prominence), key=lambda p: -(p.prominence or 0))
        top = {p.id for p in ranked[:12] if (p.prominence or 0) >= 5}
        for p in places:
            p.is_famous = (p.prominence or 0) >= FAMOUS_SITELINKS or p.id in top

        # 4) Wikivoyage dishes
        dishes: list[DishSuggestion] = []
        wv_title = None
        wv = results.get("wikivoyage")
        if isinstance(wv, tuple):
            dishes, wv_title = wv
            if wv_title:
                sources.append(f"Wikivoyage ({wv_title})")
        elif isinstance(wv, Exception):
            warnings.append("Wikivoyage was unavailable; no guidebook dish suggestions.")
        log.info("City sources for %s fetched in parallel: %s", city.name, timings)

        n_food = sum(1 for p in places if p.kind in (PlaceKind.RESTAURANT, PlaceKind.CAFE))
        log.info("Dataset %s: %d attractions/parks, %d food, %d stations from %s in %.0fs", city.name,
                 len(places) - n_food, n_food, len(stations), sources, time.monotonic() - t0)
        if len(places) - n_food < 5:
            warnings.append("Very few attractions are mapped in open data for this area.")
        return CityData(key=city_key(city), name=city.name, places=places, stations=stations, guide_dishes=dishes,
                        sources=sources, warnings=warnings, built_at=dt.datetime.now(dt.timezone.utc),
                        wikivoyage_title=wv_title)


ATTRIBUTIONS = {
    "OpenStreetMap": "Map data © OpenStreetMap contributors, ODbL 1.0 (openstreetmap.org/copyright)",
    "Wikidata": "Wikidata (CC0)",
    "Overture": "Overture Maps Foundation places (CDLA-Permissive-2.0; Foursquare records Apache-2.0, "
                "© 2024 Foursquare Labs, Inc.)",
    "Wikivoyage": "Wikivoyage contributors, CC BY-SA 4.0 (en.wikivoyage.org)",
    "Nominatim": "Geocoding by Nominatim / OpenStreetMap",
}


def attributions_for(sources: list[str]) -> list[str]:
    out = [ATTRIBUTIONS["Nominatim"]]
    for s in sources:
        for k, v in ATTRIBUTIONS.items():
            if s.startswith(k) and v not in out:
                out.append(v)
    return out
