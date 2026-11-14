"""Open-data implementations of the provider interfaces (worldwide, no API key)."""
from __future__ import annotations

import datetime as dt
import logging
import time

from rapidfuzz import fuzz

from app.core.errors import LocationNotFoundError, NotFoundError, ProviderRequestError
from app.core.geo import degree_span
from app.core.geo import haversine_km
from app.core.text import fold
from app.providers.base import CityContext, GeocodeResult, PlaceQuery, RouteResult
from app.providers.heuristic_routes import HeuristicRoutesProvider
from app.providers.open.city_store import CityDataService
from app.providers.open.http import OpenHttp
from app.schemas.common import DataSource, LatLng
from app.schemas.place import Place, PlaceKind
from app.schemas.trip import TransportMode

log = logging.getLogger(__name__)
CITY_TYPES = {"city", "town", "village", "municipality", "borough", "county", "state_district", "city_district",
              "hamlet", "suburb", "island", "region", "state", "province"}


class OpenGeocodingProvider:
    source = DataSource.OSM

    def __init__(self, http: OpenHttp, city_index=None):
        self.http = http
        self.city_index = city_index      # offline GeoNames index: resolves most cities with no network call

    @staticmethod
    def radius_for_population(pop: int) -> float:
        """Search radius (km) that covers a city's sights, by population."""
        if pop >= 5_000_000:
            return 15.0
        if pop >= 1_000_000:
            return 10.0
        if pop >= 300_000:
            return 7.0
        return 5.0

    def _from_index(self, city_name: str) -> CityContext | None:
        if self.city_index is None:
            return None
        try:
            head = city_name.split(",")[0].strip()
            c = self.city_index.exact(head)
            if c is None or ("," in city_name and fold(city_name.split(",", 1)[1].strip())
                             not in (fold(c.country), fold(c.region), fold(c.country_code))):
                hits = self.city_index.search(city_name, 1)
                c = hits[0] if hits and fuzz.ratio(fold(head), fold(hits[0].name)) >= 85 else c
        except Exception as exc:  # index unavailable -> use Nominatim
            log.warning("City index lookup failed: %s", exc)
            return None
        if c is None:
            return None
        return CityContext(name=f"{c.name}, {c.country}", center=LatLng(lat=c.lat, lng=c.lng),
                           country_code=c.country_code, radius_km=self.radius_for_population(c.population),
                           has_metro=None, source=DataSource.OSM, utc_offset_minutes=None)

    def resolve_city(self, city_name: str) -> CityContext:
        hit = self._from_index(city_name)
        if hit is not None:
            return hit
        results = self.http.nominatim("search", {"q": city_name, "limit": 5, "addressdetails": 1,
                                                 "accept-language": "en"})
        if not results:
            raise LocationNotFoundError(f"Could not find a city called '{city_name}'")
        r = next((x for x in results if x.get("addresstype") in CITY_TYPES), results[0])
        lat, lng = float(r["lat"]), float(r["lon"])
        s, n, w, e = (float(v) for v in r.get("boundingbox", [lat, lat, lng, lng]))
        diag = haversine_km(s, w, n, e)
        radius = max(4.0, min(20.0, diag / 2 if diag > 0 else 8.0))
        addr = r.get("address") or {}
        country = addr.get("country")
        name = r.get("name") or city_name
        return CityContext(
            name=f"{name}, {country}" if country else name, center=LatLng(lat=lat, lng=lng),
            country_code=(addr.get("country_code") or "").upper() or None, radius_km=radius, has_metro=None,
            source=self.source, utc_offset_minutes=None,
        )

    def geocode(self, query: str, city: CityContext | None = None) -> GeocodeResult:
        params = {"q": query, "limit": 1, "addressdetails": 0, "accept-language": "en"}
        if city:
            d, dl = degree_span(city.center.lat, city.radius_km * 1.5)
            params.update({"viewbox": f"{city.center.lng - dl},{city.center.lat + d},{city.center.lng + dl},"
                                      f"{city.center.lat - d}", "bounded": 1})
        res = self.http.nominatim("search", params)
        if not res and city:
            params.pop("bounded")
            q2 = query if city.name.split(",")[0].lower() in query.lower() else f"{query}, {city.name}"
            res = self.http.nominatim("search", {**params, "q": q2})
        if not res:
            raise LocationNotFoundError(
                f"OpenStreetMap could not find '{query}'. Try a street address, a nearby landmark, "
                "or enter exact coordinates.")
        r = res[0]
        rank = int(r.get("place_rank", 30))
        approximate = rank < 26
        return GeocodeResult(
            location=LatLng(lat=float(r["lat"]), lng=float(r["lon"])), formatted_address=r.get("display_name", query),
            approximate=approximate, source=self.source,
            note=("Only an area-level match was found for your accommodation; check the pin on the map "
                  "or enter exact coordinates." if approximate else None),
        )


