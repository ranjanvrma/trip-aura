"""Geocoding service: resolves the destination city and the user's accommodation."""
from __future__ import annotations

import logging

from app.core.geo import haversine_km
from app.providers.base import CityContext, GeocodeResult, GeocodingProvider
from app.schemas.common import DataSource
from app.schemas.trip import AccommodationInput

log = logging.getLogger(__name__)


class GeocodingService:
    def __init__(self, provider: GeocodingProvider):
        self._p = provider

    @property
    def source(self):
        return self._p.source

    def resolve_city(self, name: str) -> CityContext:
        return self._p.resolve_city(name)

    def resolve_accommodation(self, acc: AccommodationInput, city: CityContext) -> tuple[GeocodeResult, list[str]]:
        warnings: list[str] = []
        if acc.location is not None:
            result = GeocodeResult(acc.location, acc.name_or_address, approximate=False, source=DataSource.USER,
                                   note="Coordinates supplied by the user")
        else:
            result = self._p.geocode(acc.name_or_address, city)
            if result.note:
                warnings.append(result.note)
        dist = haversine_km(city.center.lat, city.center.lng, result.location.lat, result.location.lng)
        if dist > city.radius_km * 2:
            warnings.append(f"Your accommodation is {dist:.0f} km from the city centre; travel times will be long.")
        return result, warnings
