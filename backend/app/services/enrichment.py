"""Optional Google enrichment for open-data itineraries.

After the schedule is built from open data, each scheduled place (and the top
restaurant recommendations) is looked up with a Places API text search biased
to its exact location. A Google rating, review count and reviews are attached
ONLY when the Google result has a matching name within 250 m; otherwise the
place keeps "no rating". The schedule itself is not changed.
"""
from __future__ import annotations

import re

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
    na, nb = re.sub(r"[^a-z0-9]", "", fold(a)), re.sub(r"[^a-z0-9]", "", fold(b))
    if na and nb and (na in nb or nb in na):
        return True
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.5


class GoogleEnricher:
    def __init__(self, places: GooglePlacesProvider):
        self.places = places
        self.matched = 0
        self.errors: list[str] = []

    def enrich(self, place: Place, city: CityContext) -> bool:
        if place.external_rating is not None and place.external_rating.provider == DataSource.GOOGLE:
            return True
        local_name = place.name.split(" (")[0]
        ctx = CityContext(name=city.name, center=place.location, country_code=city.country_code, radius_km=0.3,
                          has_metro=None, source=city.source)
        try:
            results = self.places.search(ctx, PlaceQuery(text=local_name, tag="enrich", kind="food" if place.diet else
                                                         "attraction", max_results=3))
        except TripAuraError as exc:
            self.errors.append(exc.message)
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
                self.matched += 1
                return True
        return False
