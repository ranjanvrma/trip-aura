"""Picking real, well-known places from open data alone: non-eateries, diet hints in names, notability, minor parks
and non-sights. Examples are the ones that went wrong in a real Hisar plan."""
from app.engines.food import FoodEngine, diet_check
from app.engines.quality import is_minor_park, looks_like_eatery, looks_like_sight, name_diet_hint, notability
from app.engines.recommendation import ScoringContext
from app.schemas.common import DataSource, LatLng
from app.schemas.place import DietInfo, Place, PlaceKind
from app.schemas.trip import TripRequest

HERE = LatLng(lat=29.15, lng=75.72)


def place(name: str, kind: PlaceKind = PlaceKind.RESTAURANT, ids: dict | None = None,
          prominence: int | None = None, famous: bool = False, diet: DietInfo | None = None, at: LatLng = HERE,
          **kw) -> Place:
    return Place(id=f"t:{name}", name=name, kind=kind, location=at, external_ids=ids or {}, prominence=prominence,
                 is_famous=famous, diet=diet, source=DataSource.OVERTURE, **kw)


def test_places_whose_name_says_they_are_not_eateries():
    for name in ("Mere Shyam Dharmik Yatra", "मेरे श्याम धार्मिक यात्रा", "Sharma Tours & Travels",
                 "City Hospital Canteen",
                 "Glamour Salon"):
        assert not looks_like_eatery(place(name)), name
    for name in ("Kathi Roll Kingdom", "Chai Chowpatty", "Barista", "Hotel Saravana Bhavan"):
        assert looks_like_eatery(place(name)), name


def test_diet_hints_read_from_names():
    assert name_diet_hint(place("Jannat Bar")) == "bar"
    assert name_diet_hint(place("The Irish Pub")) == "bar"
    assert name_diet_hint(place("Chicken Corner")) == "nonveg"
    assert name_diet_hint(place("Non Veg Dhaba")) == "nonveg"
    assert name_diet_hint(place("Solar dos Presuntos")) == "nonveg"
    assert name_diet_hint(place("चिकन पॉइंट")) == "nonveg"
    assert name_diet_hint(place("Old Harlal Shudh Vaishno Dhaba")) == "veg"
    assert name_diet_hint(place("Pure Veg Restaurant")) == "veg"
    assert name_diet_hint(place("गुप्ता भोजनालय")) == "veg"
    # a word inside another word is not a hint
    assert name_diet_hint(place("Barista")) is None and name_diet_hint(place("Kathi Roll Kingdom")) is None


def test_strict_diets_skip_bars_and_meat_places_unless_the_data_says_otherwise():
    assert not diet_check(place("Jannat Bar"), ["vegetarian"]).ok
    assert not diet_check(place("Chicken Corner"), ["jain"]).ok
    assert diet_check(place("Jannat Bar"), []).ok                     # no diet: a bar may serve lunch
    assert diet_check(place("Jannat Bar"), ["non_vegetarian"]).ok
    tagged = DietInfo(vegetarian_options=True, known=True)
    assert diet_check(place("Chicken & Veg Corner", diet=tagged), ["vegetarian"]).ok   # data beats the name

    likely = diet_check(place("Shudh Vaishno Dhaba"), ["vegetarian"])
    assert likely.ok and likely.confidence == "likely"
    assert "Its name suggests vegetarian food (not verified)" in likely.reasons
    assert diet_check(place("Kathi Roll Kingdom"), ["vegetarian"]).confidence == "unverified"


def _ctx(**kw) -> ScoringContext:
    req = TripRequest(accommodation={"name_or_address": "Hisar bus stand"}, destination_city="Hisar", num_days=1,
                      budget=10000, currency="INR", **kw)
    return ScoringContext(req=req, origin=HERE, weekdays=[0])


