"""Open-data layer: OSM tag parsing, opening hours, fees, Overture rows, Wikidata classification,
Wikivoyage dish extraction, merging, cost model and FX. No network (httpx.MockTransport)."""
import httpx
import pytest

from app.core.errors import ProviderRequestError
from app.core.text import fold
from app.engines.costs import CostModel
from app.providers.open import osm
from app.providers.open.city_store import merge_places
from app.providers.open.overture import row_to_place
from app.providers.open.wikimedia import _classify, extract_dishes
from app.schemas.common import DataSource, LatLng, Money
from app.schemas.place import Place, PlaceKind
from app.schemas.trip import TransportMode
from app.services.fx_service import FxService


# ---------------------------------------------------------------- opening hours
def hours(v):
    return {d: [(r.open, r.close) for r in rs] for d, rs in osm.parse_opening_hours(v).weekly.items()}


def test_hours_simple_and_off():
    h = hours("Mo-Fr 09:00-17:00; Sa 10:00-14:00; Su off")
    assert h[0] == [("09:00", "17:00")] and h[4] == [("09:00", "17:00")]
    assert h[5] == [("10:00", "14:00")] and h[6] == []


def test_hours_split_and_wraparound_days():
    h = hours("Tu-Su 10:00-13:00,14:00-18:00")
    assert h[1] == [("10:00", "13:00"), ("14:00", "18:00")] and 0 not in h
    assert hours("Fr-Mo 12:00-20:00")[6] == [("12:00", "20:00")]


def test_hours_overnight_spills_to_next_day():
    h = hours("Fr,Sa 18:00-02:00")
    assert h[4] == [("18:00", "24:00")]
    assert ("00:00", "02:00") in h[5] and ("00:00", "02:00") in h[6]


def test_hours_24_7_daily_and_unknown():
    assert hours("24/7")[3] == [("00:00", "24:00")]
    assert hours("09:00-18:00")[2] == [("09:00", "18:00")]
    assert osm.parse_opening_hours("Apr-Oct: Mo-Su 09:00-19:00").known is False   # seasons unsupported
    assert osm.parse_opening_hours("sunrise-sunset").known is False
    assert osm.parse_opening_hours(None).known is False


def test_later_rule_overrides_earlier():
    h = hours("Mo-Su 09:00-18:00; We off")
    assert h[2] == [] and h[3] == [("09:00", "18:00")]


# ------------------------------------------------------------------------ fees
def test_fee_parsing():
    assert osm.parse_fee({"fee": "no"}).amount == 0
    m = osm.parse_fee({"fee": "yes", "charge": "15 EUR"})
    assert (m.amount, m.currency, m.verified) == (15.0, "EUR", False)
    assert osm.parse_fee({"charge": "€12.50"}).amount == 12.5
    assert osm.parse_fee({"fee": "yes"}) is None
    free = osm.parse_fee({"tourism": "viewpoint"})
    assert free.amount == 0 and free.source == DataSource.ESTIMATE and "Usually free" in free.note


# ------------------------------------------------------------------- elements
def el(tags, typ="node", i=1, lat=38.7, lon=-9.1):
    return {"type": typ, "id": i, "lat": lat, "lon": lon, "tags": tags}


def test_osm_restaurant_diet_and_categories():
    p = osm.element_to_place(el({"amenity": "restaurant", "name": "Casa", "cuisine": "portuguese;seafood",
                                 "diet:vegetarian": "yes", "opening_hours": "Mo-Su 12:00-23:00"}), {"portuguese"})
    assert p.kind == PlaceKind.RESTAURANT and "local_cuisine" in p.food_categories
    assert p.diet.known and p.diet.vegetarian_options and p.diet.non_veg
    assert p.price_level_estimated and p.opening_hours.known and p.source == DataSource.OSM


def test_osm_filters_noise_and_maps_interests():
    assert osm.element_to_place(el({"tourism": "attraction", "name": "Some tree"}), set()) is None
    assert osm.element_to_place(el({"historic": "memorial", "name": "Plaque"}), set()) is None
    museum = osm.element_to_place(el({"tourism": "museum", "name": "Museu", "wikidata": "Q1", "fee": "no"}), set())
    assert {"museums", "history"} <= set(museum.categories) and museum.typical_visit_minutes == 90
    assert museum.external_ids["wikidata"] == "Q1" and museum.entry_fee.amount == 0
    park = osm.element_to_place(el({"leisure": "park", "name": "Parque", "name:en": "Park"}), set())
    assert park.kind == PlaceKind.PARK and park.name == "Park (Parque)"


