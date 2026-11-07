"""Google Routes API provider (computeRoutes).

Docs: https://developers.google.com/maps/documentation/routes/compute_route_directions
Driving routes use TRAFFIC_AWARE routing; transit fares are kept only when
Google returns them (verified=True).
"""
from __future__ import annotations

import datetime as dt
import logging

from app.core.errors import ProviderRequestError
from app.providers.base import CityContext, RouteResult
from app.providers.google.client import GoogleClient
from app.schemas.common import DataSource, LatLng, Money
from app.schemas.trip import TransportMode

log = logging.getLogger(__name__)
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = ("routes.distanceMeters,routes.duration,routes.staticDuration,"
              "routes.polyline.encodedPolyline,routes.travelAdvisory.transitFare")

GOOGLE_MODE = {
    TransportMode.WALKING: "WALK",
    TransportMode.CAB: "DRIVE",
    TransportMode.AUTO: "DRIVE",
    TransportMode.PERSONAL_VEHICLE: "DRIVE",
    TransportMode.METRO: "TRANSIT",
    TransportMode.BUS: "TRANSIT",
    TransportMode.TRAIN: "TRANSIT",
}
TRANSIT_FILTER = {
    TransportMode.METRO: ["SUBWAY", "LIGHT_RAIL"],
    TransportMode.BUS: ["BUS"],
    TransportMode.TRAIN: ["TRAIN", "RAIL"],
}
AUTO_SLOWDOWN = 1.15  # auto-rickshaws are slower than cars; Google has no such mode


def decode_polyline(encoded: str) -> list[LatLng]:
    """Decode a Google encoded polyline (precision 5)."""
    points, index, lat, lng = [], 0, 0, 0
    while index < len(encoded):
        for coord in (0, 1):
            shift, result = 0, 0
            while True:
                b = ord(encoded[index]) - 63
                index += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if coord == 0:
                lat += delta
            else:
                lng += delta
        points.append(LatLng(lat=lat / 1e5, lng=lng / 1e5))
    return points


def _seconds(value: str | None) -> float | None:
    return float(value.rstrip("s")) if value else None


class GoogleRoutesProvider:
    source = DataSource.GOOGLE

    def __init__(self, client: GoogleClient):
        self._c = client

    def compute_route(self, origin: LatLng, destination: LatLng, mode: TransportMode,
                      departure: dt.datetime | None, city: CityContext) -> RouteResult:
        gmode = GOOGLE_MODE[mode]
        body: dict = {
            "origin": {"location": {"latLng": {"latitude": origin.lat, "longitude": origin.lng}}},
            "destination": {"location": {"latLng": {"latitude": destination.lat, "longitude": destination.lng}}},
            "travelMode": gmode,
            "computeAlternativeRoutes": False,
            "units": "METRIC",
        }
        now = dt.datetime.now(dt.timezone.utc)
        when = departure
        if when is not None and when.tzinfo is None:
            if city.utc_offset_minutes is None:
                when = None  # unknown local zone: use "now" rather than a wrong absolute time
            else:
                when = when.replace(tzinfo=dt.timezone(dt.timedelta(minutes=city.utc_offset_minutes)))
        when = when.astimezone(dt.timezone.utc) if when is not None else None
        if when is None or when <= now:
            when = now + dt.timedelta(minutes=1)
        if gmode == "DRIVE":
            body["routingPreference"] = "TRAFFIC_AWARE"
        if gmode in ("DRIVE", "TRANSIT"):
            body["departureTime"] = when.isoformat().replace("+00:00", "Z")
        if gmode == "TRANSIT":
            body["transitPreferences"] = {"allowedTravelModes": TRANSIT_FILTER[mode]}

        data = self._c.post(ROUTES_URL, body, FIELD_MASK)
        routes = data.get("routes") or []
        if not routes:
            return RouteResult(mode, 0, 0, None, False, [], self.source, available=False,
                               note=f"Google found no {mode.value} route")
        r = routes[0]
        try:
            dist_km = r.get("distanceMeters", 0) / 1000
            dur = (_seconds(r.get("duration")) or 0) / 60
            static = _seconds(r.get("staticDuration"))
        except (TypeError, ValueError) as exc:
            raise ProviderRequestError("Unexpected Routes API response shape") from exc
        if mode == TransportMode.AUTO:
            dur *= AUTO_SLOWDOWN
            static = static * AUTO_SLOWDOWN if static else None
        fare = None
        tf = (r.get("travelAdvisory") or {}).get("transitFare")
        if tf:
            fare = Money(amount=float(tf.get("units", 0)) + tf.get("nanos", 0) / 1e9, currency=tf.get("currencyCode", ""),
                         verified=True, source=self.source, note="Transit fare returned by Google Routes API")
        poly = (r.get("polyline") or {}).get("encodedPolyline")
        return RouteResult(
            mode=mode, distance_km=round(dist_km, 2), duration_min=round(dur, 1),
            duration_without_traffic_min=round(static / 60, 1) if static else None,
            traffic_aware=gmode == "DRIVE", polyline=decode_polyline(poly) if poly else [], source=self.source,
            fare=fare, note="Auto-rickshaw time derived from Google driving time x1.15" if mode == TransportMode.AUTO else None,
        )
