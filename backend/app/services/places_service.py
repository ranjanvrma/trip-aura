"""Places service: turns user interests and food preferences into provider queries,
then de-duplicates the results. Discovery queries for famous attractions are
always included so the itinerary can suggest places outside the user's interests.
"""
from __future__ import annotations

import logging

from app.core.geo import haversine_km
from app.providers.base import CityContext, PlaceQuery, PlacesProvider
from app.schemas.place import Place, PlaceKind
from app.schemas.trip import TripRequest

log = logging.getLogger(__name__)

INTEREST_QUERIES = {
    "museums": "museums", "monuments": "historical monuments", "cultural_centres": "cultural centres",
    "nature": "nature spots", "parks": "parks and gardens", "shopping": "shopping areas",
    "architecture": "architectural landmarks", "photography": "best photography spots",
    "adventure": "adventure activities", "history": "historical sites", "religious_sites": "temples and religious sites",
    "art": "art galleries", "markets": "local markets", "wildlife": "wildlife sanctuaries and zoos",
    "nightlife": "nightlife",
}
DIET_QUERIES = {
    "vegetarian": "vegetarian restaurants", "vegan": "vegan restaurants", "jain": "jain food restaurants",
    "eggetarian": "restaurants with egg dishes", "non_vegetarian": "non vegetarian restaurants",
}
FOOD_CATEGORY_QUERIES = {
    "cafes": "cafes", "street_food": "street food", "local_cuisine": "local cuisine restaurants",
    "budget_restaurants": "cheap restaurants", "fine_dining": "fine dining restaurants",
}


class PlacesService:
    def __init__(self, provider: PlacesProvider):
        self._p = provider

    @property
    def source(self):
        return self._p.source

    def _run(self, city: CityContext, queries: list[PlaceQuery]) -> list[Place]:
        seen: dict[str, Place] = {}
        for q in queries:
            for place in self._p.search(city, q):
                if haversine_km(city.center.lat, city.center.lng, place.location.lat, place.location.lng) > city.radius_km * 1.6:
                    continue
                existing = seen.get(place.id)
                if existing:
                    for tag in place.categories:
                        if tag not in existing.categories:
                            existing.categories.append(tag)
                    existing.is_famous = existing.is_famous or place.is_famous
                else:
                    seen[place.id] = place.model_copy(deep=True)
        return list(seen.values())

    def attraction_candidates(self, city: CityContext, req: TripRequest) -> list[Place]:
        cname = city.name.split(",")[0]
        queries = [PlaceQuery(text=f"top tourist attractions in {cname}", tag="famous", kind="attraction")]
        for interest in req.interests:
            phrase = INTEREST_QUERIES.get(interest, interest.replace("_", " "))
            queries.append(PlaceQuery(text=f"{phrase} in {cname}", tag=interest, kind="attraction"))
        queries.append(PlaceQuery(text=f"parks in {cname}", tag="parks", kind="attraction"))
        if self.source.value == "mock":
            queries.append(PlaceQuery(text="all", tag="all", kind="attraction", max_results=100))
        places = self._run(city, queries)
        return [p for p in places if p.kind in (PlaceKind.ATTRACTION, PlaceKind.PARK)]

    def food_candidates(self, city: CityContext, req: TripRequest) -> list[Place]:
        cname = city.name.split(",")[0]
        queries = [PlaceQuery(text=f"best restaurants in {cname}", tag="restaurants", kind="food")]
        for d in req.food_preferences:
            if d in DIET_QUERIES:
                queries.append(PlaceQuery(text=f"{DIET_QUERIES[d]} in {cname}", tag=d, kind="food"))
        for c in req.food_categories or ["local_cuisine", "cafes"]:
            phrase = FOOD_CATEGORY_QUERIES.get(c, c.replace("_", " "))
            queries.append(PlaceQuery(text=f"{phrase} in {cname}", tag=c, kind="food"))
        if self.source.value == "mock":
            queries.append(PlaceQuery(text="all", tag="all", kind="food", max_results=100))
        places = self._run(city, queries)
        return [p for p in places if p.kind in (PlaceKind.RESTAURANT, PlaceKind.CAFE)]

    def get_place(self, place_id: str) -> Place:
        return self._p.get_place(place_id)