def test_osm_stations():
    places, stations = osm.parse_elements([el({"railway": "station", "station": "subway", "name": "Baixa"}),
                                           el({"railway": "station", "name": "Santa Apolonia"}, i=2)], set())
    assert not places and {s["kind"] for s in stations} == {"metro", "train"}


# -------------------------------------------------------------------- overture
def test_overture_rows():
    food = row_to_place(("a1", "Tasca", "restaurant", "portuguese_restaurant", ["restaurant", "portuguese_restaurant"],
                         0.9, -9.1, 38.7, "http://x", "CDLA-Permissive-2.0", None, None), {"portuguese"})
    assert food.kind == PlaceKind.RESTAURANT and food.cuisines == ["portuguese"] and "local_cuisine" in food.categories
    assert food.opening_hours.known is False and food.source == DataSource.OVERTURE
    chain = row_to_place(("a2", "Starbucks", "coffee_shop", "coffee_shop", [], 0.99, 0, 0, None, "", None, "Starbucks"),
                         set())
    assert chain.kind == PlaceKind.CAFE and chain.external_ids["brand"] == "Starbucks"
    en = row_to_place(("a3", "東京駅", "museum", "museum", [], 0.9, 139, 35, None, "", "Tokyo Museum", None),
                      set())
    assert en.name.startswith("Tokyo Museum (") and "museums" in en.categories
    plaza = row_to_place(("a4", "Praca", "public_plaza", "public_plaza", [], 0.9, 0, 0, None, "", None, None), set())
    assert plaza.entry_fee.amount == 0 and "assumption" in plaza.entry_fee.note
    station = row_to_place(("a5", "Shinjuku", "train_station", None, [], 0.9, 139, 35, None, "", None, None), set())
    assert station == {"name": "Shinjuku", "lat": 35, "lng": 139, "kind": "rail"}
    assert row_to_place(("a6", "Gas", "gas_station", None, [], 0.9, 0, 0, None, "", None, None), set()) is None


# ---------------------------------------------------------------- wikimedia
def test_wikidata_type_classification():
    assert "museums" in _classify(["art museum"])[0]
    assert "religious_sites" in _classify(["cathedral", "tourist attraction"])[0]
    assert _classify(["metro station"]) is None
    assert _classify(["human settlement"]) is None
    assert _classify(["city gate"]) is not None


def test_wikivoyage_dish_extraction():
    wikitext = """== Eat ==
Lisbon is famous for its pastries, above all the ''pastéis de nata'', a custard tart best eaten warm.
Try ''bacalhau'' (salted cod), served in many ways. '''Chiado''' has many restaurants.
{{eat | name=Restaurant X | content=good '''sardines''' }}
For a snack, ''bifana'' is a pork sandwich."""
    wikitext += "\nRide the old ''eléctrico'' 28 to the hills, and expect a ''couvert'' of bread when you sit down."
    found = dict(extract_dishes(wikitext, {"pastel de nata", "pasteis de nata", "bacalhau", "sardines", "bifana"}))
    assert "pastel de nata" in found and "pasteis de nata" not in found   # plural collapsed onto one name
    assert "bacalhau" in found and "bifana" in found
    assert "chiado" not in found                 # bold Title Case place names are ignored
    assert "sardines" not in found               # text inside listing templates is ignored
    assert "eletrico" not in found and "couvert" not in found   # italic non-dishes ignored
    assert "custard" in found["pastel de nata"]
    assert fold("Pastéis") == "pasteis"


def test_wikidata_charged_types_not_assumed_free():
    from app.providers.open import wikimedia

    assert any(k in "national monument|monastery" for k in wikimedia.CHARGED_KEYS)
    assert not any(k in "square|tourist attraction" for k in wikimedia.CHARGED_KEYS)


# --------------------------------------------------------------------- merging
def P(pid, name, lat, lng, kind=PlaceKind.ATTRACTION, **kw):
    return Place(id=pid, name=name, kind=kind, location=LatLng(lat=lat, lng=lng), source=DataSource.OVERTURE, **kw)


def test_merge_enriches_matches_and_adds_others():
    from app.schemas.place import OpeningHours, TimeRange

    base = [P("ovt:1", "Castelo de Sao Jorge", 38.7139, -9.1335)]
    osm_hours = OpeningHours(known=True, weekly={0: [TimeRange(open="09:00", close="18:00")]}, source=DataSource.OSM)
    extra = [P("osm:n1", "Castelo de São Jorge", 38.7140, -9.1336, opening_hours=osm_hours, prominence=60),
             P("osm:n2", "Different Museum", 38.7141, -9.1337)]
    out = merge_places(base, extra, max_m=200)
    assert len(out) == 2
    castle = next(p for p in out if p.id == "ovt:1")
    assert castle.opening_hours.known and castle.prominence == 60


