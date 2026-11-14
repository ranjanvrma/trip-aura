"""Routes service: wraps the routes provider with a short-lived cache."""
from __future__ import annotations

import datetime as dt
import time

from app.providers.base import CityContext, RouteResult, RoutesProvider
from app.schemas.common import LatLng
from app.schemas.trip import TransportMode


MAX_ROUTES = 20_000


class RoutesService:
    def __init__(self, provider: RoutesProvider, ttl_seconds: int = 900):
        self._p = provider
        self._ttl = ttl_seconds
        self._cache: dict[tuple, tuple[float, RouteResult]] = {}

    def route(self, origin: LatLng, destination: LatLng, mode: TransportMode,
              departure: dt.datetime | None, city: CityContext, *, fresh: bool = False) -> RouteResult:
        bucket = departure.strftime("%Y%m%d%H") + str(departure.minute // 15) if departure else "none"
        key = (round(origin.lat, 5), round(origin.lng, 5), round(destination.lat, 5), round(destination.lng, 5),
               mode, bucket)
        hit = self._cache.get(key)
        if hit and not fresh and time.monotonic() - hit[0] < self._ttl:
            return hit[1]
        result = self._p.compute_route(origin, destination, mode, departure, city)
        if len(self._cache) >= MAX_ROUTES:   # drop what has expired; if that is not enough, start again
            now = time.monotonic()
            self._cache = {k: v for k, v in self._cache.items() if now - v[0] < self._ttl}
            if len(self._cache) >= MAX_ROUTES:
                self._cache.clear()
        self._cache[key] = (time.monotonic(), result)
        return result
