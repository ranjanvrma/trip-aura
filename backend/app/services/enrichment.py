"""Optional Google enrichment for open-data itineraries.

After the schedule is built from open data, each scheduled place (and the top
restaurant recommendations) is looked up with a Places API text search biased
to its exact location. A Google rating, review count and reviews are attached
ONLY when the Google result has a matching name within 250 m; otherwise the
place keeps "no rating". The schedule itself is not changed.
"""
from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.errors import TripAuraError
from app.core.geo import haversine_km
from app.core.text import fold
from app.providers.base import CityContext, PlaceQuery
from app.providers.google.places import GooglePlacesProvider
from app.schemas.common import DataSource
from app.schemas.place import Place

MAX_DISTANCE_KM = 0.25


def _tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", fold(name)) if len(t) > 2}


def names_match(a: str, b: str) -> bool:
    """True when two names plainly refer to the same place. A shared generic word is not enough: "Cafe" is not
    "Cafe Coffee Day", and "City Palace Museum" is not "City Cafe"."""
    na, nb = re.sub(r"[^a-z0-9]", "", fold(a)), re.sub(r"[^a-z0-9]", "", fold(b))
    if not na or not nb:
        return False
    short, long = sorted((na, nb), key=len)
    if short in long and len(short) >= 0.6 * len(long):
        return True
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    shared = len(ta & tb)
    few, many = sorted((len(ta), len(tb)))
    return shared / many >= 0.5 or (few >= 2 and shared == few)


NO_MATCH_TTL_S = 24 * 3600
_NO_MATCH: dict[str, float] = {}       # open-data place id -> when Google last had no match for it
_NO_MATCH_LOCK = threading.Lock()


def _known_no_match(place_id: str) -> bool:
    with _NO_MATCH_LOCK:
        t = _NO_MATCH.get(place_id)
        return t is not None and time.monotonic() - t < NO_MATCH_TTL_S


def _remember_no_match(place_id: str) -> None:
    with _NO_MATCH_LOCK:
        if len(_NO_MATCH) > 50_000:
            _NO_MATCH.clear()
        _NO_MATCH[place_id] = time.monotonic()


class GoogleEnricher:
    def __init__(self, places: GooglePlacesProvider):
        self.places = places
        self.matched = 0
        self.errors: list[str] = []
        self._lock = threading.Lock()
        self.stopped = False   # set after a quota or permission error: the remaining places are not tried

    def enrich_all(self, places: list[Place], city: CityContext, workers: int = 6) -> None:
        """Looks the places up in parallel. Each call only changes its own Place (a per-request copy)."""
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="enrich") as pool:
            list(pool.map(lambda p: self.enrich(p, city), places))

    def enrich(self, place: Place, city: CityContext) -> bool:
        if place.external_rating is not None and place.external_rating.provider == DataSource.GOOGLE:
            return True
        if self.stopped or _known_no_match(place.id):
            return False
        local_name = place.name.split(" (")[0]
        ctx = CityContext(name=city.name, center=place.location, country_code=city.country_code, radius_km=0.3,
                          has_metro=None, source=city.source)
        try:
            results = self.places.search(ctx, PlaceQuery(text=local_name, tag="enrich", kind="food" if place.diet else
                                                         "attraction", max_results=3))
        except TripAuraError as exc:
            with self._lock:
                self.errors.append(exc.message)
                if any(k in exc.message.lower() for k in ("429", "quota", "403", "permission")):
                    self.stopped = True
            return False
        for g in results:
            km = haversine_km(place.location.lat, place.location.lng, g.location.lat, g.location.lng)
            if km <= MAX_DISTANCE_KM and (names_match(local_name, g.name) or names_match(place.name, g.name)):
                place.external_rating = g.external_rating
                place.reviews = g.reviews or place.reviews
                place.google_maps_uri = g.google_maps_uri
                place.external_ids = {**place.external_ids, "google": g.id.removeprefix("g:")}  # no shared-dict mutation
                if g.price_level is not None:
                    place.price_level, place.price_level_estimated = g.price_level, False
                if (place.opening_hours is None or not place.opening_hours.known) and g.opening_hours \
                        and g.opening_hours.known:
                    # informational only: the schedule was built before enrichment
                    place.description = (place.description or "") + " (Google lists opening hours; verify before visiting)"
                with self._lock:
                    self.matched += 1
                return True
        _remember_no_match(place.id)
        return False
