"""Open mode end to end with a fake city dataset and mocked HTTP (no network)."""
import datetime as dt
import json

import httpx
import pytest

from app.core.config import Settings
from app.providers.base import CityContext
from app.providers.heuristic_routes import HeuristicRoutesProvider
from app.providers.open.city_store import CityData, CityDataService, city_key
from app.providers.open.http import OpenHttp
from app.providers.open.providers import OpenGeocodingProvider, OpenPlacesProvider
from app.schemas.common import DataSource, LatLng, Money
from app.schemas.itinerary import DishSuggestion, ItemType
from app.schemas.place import DietInfo, OpeningHours, Place, PlaceKind, TimeRange
from app.schemas.trip import TransportMode, TripRequest
from app.services.enrichment import GoogleEnricher, names_match
from app.services.itinerary_service import ItineraryService
from app.services.providers import ProviderBundle
from app.core.config import DataMode

CITY = CityContext(name="Testopolis, Testland", center=LatLng(lat=45.0, lng=10.0), country_code="PT", radius_km=6,
                   has_metro=None, source=DataSource.OSM)
ALL_WEEK = OpeningHours(known=True, weekly={d: [TimeRange(open="08:00", close="22:00")] for d in range(7)},
                        source=DataSource.OSM)


def attraction(i, name, dlat, dlng, cats, prominence=None, famous=False, fee=None, minutes=60, kind=PlaceKind.ATTRACTION):
    return Place(id=f"osm:n{i}", name=name, kind=kind, categories=cats,
                 location=LatLng(lat=45.0 + dlat, lng=10.0 + dlng), typical_visit_minutes=minutes,
                 opening_hours=ALL_WEEK, prominence=prominence, is_famous=famous, entry_fee=fee,
                 source=DataSource.OSM)


def restaurant(i, name, dlat, dlng, veg=True, cafe=False):
    return Place(id=f"ovt:r{i}", name=name, kind=PlaceKind.CAFE if cafe else PlaceKind.RESTAURANT,
                 categories=["food", "cafes" if cafe else "local_cuisine"],
                 location=LatLng(lat=45.0 + dlat, lng=10.0 + dlng), opening_hours=ALL_WEEK,
                 price_level=1 if cafe else 2, price_level_estimated=True,
                 best_time=["breakfast", "lunch"] if cafe else ["breakfast", "lunch", "dinner"],
                 diet=DietInfo(vegetarian_options=veg, known=True, source=DataSource.OSM),
                 food_categories=["cafes"] if cafe else ["local_cuisine"], cuisines=["portuguese"],
                 source=DataSource.OVERTURE)


def fake_city_data() -> CityData:
    places = [
        attraction(1, "Grand Castle", 0.010, 0.010, ["monuments", "history"], 80, True,
                   Money(amount=10, currency="EUR", source=DataSource.OSM), 120),
        attraction(2, "City Museum", 0.002, -0.003, ["museums", "history"], 30, True, None, 90),
        attraction(3, "Old Square", -0.002, 0.002, ["architecture", "photography"], 8, False,
                   Money(amount=0, currency="USD", source=DataSource.ESTIMATE, note="Usually free"), 25),
        attraction(4, "River Park", -0.004, -0.004, ["parks", "nature"], None, False, None, 45, PlaceKind.PARK),
        attraction(5, "Art Gallery", 0.004, 0.001, ["art", "museums"], 12, False, None, 60),
        attraction(6, "Cathedral", 0.001, 0.004, ["religious_sites", "architecture"], 40, True, None, 40),
    ]
    places += [restaurant(10 + i, f"Cafe {i}", 0.001 * i, 0.001, cafe=True) for i in range(3)]
    places += [restaurant(20 + i, f"Tasca {i}", -0.001 * i, 0.002) for i in range(4)]
    places += [restaurant(30, "Meat House", 0.0, 0.0, veg=False)]
    stations = [{"name": "Centro", "lat": 45.0, "lng": 10.0, "kind": "metro"},
                {"name": "Castelo", "lat": 45.009, "lng": 10.009, "kind": "metro"}]
    dishes = [DishSuggestion(name="Pastel De Nata", status="guide", evidence=['Wikivoyage: "try pastel de nata"'],
                             evidence_source=DataSource.WIKIVOYAGE, mention_count=1),
              DishSuggestion(name="Mystery Stew", status="guide", evidence=["Wikivoyage"],
                             evidence_source=DataSource.WIKIVOYAGE, mention_count=1)]
    return CityData(key=city_key(CITY), name=CITY.name, places=places, stations=stations, guide_dishes=dishes,
                    sources=["Overture Maps (2026-10-21.0)", "Wikidata", "OpenStreetMap", "Wikivoyage (Testopolis)"],
                    built_at=dt.datetime.now(dt.timezone.utc))