class OpenPlacesProvider:
    source = DataSource.OPEN
    supports_text_search = False   # the whole city dataset is local; filtering happens here

    def __init__(self, cities: CityDataService):
        self.cities = cities

    def search(self, city: CityContext, query: PlaceQuery) -> list[Place]:
        data = self.cities.get(city)
        if query.kind == "food":
            pool = [p for p in data.places if p.kind in (PlaceKind.RESTAURANT, PlaceKind.CAFE)]
            # prefer places with richer data (hours / diet tags), then closeness to the centre
            pool.sort(key=lambda p: (-(int(p.opening_hours is not None and p.opening_hours.known)
                                       + int(p.diet is not None and p.diet.known)),
                                     haversine_km(city.center.lat, city.center.lng, p.location.lat, p.location.lng)))
            return pool[: query.max_results]
        pool = [p for p in data.places if p.kind in (PlaceKind.ATTRACTION, PlaceKind.PARK)]
        if query.tag == "famous":
            pool = [p for p in pool if p.is_famous]
        elif query.tag != "all":
            pool = [p for p in pool if query.tag in p.categories]
        pool.sort(key=lambda p: (-(p.prominence or 0), p.name))
        return pool[: query.max_results]

    def get_place(self, place_id: str) -> Place:
        for data in self.cities._memory.values():
            for p in data.places:
                if p.id == place_id:
                    return p
        raise NotFoundError(f"Place '{place_id}' is not in a loaded city")


OSRM_TIMEOUT_S = 10
OSRM_PAUSE_S = 300


class OsrmRoutesProvider:
    """Walking / driving via OSRM (no live traffic); transit via the heuristic provider."""

    source = DataSource.OSM

    def __init__(self, http: OpenHttp, driving_url: str, walking_url: str, heuristic: HeuristicRoutesProvider):
        self.http = http
        self.driving_url = driving_url.rstrip("/")
        self.walking_url = walking_url.rstrip("/")
        self.heuristic = heuristic
        self._failures = 0
        self._paused_until = 0.0   # after repeated failures OSRM is skipped for a while (public demo servers)

    def _estimate(self, origin: LatLng, destination: LatLng, mode: TransportMode, departure: dt.datetime | None,
                  city: CityContext, why: str) -> RouteResult:
        r = self.heuristic.compute_route(origin, destination, mode, departure, city)
        r.note = f"{why}; time estimated from distance" + (f" ({r.note})" if r.note else "")
        return r

    def compute_route(self, origin: LatLng, destination: LatLng, mode: TransportMode,
                      departure: dt.datetime | None, city: CityContext) -> RouteResult:
        if mode in (TransportMode.METRO, TransportMode.BUS, TransportMode.TRAIN):
            return self.heuristic.compute_route(origin, destination, mode, departure, city)
        if time.monotonic() < self._paused_until:
            return self._estimate(origin, destination, mode, departure, city, "OSRM routing is paused after errors")
        base = self.walking_url if mode == TransportMode.WALKING else self.driving_url
        url = f"{base}/{origin.lng:.6f},{origin.lat:.6f};{destination.lng:.6f},{destination.lat:.6f}"
        try:
            data = self.http.get_json(url, {"overview": "simplified", "geometries": "geojson"}, what="OSRM routing",
                                      timeout=OSRM_TIMEOUT_S)
        except ProviderRequestError as exc:
            # one slow or failing leg must not fail the whole plan: estimate it, and rest OSRM if it keeps failing
            self._failures += 1
            if self._failures >= 3:
                self._paused_until, self._failures = time.monotonic() + OSRM_PAUSE_S, 0
                log.warning("OSRM failed three times in a row; using estimates for %d s", OSRM_PAUSE_S)
            return self._estimate(origin, destination, mode, departure, city, f"OSRM unavailable ({exc.message})")
        self._failures = 0
        if data.get("code") != "Ok" or not data.get("routes"):
            return RouteResult.unavailable(mode, self.source, f"OSRM found no {mode.value} route")
        r = data["routes"][0]
        minutes = r["duration"] / 60
        if mode == TransportMode.AUTO:
            minutes *= 1.15
        overhead = {TransportMode.CAB: 6, TransportMode.AUTO: 3, TransportMode.PERSONAL_VEHICLE: 6}.get(mode, 0)
        line = [LatLng(lat=c[1], lng=c[0]) for c in (r.get("geometry") or {}).get("coordinates", [])]
        return RouteResult(mode, round(r["distance"] / 1000, 2), round(minutes + overhead, 1), None, False, line,
                           self.source, note="OSRM road route (no live traffic)")
