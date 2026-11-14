"""Regression tests for defects found in the full code review (v2.3.0). All offline."""
import datetime as dt

import pytest
from pydantic import ValidationError

from app.core.ratelimit import ip_route_class
from app.engines.pace import LUNCH_WINDOW
from app.engines.transport import TransportWeights, choose, score_options
from app.providers.open import osm
from app.providers.open.city_store import CityData, CityDataService
from app.providers.open.http import OpenHttp
from app.core.config import Settings
from app.schemas.common import DataSource, Money
from app.schemas.itinerary import TransportOption
from app.schemas.trip import TransportMode, TripRequest
from app.services.enrichment import names_match


@pytest.mark.parametrize("charge, local, expected", [
    ("ADULT 12 EUR", "EUR", (12.0, "EUR")),      # "ULT" inside a word is not a currency code
    ("1,500 JPY", "JPY", (1500.0, "JPY")),       # thousands separator, not a decimal point
    ("10.000 IDR", "IDR", (10000.0, "IDR")),
    ("1.500,50 EUR", "EUR", (1500.5, "EUR")),
    ("12,50 €", "EUR", (12.5, "EUR")),
    ("$10000", "COP", (10000.0, "COP")),         # pesos, not US dollars
    ("$10", "EUR", (10.0, "USD")),
    ("200", "PKR", (200.0, "PKR")),              # a bare number is in the local money
    ("5 DEM", "EUR", None),                      # a currency that no longer exists: fee unknown
    ("200", None, None),
])
def test_osm_charge_parsing(charge, local, expected):
    fee = osm.parse_fee({"charge": charge, "tourism": "museum"}, local)
    assert (None if fee is None else (fee.amount, fee.currency)) == expected


def test_unreadable_charge_is_not_assumed_free():
    assert osm.parse_fee({"charge": "see website", "tourism": "viewpoint"}, "EUR") is None


def _option(mode, minutes, practical, cost=0.0):
    return TransportOption(mode=mode, distance_km=200, duration_min=minutes, practical=practical, score=0,
                           cost=Money.estimate(cost, "INR"), source=DataSource.ESTIMATE)


def test_unavailable_mode_is_never_the_fastest_or_chosen():
    metro = _option(TransportMode.METRO, 0, False)             # no station near either end
    cab = _option(TransportMode.CAB, 240, False, 4000)         # impractical, but it exists
    score_options([metro, cab], {TransportMode.METRO}, TransportWeights())
    assert metro.score == 0 and 0 < cab.score <= 1
    assert choose([metro, cab], {TransportMode.METRO})[0] is cab


@pytest.mark.parametrize("a, b, same", [
    ("Cafe", "Cafe Coffee Day", False),
    ("City Palace Museum", "City Cafe", False),
    ("Hotel Royal Palace", "Royal Bakery", False),
    ("Hawa Mahal", "Hawa Mahal - Palace of Winds", True),
    ("Louvre", "Louvre Museum", True),
    ("Pastéis de Belém", "Pasteis de Belem", True),
])
def test_google_name_matching_needs_more_than_a_shared_word(a, b, same):
    assert names_match(a, b) is same


def test_route_comparison_shares_the_generation_limit():
    assert ip_route_class("POST", "/api/routes/compare") == "generate"


def test_far_future_start_date_is_rejected(client, base_request):
    with pytest.raises(ValidationError):
        TripRequest.model_validate({**base_request, "start_date": "9999-12-25"})
    late = {**base_request, "start_date": "9999-12-25", "num_days": 14}
    assert client.post("/api/trips/preview", json=late).status_code == 422


def test_route_comparison_with_an_unknown_currency_is_a_client_error(client):
    body = {"city": "Jaipur", "currency": "XYZ", "modes": ["cab"], "origin": {"lat": 26.92, "lng": 75.8},
            "destination": {"lat": 26.93, "lng": 75.82}}
    r = client.post("/api/routes/compare", json=body)
    assert 400 <= r.status_code < 500


def test_long_trip_keeps_lunch_at_lunchtime_and_totals_add_up(client, base_request):
    r = client.post("/api/trips/preview", json={**base_request, "num_days": 14, "budget": 200000, "pace": "packed"})
    assert r.status_code == 200, r.text
    data = r.json()
    total = 0.0
    rested, visited = set(), set()
    for day in data["days"]:
        for item in day["items"]:
            hh, mm = item["start"].split(":")
            if item.get("meal_type") == "lunch":
                assert int(hh) * 60 + int(mm) >= LUNCH_WINDOW[0], (day["day_number"], item["start"])
            if item["type"] == "travel":
                total += item["travel"]["chosen"]["cost"]["amount"]
            elif item.get("cost"):
                total += item["cost"]["amount"]
            if item.get("place") and item["type"] == "rest":
                rested.add(item["place"]["id"])
            if item.get("place") and item["type"] == "activity":
                visited.add(item["place"]["id"])
    assert total == pytest.approx(data["budget"]["planned_total"], abs=0.5)   # every shown cost is in the total
    assert not rested & visited                                               # a park is a rest or a sight, not both


