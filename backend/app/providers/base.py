"""Provider interfaces.

Every external data source (Google Maps Platform, the bundled mock dataset)
implements these protocols. Engines only talk to these interfaces, so swapping
mock -> live is a configuration change, not a code change.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol

from app.schemas.common import DataSource, LatLng, Money
from app.schemas.place import Place
from app.schemas.trip import TransportMode


@dataclass(frozen=True)
class GeocodeResult:
    location: LatLng
    formatted_address: str
    approximate: bool
    source: DataSource
    note: str | None = None


@dataclass(frozen=True)
class CityContext:
    name: str
    center: LatLng
    country_code: str | None
    radius_km: float
    has_metro: bool | None   # None = unknown (live mode decides per route)
    source: DataSource
    utc_offset_minutes: int | None = None   # local time offset, used for departure times


@dataclass(frozen=True)
class PlaceQuery:
    """A single discovery query (e.g. "museums" or "vegetarian restaurants")."""
    text: str
    tag: str                       # interest / food tag that produced this query
    kind: str                      # "attraction" | "food"
    max_results: int = 20


@dataclass
class RouteResult:
    mode: TransportMode
    distance_km: float
    duration_min: float
    duration_without_traffic_min: float | None
    traffic_aware: bool
    polyline: list[LatLng]
    source: DataSource
    fare: Money | None = None             # set only when the provider returned a real fare
    available: bool = True                # False when the mode is not offered on this route
    note: str | None = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def unavailable(cls, mode: TransportMode, source: DataSource, note: str, distance_km: float = 0) -> "RouteResult":
        """The mode is not offered on this route (no stations nearby, no route found...)."""
        return cls(mode, distance_km, 0, None, False, [], source, available=False, note=note)


class GeocodingProvider(Protocol):
    source: DataSource

    def geocode(self, query: str, city: CityContext | None = None) -> GeocodeResult: ...

    def resolve_city(self, city_name: str) -> CityContext: ...


class PlacesProvider(Protocol):
    source: DataSource

    def search(self, city: CityContext, query: PlaceQuery) -> list[Place]: ...

    def get_place(self, place_id: str) -> Place: ...


class RoutesProvider(Protocol):
    source: DataSource

    def compute_route(
        self,
        origin: LatLng,
        destination: LatLng,
        mode: TransportMode,
        departure: dt.datetime | None,
        city: CityContext,
    ) -> RouteResult: ...
