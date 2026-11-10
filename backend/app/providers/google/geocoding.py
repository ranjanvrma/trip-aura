"""Google Geocoding API provider.

Docs: https://developers.google.com/maps/documentation/geocoding/requests-geocoding
"""
from __future__ import annotations

import logging
import time

from app.core.errors import LocationNotFoundError, ProviderRequestError
from app.core.geo import haversine_km
from app.providers.base import CityContext, GeocodeResult
from app.providers.google.client import GoogleClient
from app.schemas.common import DataSource, LatLng

log = logging.getLogger(__name__)
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
TIMEZONE_URL = "https://maps.googleapis.com/maps/api/timezone/json"


class GoogleGeocodingProvider:
    source = DataSource.GOOGLE

    def __init__(self, client: GoogleClient):
        self._c = client

    def _lookup(self, address: str) -> dict:
        data = self._c.get(GEOCODE_URL, {"address": address, "key": self._c.key})
        status = data.get("status")
        if status == "ZERO_RESULTS":
            raise LocationNotFoundError(f"Google could not find '{address}'")
        if status != "OK":
            raise ProviderRequestError(f"Geocoding failed with status {status}: {data.get('error_message', '')}")
        return data["results"][0]

    def resolve_city(self, city_name: str) -> CityContext:
        r = self._lookup(city_name)
        loc = r["geometry"]["location"]
        country = next((c["short_name"] for c in r.get("address_components", []) if "country" in c.get("types", [])), None)
        viewport = r["geometry"].get("viewport")
        radius = 20.0
        if viewport:
            ne, sw = viewport["northeast"], viewport["southwest"]
            radius = max(5.0, min(40.0, haversine_km(ne["lat"], ne["lng"], sw["lat"], sw["lng"]) / 2))
        return CityContext(name=r.get("formatted_address", city_name), center=LatLng(lat=loc["lat"], lng=loc["lng"]),
                           country_code=country, radius_km=radius, has_metro=None, source=self.source,
                           utc_offset_minutes=self._utc_offset(loc["lat"], loc["lng"]))

    def _utc_offset(self, lat: float, lng: float) -> int | None:
        """Time Zone API lookup so planned departure times are sent to Routes in the right zone."""
        try:
            data = self._c.get(TIMEZONE_URL, {"location": f"{lat},{lng}", "timestamp": int(time.time()), "key": self._c.key})
        except ProviderRequestError as exc:
            log.warning("Time Zone API unavailable (%s); departures will use 'now'", exc.message)
            return None
        if data.get("status") != "OK":
            log.warning("Time Zone API status %s; departures will use 'now'", data.get("status"))
            return None
        return int((data.get("rawOffset", 0) + data.get("dstOffset", 0)) / 60)

    def geocode(self, query: str, city: CityContext | None = None) -> GeocodeResult:
        address = query if (city is None or city.name.split(",")[0].lower() in query.lower()) else f"{query}, {city.name}"
        r = self._lookup(address)
        loc = r["geometry"]["location"]
        loc_type = r["geometry"].get("location_type", "APPROXIMATE")
        approximate = loc_type in ("APPROXIMATE", "GEOMETRIC_CENTER") or bool(r.get("partial_match"))
        return GeocodeResult(
            location=LatLng(lat=loc["lat"], lng=loc["lng"]), formatted_address=r.get("formatted_address", query),
            approximate=approximate, source=self.source,
            note=("Google returned an approximate/partial match; verify the pin on the map." if approximate else None),
        )
