from app.engines.food import city_popular_dishes, diet_check, dish_suggestions
from app.providers.mock.providers import _all_places
from app.schemas.common import DataSource, LatLng
from app.schemas.place import DietInfo, Place, PlaceKind, Review

P = _all_places()


def test_vegetarian_excludes_egg_only_stall():
    assert not diet_check(P["mock-food-egg-stall"], ["vegetarian"]).ok
    assert diet_check(P["mock-food-thali-house"], ["vegetarian"]).ok


def test_jain_requires_jain_options():
    assert diet_check(P["mock-food-jain-bhojanalaya"], ["jain"]).ok
    assert not diet_check(P["mock-food-kachori"], ["jain"]).ok


def test_vegan_and_eggetarian():
    assert diet_check(P["mock-food-green-leaf"], ["vegan"]).ok
    assert not diet_check(P["mock-food-thali-house"], ["vegan"]).ok
    assert diet_check(P["mock-food-egg-stall"], ["eggetarian"]).ok


def test_multiple_diets_must_all_match():
    assert diet_check(P["mock-food-green-leaf"], ["vegan", "jain"]).ok
    assert not diet_check(P["mock-food-brew"], ["vegan", "jain"]).ok


def test_unknown_diet_info_is_unverified_not_confirmed():
    p = Place(id="g", name="G", kind=PlaceKind.RESTAURANT, location=LatLng(lat=0, lng=0), source=DataSource.GOOGLE,
              diet=DietInfo(known=False, source=DataSource.GOOGLE))
    chk = diet_check(p, ["jain"])
    assert chk.ok and chk.confidence == "unverified"
    p.categories = ["food", "search:jain"]
    assert diet_check(p, ["jain"]).confidence == "likely"


def test_dish_popular_only_with_two_mentions():
    dishes = {d.name.lower(): d for d in dish_suggestions(P["mock-food-thali-house"], [])}
    assert dishes["dal baati churma"].status == "popular" and dishes["dal baati churma"].mention_count >= 2
    assert dishes["dal baati churma"].evidence
    assert dishes["gatte ki sabzi"].status == "mentioned"


def test_suggestions_without_evidence_are_labelled():
    p = Place(id="x", name="X", kind=PlaceKind.RESTAURANT, location=LatLng(lat=0, lng=0), source=DataSource.GOOGLE,
              cuisines=["south_indian"], reviews=[])
    ds = dish_suggestions(p, [])
    assert ds and all(d.status == "suggestion" and not d.evidence for d in ds)


def test_dishes_respect_diet():
    names = [d.name.lower() for d in dish_suggestions(P["mock-food-amer-haveli"], ["vegetarian"])]
    assert "laal maas" not in names
    names_nv = [d.name.lower() for d in dish_suggestions(P["mock-food-amer-haveli"], ["non_vegetarian"])]
    assert "laal maas" in names_nv


def test_longest_dish_match_wins_within_review():
    p = Place(id="x", name="X", kind=PlaceKind.CAFE, location=LatLng(lat=0, lng=0), source=DataSource.MOCK,
              reviews=[Review(text="The kesar lassi was great", source=DataSource.MOCK)])
    names = [d.name.lower() for d in dish_suggestions(p, [])]
    assert "kesar lassi" in names and "lassi" not in names


def test_city_popular_dishes_need_two_places():
    out = city_popular_dishes([P["mock-food-thali-house"], P["mock-food-mishthan"]], [])
    assert any(d.name.lower() == "ghevar" for d in out)  # mentioned at both places
    assert all(d.status == "popular" and d.mention_count >= 2 for d in out)
