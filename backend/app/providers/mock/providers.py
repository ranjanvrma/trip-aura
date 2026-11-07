"""Mock implementations of the provider interfaces, backed by dataset.py.

Everything returned here is labelled DataSource.MOCK. Ratings are exposed as
`provider="mock"` with an explicit "not a Google rating" label.
"""
from __future__ import annotations

import datetime as dt
import logging

from app.core.errors import LocationNotFoundError, NotFoundError, UnsupportedInMockModeError
from app.core.geo import haversine_km, interpolate
from app.engines.fares import MODE_PROFILES, heuristic_duration_min, simulated_traffic_multiplier
from app.providers.base import CityContext, GeocodeResult, PlaceQuery, RouteResult
from app.providers.mock import dataset as ds
from app.schemas.common import DataSource, LatLng, Money
from app.schemas.place import DietInfo, ExternalRating, OpeningHours, Place, PlaceKind, Review, TimeRange
from app.schemas.trip import TransportMode

log = logging.getLogger(__name__)
SRC = DataSource.MOCK
MOCK_RATING_LABEL = "Demo rating (mock data, not from Google)"


def _hours(raw: dict) -> OpeningHours:
    return OpeningHours(
        known=True,
        weekly={d: [TimeRange(**r) for r in ranges] for d, ranges in raw.items()},
        source=SRC,
    )


def _rating(r: float, n: int) -> ExternalRating:
    return ExternalRating(provider=SRC, rating=r, review_count=n, verified=False, label=MOCK_RATING_LABEL)


def _attraction(a: dict) -> Place:
    return Place(
        id=a["id"], name=a["name"], kind=PlaceKind(a["kind"]), categories=a["categories"],
        location=LatLng(lat=a["lat"], lng=a["lng"]), address=f"{a['name']}, Jaipur (approximate location)",
        description=a["desc"], external_rating=_rating(a["rating"], a["reviews"]),
        entry_fee=Money(amount=a["fee"], currency="INR", verified=False, source=SRC,
                        note="Demo entry fee (mock) - check the official price before visiting"),
        typical_visit_minutes=a["mins"], opening_hours=_hours(a["hours"]), is_famous=a["famous"],
        best_time=a["best"], source=SRC,
    )


def _restaurant(r: dict) -> Place:
    d = r["diet"]
    diet = DietInfo(
        vegetarian_only=d.get("veg_only", False), vegetarian_options=d.get("veg", False),
        vegan_options=d.get("vegan", False), jain_options=d.get("jain", False),
        egg_options=d.get("egg", False), non_veg=d.get("nonveg", False), known=True, source=SRC,
    )
    return Place(
        id=r["id"], name=r["name"], kind=PlaceKind(r["kind"]), categories=["food"] + r["cats"],
        location=LatLng(lat=r["lat"], lng=r["lng"]), address="Jaipur (demo restaurant, fictional)",
        external_rating=_rating(r["rating"], r["reviews_n"]),
        avg_cost_per_person=Money(amount=r["cost"], currency="INR", verified=False, source=SRC,
                                  note="Demo average cost per person (mock)"),
        typical_visit_minutes=60, opening_hours=_hours(r["hours"]), diet=diet,
        food_categories=r["cats"], cuisines=r["cuisines"], best_time=r["meals"],
        reviews=[Review(text=t, source=SRC) for t in r["reviews"]], source=SRC,
    )


_PLACES: dict[str, Place] = {}


def _all_places() -> dict[str, Place]:
    if not _PLACES:
        for a in ds.ATTRACTIONS:
            _PLACES[a["id"]] = _attraction(a)
        for r in ds.RESTAURANTS:
            _PLACES[r["id"]] = _restaurant(r)
    return _PLACES


def _city_context() -> CityContext:
    c = ds.MOCK_CITY
    return CityContext(name=c["name"], center=LatLng(lat=c["center"][0], lng=c["center"][1]),
                       country_code=c["country_code"], radius_km=c["radius_km"], has_metro=c["has_metro"], source=SRC,
                       utc_offset_minutes=330)


