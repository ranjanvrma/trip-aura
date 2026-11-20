"""The day planner searches routes on a graph of places and travel times instead of taking the greedy next stop.
These compare it with the greedy route (a search that keeps one route per step) on the same trips."""
import math
import random
import time

import pytest

from app.engines import itinerary
from app.schemas.common import DataSource, LatLng
from app.schemas.place import OpeningHours, Place, PlaceKind, TimeRange
from app.schemas.trip import TripRequest

CENTRE = (26.9124, 75.7873)
TAGS = [["museums", "history"], ["monuments", "history"], ["parks", "nature"], ["architecture", "photography"]]


def city(seed: int, n: int) -> list[Place]:
    """A made-up city: sights scattered up to 9 km out, half with real opening hours, some on Wikidata."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        r, a = rng.uniform(0.2, 9), rng.uniform(0, 2 * math.pi)
        lat = CENTRE[0] + r / 111 * math.cos(a)
        lng = CENTRE[1] + r / (111 * math.cos(math.radians(CENTRE[0]))) * math.sin(a)
        tags = rng.choice(TAGS)
        hours = None
        if rng.random() < 0.5:
            o, c = rng.choice([8, 9, 10, 11]), rng.choice([13, 16, 17, 18, 20])
            hours = OpeningHours(known=True, source=DataSource.OSM,
                                 weekly={d: [TimeRange(open=f"{o:02d}:00", close=f"{c:02d}:00")] for d in range(7)})
        ids = {"overture": str(i)} | ({"wikidata": f"Q{100 + i}"} if rng.random() < 0.3 else {})
        out.append(Place(id=f"g{seed}-{i}", name=f"Sight {seed}-{i}", categories=tags,
                         kind=PlaceKind.PARK if "parks" in tags else PlaceKind.ATTRACTION,
                         location=LatLng(lat=lat, lng=lng), typical_visit_minutes=rng.choice([30, 45, 60, 90, 120]),
                         opening_hours=hours, prominence=rng.choice([None, 3, 8, 20]), external_ids=ids,
                         source=DataSource.OVERTURE))
    return out


def trip(days: int, pace: str, modes: list[str], **kw) -> TripRequest:
    return TripRequest(accommodation={"type": "hotel", "name_or_address": "Hotel on MI Road"},
                       destination_city="Jaipur", start_date="2026-11-10", num_days=days, budget=60000,
                       currency="INR", interests=["museums", "history", "parks", "monuments"], food_preferences=[],
                       food_categories=["local_cuisine"], transport_modes=modes, pace=pace, **kw)


CASES = [(seed, ["relaxed", "moderate", "packed"][seed % 3], [["walking", "auto"], ["walking"]][seed % 2])
         for seed in range(12)]


def plan(service, monkeypatch, places: list[Place], req: TripRequest, width: int):
    from app.services.places_service import PlacesService

    monkeypatch.setattr(PlacesService, "attraction_candidates", lambda self, c, r: list(places))
    monkeypatch.setattr(itinerary, "SEARCH_WIDTH", width)
    return service.generate(req)


def stops(itin) -> int:
    return sum(i.type == "activity" for d in itin.days for i in d.items)


def dropped(itin) -> int:
    return sum(u.reason.startswith(("Did not fit", "Would have")) for u in itin.unscheduled)


def test_the_route_search_fits_more_than_the_greedy_route(mock_service, monkeypatch):
    greedy_stops = search_stops = greedy_dropped = search_dropped = better = 0
    for seed, pace, modes in CASES:
        places, req = city(seed, 70), trip(3, pace, modes)
        greedy = plan(mock_service, monkeypatch, places, req, 1)
        search = plan(mock_service, monkeypatch, places, req, 16)
        greedy_stops, search_stops = greedy_stops + stops(greedy), search_stops + stops(search)
        greedy_dropped, search_dropped = greedy_dropped + dropped(greedy), search_dropped + dropped(search)
        better += stops(search) > stops(greedy)
    assert search_stops > greedy_stops and better >= 3, (greedy_stops, search_stops, better)
    assert search_dropped <= greedy_dropped     # and no more stops that break once real travel is known


def test_a_day_keeps_the_greedy_route_when_the_search_finds_nothing_better(mock_service, monkeypatch):
    """The greedy route is always tried, and the wider search's route replaces it only when it is worth more."""
    kept: list[tuple[float, float]] = []   # (greedy, wide) value of each day
    search, final = itinerary.ItineraryEngine._search, itinerary.ItineraryEngine._final
    runs: list[tuple[float, set[str]]] = []

    def spy_search(self, nodes, width, *args):
        route = search(self, nodes, width, *args)
        runs.append((final(self, route), {n.id for n in route.seq}))
        return route

    original_plan = itinerary.ItineraryEngine._plan_day

    def spy_plan(self, weekday, pool, used, want_park, must_quota=0):
        runs.clear()
        seq = original_plan(self, weekday, pool, used, want_park, must_quota)
        if len(runs) == 2:
            (greedy, greedy_ids), (wide, wide_ids) = runs
            assert {c.place.id for c in seq} == (wide_ids if wide > greedy + itinerary.SEARCH_MARGIN else greedy_ids)
            kept.append((greedy, wide))
        return seq

    monkeypatch.setattr(itinerary.ItineraryEngine, "_search", spy_search)
    monkeypatch.setattr(itinerary.ItineraryEngine, "_plan_day", spy_plan)
    for seed, pace, modes in CASES[:6]:
        plan(mock_service, monkeypatch, city(seed, 70), trip(3, pace, modes), 16)
    assert kept
    assert any(wide > greedy + 0.01 for greedy, wide in kept)      # the search finds better days
    assert any(wide < greedy - 0.01 for greedy, wide in kept)      # and sometimes not (its timing is padded)


def test_a_long_trip_in_a_large_city_plans_quickly(mock_service, monkeypatch):
    places, req = city(99, 150), trip(7, "packed", ["walking", "auto"])
    started = time.perf_counter()
    itin = plan(mock_service, monkeypatch, places, req, 16)
    assert time.perf_counter() - started < 3.0
    assert all(any(i.type == "activity" for i in d.items) for d in itin.days)


@pytest.mark.parametrize("width", [1, 16])
def test_must_sees_still_come_first(mock_service, monkeypatch, width):
    places = city(5, 60)
    far = places[7].model_copy(update={"location": LatLng(lat=CENTRE[0] + 0.07, lng=CENTRE[1])})
    places[7] = far
    req = trip(2, "moderate", ["walking", "auto"],
               must_see=[{"name": far.name, "location": {"lat": far.location.lat, "lng": far.location.lng}}])
    itin = plan(mock_service, monkeypatch, places, req, width)
    assert far.name in [i.title for d in itin.days for i in d.items if i.type == "activity"]