def test_the_food_engine_drops_non_eateries_and_keeps_bars_from_breakfast():
    engine = FoodEngine(_ctx(food_preferences=[]), [place("Mere Shyam Dharmik Yatra", PlaceKind.CAFE),
                                                    place("Jannat Bar"), place("Chai Chowpatty", PlaceKind.CAFE)])
    assert [c.place.name for c in engine.candidates] == ["Jannat Bar", "Chai Chowpatty"]
    breakfast = engine.pick("breakfast", HERE, 9 * 60, 0, set())
    assert breakfast and breakfast[0].place.name == "Chai Chowpatty"
    bar_only = FoodEngine(_ctx(food_preferences=[]), [place("Jannat Bar")])
    assert bar_only.pick("breakfast", HERE, 9 * 60, 0, set()) is None
    assert bar_only.pick("lunch", HERE, 13 * 60, 0, set()) is not None


def test_a_vegetarian_gets_the_surest_vegetarian_place_first():
    near = LatLng(lat=29.1502, lng=75.7202)
    confirmed = place("Green Leaf", diet=DietInfo(vegetarian_only=True, vegetarian_options=True, known=True), at=near)
    named = place("Shudh Vaishno Dhaba", at=near)
    unknown = place("Masala Muse", at=HERE)          # nearest, but nothing says it is vegetarian
    engine = FoodEngine(_ctx(food_preferences=["vegetarian"]), [unknown, named, confirmed])
    assert engine.pick("lunch", HERE, 13 * 60, 0, set())[0].place.name == "Green Leaf"
    engine = FoodEngine(_ctx(food_preferences=["vegetarian"]), [unknown, named])
    assert engine.pick("lunch", HERE, 13 * 60, 0, set())[0].place.name == "Shudh Vaishno Dhaba"
    assert [r.place.name for r in engine.recommendations(2)][0] == "Shudh Vaishno Dhaba"


def test_notability_and_minor_parks():
    sector = place("Sector 14 Park", PlaceKind.PARK, ids={"overture": "1"})
    town = place("Town Park", PlaceKind.PARK, ids={"overture": "2"})
    known = place("Estufa Fria", PlaceKind.PARK, ids={"overture": "3", "wikidata": "Q1"}, prominence=10)
    assert notability(sector) == 0 and notability(known) > 0.6
    assert notability(place("X", famous=True, ids={"wikidata": "Q2"}, prominence=40)) == 1.0
    assert is_minor_park(sector) and is_minor_park(town) and not is_minor_park(known)
    assert not is_minor_park(place("Gujri Mahal", PlaceKind.ATTRACTION))


def test_neighbourhoods_junctions_shops_and_rentals_are_not_sights():
    for name in ("Rishi Nagar", "Camp Chowk", "Shri Kanha Pujan Bhandar", "Old Courts Commercial Complex, Hisar"):
        assert not looks_like_sight(place(name, PlaceKind.ATTRACTION, ids={"overture": "1"})), name
    # a rental is never a sight, even one wrongly matched to a famous Wikidata place
    apartment = place("Downtown Alfama River View Apartment", PlaceKind.ATTRACTION, ids={"wikidata": "Q3"},
                      prominence=34, famous=True)
    assert not looks_like_sight(apartment)
    # a well-known chowk is a sight; so are real sights and parks named after a neighbourhood
    chandni = place("Chandni Chowk", PlaceKind.ATTRACTION, ids={"wikidata": "Q4", "osm": "n1"}, prominence=12)
    assert looks_like_sight(chandni)
    assert looks_like_sight(place("Firoz Shah Palace Complex", PlaceKind.ATTRACTION))
    assert looks_like_sight(place("Sant Nagar Park", PlaceKind.PARK))


def test_a_day_has_at_most_one_minor_park(client, base_request, monkeypatch):
    from app.services.places_service import PlacesService

    original = PlacesService.attraction_candidates

    def with_many_parks(self, city, req):
        found = original(self, city, req)
        parks = [Place(id=f"park{i}", name=f"Sector {i} Park", kind=PlaceKind.PARK, categories=["parks", "nature"],
                       location=LatLng(lat=26.9124 + i * 0.002, lng=75.7873), source=DataSource.OVERTURE)
                 for i in range(8)]
        return parks + found

    monkeypatch.setattr(PlacesService, "attraction_candidates", with_many_parks)
    data = client.post("/api/trips/preview", json={**base_request, "interests": ["parks"]}).json()
    for day in data["days"]:
        minor = [i for i in day["items"] if i["type"] == "activity" and i["place"]["name"].startswith("Sector ")]
        assert len(minor) <= 1, [i["place"]["name"] for i in minor]