class MockGeocodingProvider:
    source = SRC

    def resolve_city(self, city_name: str) -> CityContext:
        if city_name.strip().lower() not in ds.MOCK_CITY["aliases"]:
            raise UnsupportedInMockModeError(
                f"Mock mode only includes demo data for {ds.MOCK_CITY['name']}. "
                "Set DATA_MODE=live with a GOOGLE_MAPS_API_KEY to plan trips to other cities.",
                details={"supported_cities": [ds.MOCK_CITY["name"]]},
            )
        return _city_context()

    def geocode(self, query: str, city: CityContext | None = None) -> GeocodeResult:
        q = query.strip().lower()
        if not q:
            raise LocationNotFoundError("Empty address")
        for name, lat, lng in ds.MOCK_LOCALITIES:
            if name in q:
                return GeocodeResult(LatLng(lat=lat, lng=lng), f"{name.title()}, Jaipur (mock locality centre)",
                                     approximate=True, source=SRC,
                                     note="Mock geocoder resolved the locality only, not the exact building.")
        for p in _all_places().values():
            if p.name.lower().replace(" (demo)", "") in q:
                return GeocodeResult(p.location, p.name, approximate=False, source=SRC)
        ctx = city or _city_context()
        return GeocodeResult(
            ctx.center, f"{ctx.name} city centre (approximation)", approximate=True, source=SRC,
            note=("Mock geocoder could not resolve this address, so the city centre is used. "
                  "Pick the location on the map or enable live mode for exact geocoding."),
        )


class MockPlacesProvider:
    source = SRC

    def search(self, city: CityContext, query: PlaceQuery) -> list[Place]:
        places = _all_places().values()
        tag = query.tag
        if query.kind == "food":
            pool = [p for p in places if p.kind in (PlaceKind.RESTAURANT, PlaceKind.CAFE)]
            if tag in ("all", "restaurants"):
                return list(pool)[: query.max_results]
            return [p for p in pool if tag in p.food_categories or tag in p.cuisines][: query.max_results]
        pool = [p for p in places if p.kind in (PlaceKind.ATTRACTION, PlaceKind.PARK)]
        if tag == "famous":
            return [p for p in pool if p.is_famous][: query.max_results]
        if tag == "all":
            return list(pool)[: query.max_results]
        words = set(tag.split("_"))
        return [p for p in pool if tag in p.categories
                or any(w in (p.description or "").lower() or w in p.name.lower() for w in words if len(w) > 3)
                ][: query.max_results]

    def get_place(self, place_id: str) -> Place:
        try:
            return _all_places()[place_id]
        except KeyError as exc:
            raise NotFoundError(f"Mock place '{place_id}' not found") from exc


def _nearest_station(lat: float, lng: float) -> tuple[str, float]:
    best = min(ds.MOCK_METRO_STATIONS, key=lambda s: haversine_km(lat, lng, s[1], s[2]))
    return best[0], haversine_km(lat, lng, best[1], best[2])


class MockRoutesProvider:
    """Heuristic routes: straight-line distance x detour factor, mode speeds and simulated traffic."""

    source = SRC

    def compute_route(self, origin: LatLng, destination: LatLng, mode: TransportMode,
                      departure: dt.datetime | None, city: CityContext) -> RouteResult:
        straight = haversine_km(origin.lat, origin.lng, destination.lat, destination.lng)
        minute = (departure.hour * 60 + departure.minute) if departure else 11 * 60
        traffic = simulated_traffic_multiplier(minute)
        line = [LatLng(lat=a, lng=b) for a, b in interpolate(origin.as_tuple(), destination.as_tuple(), 6)]

        if mode == TransportMode.METRO:
            s1, d1 = _nearest_station(origin.lat, origin.lng)
            s2, d2 = _nearest_station(destination.lat, destination.lng)
            if d1 > 1.5 or d2 > 1.5 or s1 == s2:
                return RouteResult(mode, straight, 0, None, False, [], SRC, available=False,
                                   note="No metro station within 1.5 km of both ends (mock metro network)")
            walk = (d1 + d2) * 1.25 / MODE_PROFILES[TransportMode.WALKING].speed_kmh * 60
            dist, dur = heuristic_duration_min(mode, straight)
            return RouteResult(mode, round(dist + d1 + d2, 2), round(dur + walk, 1), None, False, line, SRC,
                               note=f"Metro {s1} -> {s2} incl. walking to stations (mock estimate)")
        if mode == TransportMode.TRAIN and straight < 8:
            return RouteResult(mode, straight, 0, None, False, [], SRC, available=False,
                               note="Suburban train not useful for short intra-city hops")

        dist, dur = heuristic_duration_min(mode, straight, traffic)
        _, free_flow = heuristic_duration_min(mode, straight, 1.0)
        sensitive = MODE_PROFILES[mode].traffic_sensitive
        return RouteResult(
            mode, round(dist, 2), round(dur, 1), round(free_flow, 1) if sensitive else None,
            traffic_aware=sensitive, polyline=line, source=SRC,
            note=(f"Simulated traffic x{traffic:.2f} (mock)" if sensitive and traffic > 1 else "Mock estimate"),
        )
