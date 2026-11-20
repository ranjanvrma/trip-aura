"""A place's photo comes from its Wikidata image (P18), a Wikimedia Commons file, and only a plain file name is kept."""
from app.core.urls import commons_file
from app.providers.open.city_store import merge_places
from app.providers.open.wikimedia import wikidata_notable_places
from app.schemas.common import DataSource, LatLng
from app.schemas.place import Place, PlaceKind


def test_commons_file_names_are_taken_from_wikidata_values():
    url = "http://commons.wikimedia.org/wiki/Special:FilePath/Hawa%20Mahal%202011.jpg"
    assert commons_file(url) == "Hawa Mahal 2011.jpg"
    assert commons_file("Gujri_Mahal,_Hisar.JPG") == "Gujri Mahal, Hisar.JPG"
    assert commons_file("Map of the fort.svg") == "Map of the fort.svg"
    for bad in (None, 42, "", "notes.txt", "x.jpg?width=1", "a<b>.png", "javascript:alert(1)", "..%2F..%2Fx.jpg",
                "a\\b.jpg", "a" * 300 + ".jpg"):
        assert commons_file(bad) is None, bad


def test_a_place_keeps_only_a_valid_image_name():
    def make(image):
        return Place(id="x", name="X", kind=PlaceKind.ATTRACTION, location=LatLng(lat=1, lng=1), image=image,
                     source=DataSource.WIKIDATA)
    assert make("Fort.jpg").image == "Fort.jpg"
    assert make("https://evil.example/x.html").image is None


class FakeHttp:
    def __init__(self, data):
        self.data = data
        self.query = ""

    def get_json(self, url, params, what=""):
        self.query = params["query"]
        return self.data


def binding(qid, name, image=None):
    b = {"item": {"value": f"http://www.wikidata.org/entity/{qid}"}, "itemLabel": {"value": name},
         "lat": {"value": "29.15"}, "lon": {"value": "75.72"}, "links": {"value": "9"}, "types": {"value": "fort"}}
    if image:
        b["image"] = {"value": image}
    return b


def test_wikidata_places_carry_their_photo():
    http = FakeHttp({"results": {"bindings": [
        binding("Q1", "Firoz Shah Palace", "http://commons.wikimedia.org/wiki/Special:FilePath/Firoz%20Shah.jpg"),
        binding("Q2", "Gujri Mahal"),
    ]}})
    places = wikidata_notable_places(http, 29.15, 75.72, 10)
    assert "wdt:P18" in http.query
    assert [(p.name, p.image) for p in places] == [("Firoz Shah Palace", "Firoz Shah.jpg"), ("Gujri Mahal", None)]


def test_merging_keeps_the_photo_from_wikidata():
    at = LatLng(lat=29.15, lng=75.72)
    base = Place(id="ov:1", name="Firoz Shah Palace", kind=PlaceKind.ATTRACTION, location=at, source=DataSource.OVERTURE)
    extra = Place(id="wd:Q1", name="Firoz Shah Palace", kind=PlaceKind.ATTRACTION, location=at, image="Firoz Shah.jpg",
                  source=DataSource.WIKIDATA)
    merged = merge_places([base], [extra])
    assert len(merged) == 1 and merged[0].image == "Firoz Shah.jpg"


def test_a_plan_with_photos_credits_wikimedia_commons(client, base_request, monkeypatch):
    from app.services.places_service import PlacesService

    original = PlacesService.attraction_candidates

    def with_photos(self, city, req):
        return [p.model_copy(update={"image": "Sight.jpg"}) for p in original(self, city, req)]

    data = client.post("/api/trips/preview", json=base_request).json()
    assert not any("Wikimedia Commons" in a for a in data["attributions"])
    monkeypatch.setattr(PlacesService, "attraction_candidates", with_photos)
    data = client.post("/api/trips/preview", json=base_request).json()
    assert any("Wikimedia Commons" in a for a in data["attributions"])
    shown = [i["place"]["image"] for d in data["days"] for i in d["items"] if i["type"] == "activity"]
    assert shown and set(shown) == {"Sight.jpg"}
