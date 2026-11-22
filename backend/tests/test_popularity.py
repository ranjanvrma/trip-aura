"""How well known a place is, from free open data kept with the city: Wikipedia readers and Wikivoyage's See list."""
from app.engines.quality import notability
from app.providers.open.city_store import mark_guide_picks, merge_places
from app.providers.open.wikimedia import GuidePick, add_wikipedia_readers, extract_see_listings, wiki_title
from app.schemas.common import DataSource, LatLng
from app.schemas.place import Place, PlaceKind

AT = LatLng(lat=38.6916, lng=-9.2160)


def place(name: str, **kw) -> Place:
    return Place(id=f"t:{name}", name=name, kind=kw.pop("kind", PlaceKind.ATTRACTION), location=kw.pop("at", AT),
                 source=DataSource.WIKIDATA, **kw)


class FakeWikipedia:
    """Answers page-view queries like the Wikipedia API: in parts, with normalised and redirected titles."""

    def __init__(self, views: dict[str, list[int | None]], renames: dict[str, str] | None = None, fail=False):
        self.views, self.renames, self.fail, self.calls = views, renames or {}, fail, []

    def get_json(self, url, params, what=""):
        self.calls.append(dict(params))
        if self.fail:
            raise RuntimeError("down")
        titles = params["titles"].split("|")
        part = titles[:2] if "pvipcontinue" not in params else titles[2:]   # two pages per answer
        pages = []
        for t in part:
            name = self.renames.get(t, t)
            if name in self.views:
                pages.append({"title": name, "pageviews": {f"2026-11-{d:02d}": v
                                                           for d, v in enumerate(self.views[name], 1)}})
            else:
                pages.append({"title": name, "missing": True})
        answer = {"query": {"pages": pages, "redirects": [{"from": t, "to": n} for t, n in self.renames.items()]}}
        if "pvipcontinue" not in params and len(titles) > 2:
            answer["continue"] = {"pvipcontinue": "next", "continue": "||"}
        return answer


def test_wikipedia_readers_are_counted_once_per_city_in_batches():
    tower = place("Belem Tower", external_ids={"wikidata": "Q1", "enwiki": "Belém Tower"})
    abbey = place("Jeronimos", external_ids={"wikidata": "Q2", "enwiki": "Jerónimos Monastery"})
    fort = place("Fort", external_ids={"wikidata": "Q3", "enwiki": "Old fort"})
    plain = place("No article", external_ids={"wikidata": "Q4"})
    http = FakeWikipedia({"Belém Tower": [1000, 2000, None], "Jerónimos Monastery": [500, 500],
                          "Old Fort (Lisbon)": [7]}, renames={"Old fort": "Old Fort (Lisbon)"})
    assert add_wikipedia_readers(http, [tower, abbey, fort, plain]) == 3
    assert (tower.readers, abbey.readers, fort.readers, plain.readers) == (3000, 1000, 7, None)
    assert len(http.calls) == 2 and http.calls[0]["pvipdays"] == 30   # one batch, answered in two parts


def test_no_count_is_made_up_when_wikipedia_has_none():
    quiet = place("Quiet", external_ids={"enwiki": "Quiet"})
    add_wikipedia_readers(FakeWikipedia({"Quiet": [None, None]}), [quiet])
    assert quiet.readers == 0
    gone = place("Gone", external_ids={"enwiki": "Gone"})
    add_wikipedia_readers(FakeWikipedia({}), [gone])
    assert gone.readers is None


def test_article_titles_are_checked():
    assert wiki_title({"article": {"value": "Belém Tower"}}) == "Belém Tower"
    for bad in ("", "a|b", "x" * 300, "<script>", "Page{{x}}"):
        assert wiki_title({"article": {"value": bad}}) is None
    assert wiki_title({}) is None


SEE = """
* {{see | name=Belém Tower | alt=Torre de Belém | wikidata=Q1 | lat=38.6916 | long=-9.2160
| content=A fortified tower {{IATA|LIS}} on the river. }}
* {{see|name='''Jerónimos Monastery'''|lat=38.6979|long=-9.2068}}
* {{listing|type=see|name=Gulbenkian Museum|wikidata=Q5}}
* {{listing|type=eat|name=Pasteis de Belem}}
* {{do|name=Tram 28}}
* {{see|name=X}}
"""


def test_see_listings_are_read_from_the_guide():
    picks = extract_see_listings(SEE)
    assert [(p.name, p.qid) for p in picks] == [("Belém Tower", "Q1"), ("Jerónimos Monastery", None),
                                                ("Gulbenkian Museum", "Q5")]
    assert picks[0].lat == 38.6916 and picks[1].lng == -9.2068


def test_guide_picks_are_matched_by_wikidata_id_or_by_name_nearby():
    tower = place("Torre de Belém", external_ids={"wikidata": "Q1"})
    abbey = place("Jeronimos Monastery", at=LatLng(lat=38.6980, lng=-9.2066))
    namesake = place("Jeronimos Monastery", at=LatLng(lat=41.0, lng=-8.6))     # same name, another city
    cafe = place("Gulbenkian Museum", kind=PlaceKind.CAFE)
    picks = [GuidePick("Belém Tower", "Q1"), GuidePick("Jerónimos Monastery", None, 38.6979, -9.2068),
             GuidePick("Gulbenkian Museum")]
    assert mark_guide_picks([tower, abbey, namesake, cafe], picks) == 2
    assert tower.guide_pick and abbey.guide_pick and not namesake.guide_pick and not cafe.guide_pick