def test_merge_respects_distance_and_kind():
    base = [P("a", "Central", 38.7, -9.1)]
    far = [P("b", "Central", 38.71, -9.1)]                                   # ~1.1 km away
    food = [P("c", "Central", 38.7, -9.1, kind=PlaceKind.RESTAURANT)]       # different kind
    assert len(merge_places(base, far, max_m=150)) == 2
    assert len(merge_places(base, food, max_m=150)) == 2


# ----------------------------------------------------------------- costs / fx
class FakeFx:
    rates = {"USD": 1.0, "EUR": 0.9, "JPY": 150.0, "INR": 85.0}

    def usd_to(self, c):
        return self.rates[c]

    def convert(self, amount, src, dst):
        return amount / self.rates[src] * self.rates[dst]

    def basis(self, src, dst):
        return "ECB reference rate"


def test_cost_model_scales_by_country_and_currency():
    us = CostModel.build("US", "USD")
    jp = CostModel.build("JP", "JPY", FakeFx())
    assert jp.meal(2) == pytest.approx(us.meal(2) * 0.75 * 150)
    assert jp.fare(TransportMode.CAB, 5).currency == "JPY"
    unknown = CostModel.build("ZZ", "USD")
    assert unknown.notes and unknown.meal(1) == pytest.approx(us.meal(1) * 0.7)


def test_curated_india_table_converted():
    inr = CostModel.build("IN", "INR")
    usd = CostModel.build("IN", "USD", FakeFx())
    assert inr.fare(TransportMode.CAB, 0.1).amount == 100
    assert usd.fare(TransportMode.CAB, 0.1).amount == pytest.approx(100 / 85, abs=0.01)


def test_money_conversion_marks_estimate():
    cm = CostModel.build("PT", "USD", FakeFx())
    m = cm.to_trip_currency(Money(amount=9, currency="EUR", verified=True, source=DataSource.OSM))
    assert m.currency == "USD" and m.amount == pytest.approx(10) and m.verified is False
    assert cm.to_trip_currency(Money(amount=0, currency="EUR")).amount == 0


def test_fx_service_parses_and_fails_loudly():
    ok = FxService("https://fx.test/latest", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"base": "USD", "date": "2026-11-06", "rates": {"EUR": 0.9, "INR": 85}})))
    assert ok.usd_to("EUR") == 0.9 and ok.convert(85, "INR", "EUR") == pytest.approx(0.9)
    bad = FxService("https://fx.test/latest", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(ProviderRequestError):
        bad.usd_to("EUR")


def _two_source_fx(ecb_ok: bool = True, open_ok: bool = True) -> FxService:
    def handler(r: httpx.Request) -> httpx.Response:
        if r.url.host == "ecb.test":
            ok = httpx.Response(200, json={"date": "2026-11-13", "rates": {"EUR": 0.9}})
            return ok if ecb_ok else httpx.Response(500)
        return (httpx.Response(200, json={"result": "success", "rates": {"USD": 1, "EUR": 0.95, "PKR": 280}})
                if open_ok else httpx.Response(503))
    return FxService("https://ecb.test/latest", "https://open.test/latest/USD", transport=httpx.MockTransport(handler))


def test_fx_covers_every_currency_and_prefers_ecb():
    fx = _two_source_fx()
    assert fx.usd_to("EUR") == 0.9                      # ECB wins over the open source
    assert fx.usd_to("PKR") == 280                      # only the open source has it
    assert fx.basis("USD", "EUR") == "ECB reference rate"
    assert fx.basis("EUR", "PKR") == "ExchangeRate-API rate"
    assert _two_source_fx(ecb_ok=False).usd_to("PKR") == 280 and _two_source_fx(open_ok=False).usd_to("EUR") == 0.9
    with pytest.raises(ProviderRequestError):
        _two_source_fx(ecb_ok=False, open_ok=False).usd_to("PKR")


def test_every_country_currency_is_accepted():
    from app.core.currencies import COUNTRY_CURRENCY, SUPPORTED_CURRENCIES, currency_for_country
    from app.schemas.trip import TripRequest

    assert currency_for_country("pk") == "PKR" and currency_for_country("FR") == "EUR"
    assert currency_for_country("ZZ") is None
    assert set(COUNTRY_CURRENCY.values()) == set(SUPPORTED_CURRENCIES)
    assert len(SUPPORTED_CURRENCIES) == len(set(SUPPORTED_CURRENCIES)) > 140
    req = TripRequest(destination_city="Karachi", accommodation={"type": "hotel", "name_or_address": "Saddar"},
                      start_date="2026-12-01", num_days=2, travelers=1, budget=90000, currency="pkr")
    assert req.currency == "PKR"
