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