def test_readers_and_guide_picks_survive_merging_and_raise_notability():
    base = place("Belem Tower", external_ids={"overture": "1"})
    extra = place("Belem Tower", external_ids={"wikidata": "Q1"}, readers=25_000, guide_pick=True)
    merged = merge_places([base], [extra])[0]
    assert merged.readers == 25_000 and merged.guide_pick
    plain = place("Small chapel", external_ids={"overture": "2"})
    assert notability(place("Read", readers=25_000)) > notability(place("Little read", readers=600)) > 0
    assert notability(place("Pick", guide_pick=True)) == 0.25 and notability(plain) == 0


def test_a_famous_place_is_not_merged_into_a_minor_one_that_mentions_it():
    near = LatLng(lat=26.9855, lng=75.8513)
    tunnel = Place(id="ov:t", name="Tunnel Connecting Amber Fort and Jaigarh Fort", kind=PlaceKind.ATTRACTION,
                   location=near, source=DataSource.OVERTURE)
    museum = Place(id="ov:m", name="Albert Hall", kind=PlaceKind.ATTRACTION, location=AT, source=DataSource.OVERTURE)
    fort = place("Amber Fort", at=near, external_ids={"wikidata": "Q1"}, readers=9930)
    hall = place("Albert Hall Museum", external_ids={"wikidata": "Q2"}, readers=1800)
    merged = merge_places([tunnel, museum], [fort, hall], max_m=300)
    assert [(p.name, p.readers) for p in merged] == [("Tunnel Connecting Amber Fort and Jaigarh Fort", None),
                                                    ("Albert Hall", 1800), ("Amber Fort", 9930)]


def test_a_city_says_when_reader_counts_were_unavailable(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import Settings
    from app.db import models  # noqa: F401
    from app.db.database import Base
    from app.providers.base import CityContext
    from app.providers.open import osm, overture, wikimedia
    from app.providers.open.city_store import CityDataService

    engine = create_engine(f"sqlite:///{tmp_path / 'c.db'}")
    Base.metadata.create_all(engine)
    settings = Settings(data_mode="open", wikivoyage_enabled=False, osm_grace_seconds=0.1)
    tower = place("Belem Tower", external_ids={"wikidata": "Q1", "enwiki": "Belém Tower"}, prominence=40)
    monkeypatch.setattr(overture, "fetch", lambda *a, **k: ([], []))
    monkeypatch.setattr(overture, "latest_release", lambda *a, **k: "2026-11-18.0")
    monkeypatch.setattr(wikimedia, "wikidata_notable_places", lambda *a, **k: [tower.model_copy(deep=True)])
    monkeypatch.setattr(osm, "build_queries", lambda *a, **k: {})
    svc = CityDataService(settings, FakeWikipedia({}, fail=True), sessionmaker(bind=engine))
    city = CityContext(name="Lisbon, Portugal", center=AT, country_code="PT", radius_km=8, has_metro=None,
                       source=DataSource.OSM)
    data = svc.build(city)
    assert [p.name for p in data.places] == ["Belem Tower"] and data.places[0].readers is None
    assert any("Wikipedia reader counts were unavailable" in w for w in data.warnings)


def test_the_more_read_of_two_famous_sights_is_chosen(mock_service, monkeypatch):
    """Two sights the data knows equally well (full notability), long enough that a day takes only one: the one far
    more people read about wins, and swapping the reader counts swaps the choice. Notability alone is full for both,
    which is how Hawa Mahal (11,800 readers a month) once lost to Albert Hall (2,100)."""
    from app.schemas.trip import TripRequest
    from app.services.places_service import PlacesService

    stay = LatLng(lat=26.9124, lng=75.7873)

    def sight(pid: str, name: str, north: float, readers: int) -> Place:
        return Place(id=pid, name=name, kind=PlaceKind.ATTRACTION, categories=["history"],
                     location=LatLng(lat=stay.lat + north, lng=stay.lng), is_famous=True, prominence=40,
                     external_ids={"wikidata": pid, "osm": "n1"}, readers=readers, typical_visit_minutes=180,
                     source=DataSource.OVERTURE)

    req = TripRequest(accommodation={"type": "hotel", "name_or_address": "Hotel on MI Road"}, destination_city="Jaipur",
                      start_date="2026-11-10", num_days=1, budget=20000, currency="INR", interests=["history"],
                      food_preferences=[], food_categories=["local_cuisine"], transport_modes=["walking", "auto"],
                      pace="relaxed")

    def planned(museum_readers: int, palace_readers: int) -> list[str]:
        places = [sight("Q2", "Albert Museum", 0.004, museum_readers),
                  sight("Q1", "Wind Palace", 0.006, palace_readers)]
        monkeypatch.setattr(PlacesService, "attraction_candidates", lambda self, c, r: places)
        return [i.title for d in mock_service.generate(req).days for i in d.items if i.type == "activity"]

    assert planned(2_100, 11_800) == ["Wind Palace"]
    assert planned(11_800, 2_100) == ["Albert Museum"]


def test_reader_counts_are_credited():
    from app.providers.open.city_store import attributions_for

    assert any("page-view statistics" in a for a in attributions_for(["Wikidata", "Wikipedia page views"]))
    assert not any("page-view" in a for a in attributions_for(["Wikidata"]))