class FixedGeo:
    source = DataSource.OSM

    def resolve_city(self, name):
        return CITY

    def geocode(self, query, city=None):
        from app.providers.base import GeocodeResult
        return GeocodeResult(LatLng(lat=45.0, lng=10.0), "Hotel, Testopolis", approximate=False, source=DataSource.OSM)


class FakeFx:
    rates = {"USD": 1.0, "EUR": 0.9, "INR": 85.0}

    def usd_to(self, c):
        return self.rates[c]

    def convert(self, a, s, d):
        return a / self.rates[s] * self.rates[d]

    def basis(self, src, dst):
        return "ECB reference rate"


@pytest.fixture
def open_service():
    settings = Settings(data_mode="open", google_maps_api_key="", ai_enabled=False)
    cities = CityDataService(settings, OpenHttp(settings))
    cities._memory[city_key(CITY)] = fake_city_data()
    bundle = ProviderBundle(DataMode.OPEN, DataSource.OPEN, OpenPlacesProvider(cities),
                            HeuristicRoutesProvider(cities.stations, DataSource.ESTIMATE), FixedGeo(),
                            {"cities": cities})
    return ItineraryService(bundle, settings, fx=FakeFx())


def request(**kw):
    base = {"accommodation": {"name_or_address": "Hotel"}, "destination_city": "Testopolis", "num_days": 2,
            "start_date": "2026-11-10", "budget": 500, "currency": "EUR", "interests": ["museums"],
            "food_preferences": ["vegetarian"], "transport_modes": ["walking", "metro", "cab"]}
    base.update(kw)
    return TripRequest.model_validate(base)


def test_open_itinerary_builds_with_labels(open_service):
    it = open_service.generate(request())
    assert it.data_source == DataSource.OPEN
    acts = [i for d in it.days for i in d.items if i.type == ItemType.ACTIVITY]
    assert acts and acts[0].place is not None
    assert any(i.place.name == "Grand Castle" for i in acts)          # famous anchor gets scheduled
    for i in acts:
        assert i.place.external_rating is None                          # open data has no ratings
    assert any("OpenStreetMap contributors" in a for a in it.attributions)
    assert any("Wikivoyage" in a for a in it.attributions)
    assert any("community open data" in d for d in it.disclaimers)


def test_open_itinerary_costs_in_trip_currency(open_service):
    it = open_service.generate(request(currency="USD"))
    castle = next(i for d in it.days for i in d.items if i.type == ItemType.ACTIVITY and i.place.name == "Grand Castle")
    assert castle.cost.currency == "USD" and castle.cost.amount == pytest.approx(10 / 0.9, abs=0.01)
    assert castle.cost.verified is False
    assert it.budget.currency == "USD"
    assert any("price index (PT)" in n for n in it.budget.notes)


def test_vegetarian_never_sent_to_meat_only_place(open_service):
    it = open_service.generate(request())
    meals = [i for d in it.days for i in d.items if i.type == ItemType.MEAL and i.place]
    assert meals and all(m.place.name != "Meat House" for m in meals)


def test_guide_dishes_filtered_by_diet(open_service):
    veg = [d.name for d in open_service.generate(request()).popular_dishes]
    assert "Pastel De Nata" in veg and "Mystery Stew" not in veg       # unknown ingredients hidden for vegetarians
    anyone = [d.name for d in open_service.generate(request(food_preferences=[])).popular_dishes]
    assert "Mystery Stew" in anyone


def test_metro_uses_city_stations():
    data = fake_city_data()
    routes = HeuristicRoutesProvider(lambda c: data.stations, DataSource.ESTIMATE)
    r = routes.compute_route(LatLng(lat=45.0, lng=10.0), LatLng(lat=45.009, lng=10.0095), TransportMode.METRO, None, CITY)
    assert r.available and "Centro -> Castelo" in r.note
    none = HeuristicRoutesProvider(lambda c: [], DataSource.ESTIMATE).compute_route(
        LatLng(lat=45.0, lng=10.0), LatLng(lat=45.01, lng=10.01), TransportMode.METRO, None, CITY)
    assert not none.available and "No metro stations" in none.note


