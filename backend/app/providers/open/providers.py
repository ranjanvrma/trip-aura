"""Open-data implementations of the provider interfaces (worldwide, no API key)."""
from __future__ import annotations

import datetime as dt
import logging
import math

from app.core.errors import LocationNotFoundError, NotFoundError
from app.core.geo import haversine_km
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

    def __init__(self, http: OpenHttp):
        self.http = http

    def resolve_city(self, city_name: str) -> CityContext:
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
            d = city.radius_km * 1.5 / 111
            dl = d / max(0.2, math.cos(math.radians(city.center.lat)))
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
        elif query.tag not in ("all",):
            pool = [p for p in pool if query.tag in p.categories]
        pool.sort(key=lambda p: (-(p.prominence or 0), p.name))
        return pool[: query.max_results]

    def get_place(self, place_id: str) -> Place:
        for data in self.cities._memory.values():
            for p in data.places:
                if p.id == place_id:
                    return p
        raise NotFoundError(f"Place '{place_id}' is not in a loaded city")

    def city_data(self, city: CityContext):
        return self.cities.get(city)


class OsrmRoutesProvider:
    """Walking / driving via OSRM (no live traffic); transit via the heuristic provider."""

    source = DataSource.OSM

    def __init__(self, http: OpenHttp, driving_url: str, walking_url: str, heuristic: HeuristicRoutesProvider):
        self.http = http
        self.driving_url = driving_url.rstrip("/")
        self.walking_url = walking_url.rstrip("/")
        self.heuristic = heuristic

    def compute_route(self, origin: LatLng, destination: LatLng, mode: TransportMode,
                      departure: dt.datetime | None, city: CityContext) -> RouteResult:
        if mode in (TransportMode.METRO, TransportMode.BUS, TransportMode.TRAIN):
            return self.heuristic.compute_route(origin, destination, mode, departure, city)
        base = self.walking_url if mode == TransportMode.WALKING else self.driving_url
        url = f"{base}/{origin.lng:.6f},{origin.lat:.6f};{destination.lng:.6f},{destination.lat:.6f}"
        data = self.http.get_json(url, {"overview": "simplified", "geometries": "geojson"}, what="OSRM routing")
        if data.get("code") != "Ok" or not data.get("routes"):
            return RouteResult(mode, 0, 0, None, False, [], self.source, available=False,
                               note=f"OSRM found no {mode.value} route")
        r = data["routes"][0]
        minutes = r["duration"] / 60
        if mode == TransportMode.AUTO:
            minutes *= 1.15
        overhead = {TransportMode.CAB: 6, TransportMode.AUTO: 3, TransportMode.PERSONAL_VEHICLE: 6}.get(mode, 0)
        line = [LatLng(lat=c[1], lng=c[0]) for c in (r.get("geometry") or {}).get("coordinates", [])]
        return RouteResult(mode, round(r["distance"] / 1000, 2), round(minutes + overhead, 1), None, False, line,
                           self.source, note="OSRM road route (no live traffic)")