def test_a_city_built_while_a_source_was_down_expires_after_a_day():
    settings = Settings(data_mode="open")
    svc = CityDataService(settings, OpenHttp(settings))
    now = dt.datetime.now(dt.timezone.utc)

    def city(warnings, age):
        return CityData(key="k", name="X", places=[], stations=[], guide_dishes=[], sources=[], warnings=warnings,
                        built_at=now - age, wikivoyage_title=None)

    down = ["Wikidata was unavailable, so 'famous place' detection is limited."]
    assert svc._fresh(city([], dt.timedelta(days=20)))
    assert svc._fresh(city(down, dt.timedelta(hours=3)))
    assert not svc._fresh(city(down, dt.timedelta(days=2)))
    assert not svc._fresh(city([], dt.timedelta(days=settings.city_cache_days + 1)))


# ---------------------------------------------------------------- second round (v2.3.1)
def _minutes(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


@pytest.mark.parametrize("pace", ["relaxed", "moderate", "packed"])
def test_lunch_never_slips_past_mid_afternoon(client, base_request, pace):
    from app.engines.itinerary import LATEST_LUNCH_START

    data = client.post("/api/trips/preview", json={**base_request, "num_days": 6, "pace": pace}).json()
    starts = [_minutes(i["start"]) for d in data["days"] for i in d["items"] if i.get("meal_type") == "lunch"]
    assert starts and all(LUNCH_WINDOW[0] - 60 <= s <= LATEST_LUNCH_START for s in starts), starts


def test_a_far_away_stay_has_dinner_near_it_and_no_late_ride(client, base_request):
    # about 45 km outside the Jaipur demo data
    stay = {"type": "hotel", "name_or_address": "Far Farm Stay", "location": {"lat": 27.32, "lng": 75.82}}
    data = client.post("/api/trips/preview", json={**base_request, "accommodation": stay,
                                                   "transport_modes": ["cab"]}).json()
    for day in data["days"]:
        times = [_minutes(i["start"]) for i in day["items"]]
        assert times == sorted(times), (day["day_number"], [i["start"] for i in day["items"]])   # nothing wraps
        end = day["items"][-1]
        assert end["type"] == "end" and _minutes(end["start"]) <= 23 * 60, end["start"]
        dinner = next(i for i in day["items"] if i.get("meal_type") == "dinner")
        after = day["items"][day["items"].index(dinner):]
        assert all(i["travel"]["chosen"]["duration_min"] <= 30 for i in after if i["type"] == "travel")


def test_a_park_rest_has_a_way_to_get_there(client, base_request):
    data = client.post("/api/trips/preview", json={**base_request, "num_days": 6, "pace": "relaxed"}).json()
    for day in data["days"]:
        items = day["items"]
        for k, item in enumerate(items):
            if item["type"] == "rest" and item.get("place"):
                before = items[k - 1]
                there = item["place"]["location"]
                arrived = ((before["type"] == "travel" and before["travel"]["destination"] == there)
                           or (before.get("place") or {}).get("location") == there)
                assert arrived, (day["day_number"], item["title"], before["title"])


def test_meal_ranking_picks_what_full_scoring_would():
    """The scheduler ranks restaurants with plain arithmetic; it must agree with the full score every time."""
    from app.core.geo import haversine_km
    from app.engines.food import FoodEngine, is_open_for
    from app.engines.recommendation import ScoringContext, score_food_place
    from app.providers.mock.providers import _all_places
    from app.schemas.common import LatLng

    places = [p for p in _all_places().values() if p.kind.value in ("restaurant", "cafe")]
    assert places
    req = TripRequest(destination_city="Jaipur", accommodation={"type": "hotel", "name_or_address": "MI Road"},
                      num_days=2, budget=12000, currency="INR", food_preferences=["vegetarian"])
    ctx = ScoringContext(req=req, origin=LatLng(lat=26.92, lng=75.81), weekdays=[1, 2])
    engine = FoodEngine(ctx, places)
    for lat, lng, meal, minute in [(26.92, 75.81, "lunch", 780), (26.90, 75.80, "dinner", 1170),
                                   (26.95, 75.85, "breakfast", 560), (26.88, 75.78, "lunch", 800)]:
        near = LatLng(lat=lat, lng=lng)
        got = engine.pick(meal, near, minute, 1, set(), max_km=1.5)
        best = None
        for radius in (1.5, 3.0, 6.0):
            for c in engine.candidates:
                p = c.place
                if (p.best_time and meal not in p.best_time) or not is_open_for(p, 1, minute, 45):
                    continue
                if haversine_km(lat, lng, p.location.lat, p.location.lng) > radius:
                    continue
                s = score_food_place(p, ctx, c.food_match, c.check.reasons, origin=near)
                if best is None or s.score > best[0]:
                    best = (s.score, p.id)
            if best:
                break
        assert (got[0].place.id if got else None) == (best[1] if best else None)


def test_cheaper_restaurant_step_also_filters_estimated_prices():
    from app.engines.food import FoodEngine
    from app.engines.recommendation import ScoringContext
    from app.schemas.common import LatLng
    from app.schemas.place import DietInfo, OpeningHours, Place, PlaceKind, TimeRange

    hours = OpeningHours(known=True, weekly={d: [TimeRange(open="08:00", close="23:00")] for d in range(7)},
                         source=DataSource.OSM)

    def place(i, level):
        return Place(id=f"r{i}", name=f"Place {i}", kind=PlaceKind.RESTAURANT, categories=["food"],
                     location=LatLng(lat=26.92, lng=75.81 + i * 0.001), opening_hours=hours, price_level=level,
                     price_level_estimated=True, best_time=["lunch"], source=DataSource.OSM,
                     diet=DietInfo(vegetarian_options=True, known=True, source=DataSource.OSM))

    req = TripRequest(destination_city="Jaipur", accommodation={"type": "hotel", "name_or_address": "MI Road"},
                      num_days=1, budget=100000, currency="INR")
    ctx = ScoringContext(req=req, origin=LatLng(lat=26.92, lng=75.81), weekdays=[1])
    engine = FoodEngine(ctx, [place(1, 4), place(2, 1)])
    picked = engine.pick("lunch", LatLng(lat=26.92, lng=75.81), 780, 1, set(), max_cost=ctx.costs.meal(2))
    assert picked is not None and picked[0].place.id == "r2"           # the price level 4 place is over the cap


def test_osrm_failures_fall_back_to_an_estimate_and_pause():
    from app.core.errors import ProviderRequestError
    from app.providers.base import CityContext
    from app.providers.heuristic_routes import HeuristicRoutesProvider
    from app.providers.open.providers import OsrmRoutesProvider
    from app.schemas.common import LatLng

    calls = []

    class DownHttp:
        def get_json(self, *a, **k):
            calls.append(1)
            raise ProviderRequestError("OSRM routing: could not connect (ConnectTimeout)")

    city = CityContext(name="Jaipur", center=LatLng(lat=26.92, lng=75.81), country_code="IN", radius_km=8,
                       has_metro=None, source=DataSource.OSM)
    osrm = OsrmRoutesProvider(DownHttp(), "https://osrm.test/driving", "https://osrm.test/walking",
                              HeuristicRoutesProvider(lambda city: [], DataSource.ESTIMATE))
    a, b = LatLng(lat=26.92, lng=75.81), LatLng(lat=26.95, lng=75.84)
    for _ in range(5):
        r = osrm.compute_route(a, b, TransportMode.CAB, None, city)
        assert r.available and r.duration_min > 0 and "estimated" in r.note
    assert len(calls) == 3                                               # paused after three failures


def test_google_lookups_stop_after_a_quota_error():
    from app.core.errors import TripAuraError
    from app.providers.base import CityContext
    from app.schemas.common import LatLng
    from app.schemas.place import Place, PlaceKind
    from app.services.enrichment import GoogleEnricher

    calls = []

    class Quota:
        def search(self, city, query):
            calls.append(query.text)
            raise TripAuraError("Google Places: HTTP 429 quota exceeded")

    city = CityContext(name="Jaipur", center=LatLng(lat=26.92, lng=75.81), country_code="IN", radius_km=8,
                       has_metro=None, source=DataSource.OSM)
    places = [Place(id=f"q{i}", name=f"Sight {i}", kind=PlaceKind.ATTRACTION, location=LatLng(lat=26.9, lng=75.8),
                    source=DataSource.OSM) for i in range(30)]
    enricher = GoogleEnricher(Quota())
    enricher.enrich_all(places, city, workers=1)
    assert enricher.stopped and len(calls) == 1 and enricher.matched == 0


def test_a_degraded_city_is_rebuilt_once_in_the_background():
    import threading

    settings = Settings(data_mode="open")
    svc = CityDataService(settings, OpenHttp(settings))
    built = threading.Event()
    calls = []
    now = dt.datetime.now(dt.timezone.utc)
    old = CityData(key="k", name="X", places=[], stations=[], guide_dishes=[], sources=[],
                   warnings=["Wikidata was unavailable, so famous place detection is limited."],
                   built_at=now - dt.timedelta(hours=2), wikivoyage_title=None)
    fresh = CityData(key="k", name="X", places=[], stations=[], guide_dishes=[], sources=["Wikidata"], warnings=[],
                     built_at=now, wikivoyage_title=None)
    svc.build = lambda city: (calls.append(1), built.set(), fresh)[2]
    svc._save = lambda data: None
    svc._retry_if_degraded(None, old)
    svc._retry_if_degraded(None, old)                                  # a second request does not start another
    assert built.wait(5)
    for _ in range(100):
        if svc._memory.get("k") is fresh:
            break
        threading.Event().wait(0.02)
    assert svc._memory.get("k") is fresh and len(calls) == 1