def test_city_dataset_cache_roundtrip(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.database import Base
    from app.db import models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    Base.metadata.create_all(engine)
    settings = Settings(data_mode="open")
    svc = CityDataService(settings, OpenHttp(settings), sessionmaker(bind=engine))
    calls = []
    svc.build = lambda city: (calls.append(1), fake_city_data())[1]
    first = svc.get(CITY)
    svc._memory.clear()
    second = svc.get(CITY)                  # from SQLite, no rebuild
    assert len(calls) == 1 and len(second.places) == len(first.places)
    assert second.places[0].location == first.places[0].location


def test_nominatim_city_and_address_parsing():
    seen = []

    def handler(req: httpx.Request):
        seen.append(dict(req.url.params))
        if "Lisbon" == req.url.params.get("q"):
            return httpx.Response(200, json=[{"lat": "38.70", "lon": "-9.13", "addresstype": "city", "name": "Lisbon",
                                              "boundingbox": ["38.69", "38.79", "-9.23", "-9.09"],
                                              "address": {"country": "Portugal", "country_code": "pt"}}])
        return httpx.Response(200, json=[{"lat": "38.714", "lon": "-9.139", "place_rank": 30,
                                          "display_name": "Rossio, Lisbon"}])

    settings = Settings(data_mode="open")
    http = OpenHttp(settings, transport=httpx.MockTransport(handler))
    http._last_nominatim = -10  # skip the 1 req/s wait in tests
    geo = OpenGeocodingProvider(http)
    city = geo.resolve_city("Lisbon")
    assert city.name == "Lisbon, Portugal" and city.country_code == "PT" and 4 <= city.radius_km <= 20
    r = geo.geocode("Rossio", city)
    assert not r.approximate and r.location.lat == pytest.approx(38.714)
    assert "TripAura" in settings.open_user_agent and "viewbox" in seen[-1]


def test_names_match():
    assert names_match("Castelo de Sao Jorge", "Castelo de Sao Jorge Lisboa")      # containment
    assert names_match("Castelo de São Jorge", "Castelo de Sao Jorge")             # accents ignored
    assert names_match("Nicolau Cafe Lisboa", "Nicolau Cafe")
    assert names_match("Hard Rock Cafe", "Hard Rock Cafe Lisbon")
    assert not names_match("Cafe Central", "Museum of Art")
    assert not names_match("Cafe", "Bar")


def test_google_enrichment_only_on_close_name_match():
    from app.providers.google.client import GoogleClient
    from app.providers.google.places import GooglePlacesProvider

    def handler(req):
        body = json.loads(req.content)
        if body["textQuery"] == "City Museum":
            return httpx.Response(200, json={"places": [{
                "id": "g1", "displayName": {"text": "City Museum"}, "location": {"latitude": 45.0021, "longitude": 9.9971},
                "rating": 4.7, "userRatingCount": 900, "types": ["museum"]}]})
        return httpx.Response(200, json={"places": [{
            "id": "g2", "displayName": {"text": "Unrelated Bar"}, "location": {"latitude": 45.0, "longitude": 10.0},
            "rating": 3.1, "userRatingCount": 10, "types": ["bar"]}]})

    client = GoogleClient(Settings(google_maps_api_key="test"), transport=httpx.MockTransport(handler))
    enricher = GoogleEnricher(GooglePlacesProvider(client))
    museum = fake_city_data().places[1]
    park = fake_city_data().places[3]
    assert enricher.enrich(museum, CITY) is True
    assert museum.external_rating.provider == DataSource.GOOGLE and museum.external_rating.rating == 4.7
    assert enricher.enrich(park, CITY) is False and park.external_rating is None


def test_city_resolves_offline_from_index():
    from tests.test_nlp import make_index

    settings = Settings(data_mode="open")
    http = OpenHttp(settings, transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError("no network"))))
    geo = OpenGeocodingProvider(http, make_index())
    lisbon = geo.resolve_city("Lisboa")
    assert lisbon.name == "Lisbon, Portugal" and lisbon.country_code == "PT" and lisbon.radius_km == 7.0
    assert geo.resolve_city("Paris, United States").country_code == "US"
    assert geo.resolve_city("New York City").radius_km == 15.0


def test_parallel_build_survives_failing_sources(monkeypatch):
    from app.providers.open import overture, wikimedia

    settings = Settings(data_mode="open", wikivoyage_enabled=False, osm_time_budget_seconds=1)
    svc = CityDataService(settings, OpenHttp(settings))
    data = fake_city_data()
    monkeypatch.setattr(overture, "latest_release", lambda ua: "2026-10-21.0")
    monkeypatch.setattr(overture, "fetch", lambda *a, **k: (data.places, data.stations))
    monkeypatch.setattr(wikimedia, "wikidata_notable_places", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(svc.http, "overpass", lambda q, deadline=None: (_ for _ in ()).throw(RuntimeError("busy")))
    built = svc.build(CITY)
    assert len(built.places) == len(data.places) and built.stations == data.stations
    assert any("Wikidata was unavailable" in w for w in built.warnings)
    assert sum("OpenStreetMap" in w for w in built.warnings) == 3
    assert built.sources == ["Overture Maps (2026-10-21.0)"]


def test_trip_does_not_mutate_cached_city(open_service):
    cached = open_service.providers.extras["cities"].get(CITY)
    before = [(p.id, list(p.categories), dict(p.external_ids), p.external_rating) for p in cached.places]
    open_service.generate(request(interests=["museums", "history buff"]))
    after = [(p.id, list(p.categories), dict(p.external_ids), p.external_rating) for p in cached.places]
    assert before == after
