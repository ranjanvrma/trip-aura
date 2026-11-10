"""NLP features: city index, trip-description parser, interest normalisation, sentiment,
semantic scoring. Offline: a small fake GeoNames table and a fake embedding model."""
import datetime as dt

import numpy as np
import pytest

from app.engines.food import dish_suggestions
from app.engines.recommendation import ScoringContext, score_attraction
from app.nlp.city_index import CityIndex
from app.nlp.interests import expand_interests, normalise_interest
from app.nlp.semantic import strength
from app.nlp.sentiment import lexicon_score, sentence_polarity
from app.nlp.trip_parser import parse_budget, parse_date, parse_trip_text
from app.schemas.common import DataSource, LatLng
from app.schemas.place import Place, PlaceKind, Review
from app.schemas.trip import TripRequest

ROWS = [
    # id, name, ascii, alternates, lat, lng, cc, admin1, population
    (2267057, "Lisbon", "Lisbon", "Lisboa,Lisbonne,Lissabon", 38.72, -9.13, "PT", "14", 517802),
    (1269515, "Jaipur", "Jaipur", "Jaypur", 26.92, 75.78, "IN", "24", 3046163),
    (1275339, "Mumbai", "Mumbai", "Bombay,Bombaim", 19.07, 72.88, "IN", "16", 12691836),
    (2988507, "Paris", "Paris", "Lutece,Parigi", 48.85, 2.35, "FR", "11", 2138551),
    (4717560, "Paris", "Paris", "", 33.66, -95.56, "US", "TX", 24782),
    (5128581, "New York City", "New York City", "NYC,New York", 40.71, -74.01, "US", "NY", 8804190),
    (1850147, "Tokyo", "Tokyo", "Tokio,Tokyo-to", 35.69, 139.69, "JP", "40", 8336599),
    (3128760, "Barcelona", "Barcelona", "Barcelone", 41.39, 2.16, "ES", "56", 1620343),
]


def make_index() -> CityIndex:
    lines = []
    for gid, name, ascii_, alt, lat, lng, cc, a1, pop in ROWS:
        f = [str(gid), name, ascii_, alt, str(lat), str(lng), "P", "PPLC", cc, "", a1, "", "", "", str(pop), "", "", "tz", ""]
        lines.append("\t".join(f))
    ix = CityIndex("unused", "https://example.invalid", "test")
    ix.load_from_text("\n".join(lines), {"PT": "Portugal", "IN": "India", "FR": "France", "US": "United States",
                                         "JP": "Japan", "ES": "Spain"},
                      {"PT.14": "Lisbon", "IN.24": "Rajasthan", "IN.16": "Maharashtra", "FR.11": "Ile-de-France",
                       "US.TX": "Texas", "US.NY": "New York", "JP.40": "Tokyo", "ES.56": "Catalonia"})
    return ix


@pytest.fixture(scope="module")
def ix():
    return make_index()


# ---------------------------------------------------------------- city index
def test_prefix_search_prefers_big_primary_names(ix):
    assert ix.search("par")[0].country == "France"
    assert [c.name for c in ix.search("lis")] == ["Lisbon"]
    assert ix.search("jai")[0].display == "Jaipur, Rajasthan, India"


def test_alternate_names_and_typos(ix):
    assert ix.search("Lisboa")[0].name == "Lisbon"
    assert ix.search("Bombay")[0].name == "Mumbai"
    assert ix.search("Barcelonna")[0].name == "Barcelona"      # fuzzy
    assert ix.exact("tokio").name == "Tokyo"


def test_country_hint(ix):
    assert ix.search("paris, us")[0].country == "United States"


# --------------------------------------------------------------- trip parser
TODAY = dt.date(2026, 11, 7)  # a Saturday


def test_full_description(ix):
    r = parse_trip_text("4 days in Lisboa with my wife, vegetarian, we love museums, street art and sunsets, "
                        "budget 900 euros, staying at Hotel Avenida Palace, relaxed pace, mostly metro and walking",
                        ix, TODAY)
    f = r.fields
    assert f["destination_city"] == "Lisbon, Portugal" and f["num_days"] == 4 and f["travelers"] == 2
    assert (f["budget"], f["currency"]) == (900, "EUR")
    assert f["accommodation"]["name_or_address"] == "Hotel Avenida Palace"
    assert f["pace"] == "relaxed" and f["food_preferences"] == ["vegetarian"]
    assert set(f["transport_modes"]) == {"metro", "walking"}
    assert {"museums", "street_art", "art", "photography"} <= set(f["interests"])
    assert not any("staying" in i or "budget" in i for i in f["interests"])
    r2 = parse_trip_text("we love museums, street art and sunsets, budget 900 euros, staying at Rossio", ix, TODAY)
    assert not any("rossio" in i for i in r2.fields["interests"])


def test_indian_style_description(ix):
    r = parse_trip_text("Weekend trip to Jaipur for 3 friends, budget Rs 25k, pure veg street food, love forts and "
                        "palaces, autos and cabs, from 12th Dec", ix, TODAY)
    f = r.fields
    assert f["destination_city"].startswith("Jaipur") and f["num_days"] == 2 and f["travelers"] == 3
    assert (f["budget"], f["currency"]) == (25000, "INR")
    assert f["start_date"] == "2026-12-12" and f["food_categories"] == ["street_food"]
    assert {"monuments", "history"} <= set(f["interests"])
    assert not any(ch.isdigit() for i in f["interests"] for ch in i)


def test_per_day_budget_negation_and_relative_date(ix):
    r = parse_trip_text("Solo trip to Tokio next friday for a week, hostel, $80 per day, packed schedule, "
                        "no taxis, public transport", ix, TODAY)
    f = r.fields
    assert f["destination_city"] == "Tokyo, Japan" and f["num_days"] == 7 and f["travelers"] == 1
    assert f["budget"] == 560 and f["currency"] == "USD" and f["start_date"] == "2026-11-13"
    assert f["accommodation"]["type"] == "hostel" and f["pace"] == "packed"
    assert "cab" not in f["transport_modes"] and {"metro", "bus"} <= set(f["transport_modes"])


def test_lowercase_city_typos_and_notes(ix):
    r = parse_trip_text("family of 4 going to new york city, 5 nights, budget 3000 usd, musuems and parks, non-veg",
                        ix, TODAY)
    f = r.fields
    assert f["destination_city"].startswith("New York City") and f["num_days"] == 6 and f["travelers"] == 4
    assert "museums" in f["interests"] and f["food_preferences"] == ["non_vegetarian"]
    assert any("musuems" in n for n in r.notes)


def test_missing_fields_are_reported(ix):
    r = parse_trip_text("somewhere warm, budget 500", ix, TODAY)
    assert "destination_city" not in r.fields
    assert any("No destination" in n for n in r.notes) and any("currency" in n for n in r.notes)


def test_budget_and_date_helpers():
    assert parse_budget("about ₹40,000 total") == (40000, "INR")
    assert parse_budget("2 lakh rupees") == (200000, "INR")
    assert parse_budget("€1.5k") == (1500, "EUR")
    assert parse_date("on 2026-12-24", TODAY) == dt.date(2026, 12, 24)
    assert parse_date("March 3rd", TODAY) == dt.date(2027, 3, 3)
    assert parse_date("tomorrow", TODAY) == dt.date(2026, 11, 8)


def test_parser_typo_interests_keep_text_order():
    # the single-word typo pass used to iterate a set, so the order depended on the hash seed
    res = parse_trip_text("3 days of architecure, musuems and wildlfe")
    assert res.fields["interests"] == ["architecture", "museums", "wildlife"]
    assert res.notes[:3] == ["Read 'architecure' as 'architecture'.", "Read 'musuems' as 'museums'.",
                             "Read 'wildlfe' as 'wildlife'."]


# ------------------------------------------------------------------ interests
def test_interest_normalisation():
    assert normalise_interest("musuems") == (["museums"], "museums")
    assert normalise_interest("temples")[0] == ["religious_sites"]
    assert normalise_interest("history buff")[0] == ["history", "monuments", "museums"]
    expanded, corrections = expand_interests(["architecure", "street_art"])
    assert corrections == {"architecure": "architecture"}
    assert expanded[:2] == ["architecture", "street_art"] and "art" in expanded


# ------------------------------------------------------------------ sentiment
def test_lexicon_sentiment_with_negation():
    assert lexicon_score("The biryani was amazing, a must try") > 0
    assert lexicon_score("The biryani was cold and bland") < 0
    assert lexicon_score("Not good at all") < 0
    assert lexicon_score("The dal was not bad") > 0
    assert sentence_polarity(["We had biryani."]) == [0.0]


def test_negative_mentions_are_not_evidence():
    p = Place(id="r", name="R", kind=PlaceKind.RESTAURANT, location=LatLng(lat=0, lng=0), source=DataSource.GOOGLE,
              reviews=[Review(text="The biryani was cold and bland.", source=DataSource.GOOGLE),
                       Review(text="Biryani was terrible, avoid.", source=DataSource.GOOGLE),
                       Review(text="Loved the paneer tikka. Paneer tikka is a must!", source=DataSource.GOOGLE),
                       Review(text="Best paneer tikka in town.", source=DataSource.GOOGLE)])
    dishes = {d.name.lower(): d for d in dish_suggestions(p, [])}
    assert "biryani" not in dishes                                   # only negative mentions
    assert dishes["paneer tikka"].status == "popular" and dishes["paneer tikka"].negative_mentions == 0


# ------------------------------------------------------------------- semantic
class FakeSemantic:
    """Deterministic stand-in for an embedding model: texts sharing a concept group are similar."""
    available = True
    GROUPS = [("mural", "street art", "graffiti"), ("sunset", "view")]

    def similarity(self, queries, docs):
        def vec(t):
            t = t.lower()
            return np.array([float(any(k in t for k in g)) for g in self.GROUPS])
        q = np.stack([vec(x) for x in queries])
        d = np.stack([vec(x) for x in docs])
        return 0.5 + 0.35 * (q @ d.T > 0)


def test_semantic_strength_curve():
    assert strength(0.5) == 0 and strength(0.66) == 0 and strength(0.9) == 1 and 0 < strength(0.73) < 1


def test_semantic_match_raises_suitability():
    from app.services.itinerary_service import semantic_interest_matches

    req = TripRequest.model_validate({"accommodation": {"name_or_address": "Hotel"}, "destination_city": "Lisbon",
                                      "num_days": 1, "budget": 1000, "interests": ["street_art"]})
    mural = Place(id="p1", name="LX Factory murals", kind=PlaceKind.ATTRACTION, location=LatLng(lat=0, lng=0),
                  description="Former factory covered in graffiti and murals", source=DataSource.OVERTURE)
    plain = Place(id="p2", name="Tax Office", kind=PlaceKind.ATTRACTION, location=LatLng(lat=0, lng=0),
                  source=DataSource.OVERTURE)
    ctx = ScoringContext(req=req, origin=LatLng(lat=0, lng=0), weekdays=[0])
    before = score_attraction(mural, ctx).score
    ctx.semantic = semantic_interest_matches(FakeSemantic(), ["street art"], [mural, plain])
    assert "p1" in ctx.semantic and "p2" not in ctx.semantic
    ctx.semantic = {"p1": {"street_art": ctx.semantic["p1"]["street art"]}}
    after = score_attraction(mural, ctx)
    assert after.score > before
    assert any("AI text matching" in r for r in after.reasons)


# --------------------------------------------------------------------- API
def test_api_parse_and_city_endpoints(client, monkeypatch):
    from app.nlp import registry

    fake = make_index()
    monkeypatch.setattr(registry, "get_city_index", lambda: fake)
    import app.routers.geo as geo
    import app.routers.nlp as nlp
    monkeypatch.setattr(geo, "get_city_index", lambda: fake)
    monkeypatch.setattr(nlp, "get_city_index", lambda: fake)
    r = client.get("/api/geo/cities", params={"q": "lis"})
    assert r.status_code == 200 and r.json()["results"][0]["query"] == "Lisbon, Portugal"
    assert client.get("/api/geo/cities", params={"q": "l"}).status_code == 422
    r = client.post("/api/nlp/parse-trip", json={"text": "3 days in Barcelona, vegan, budget 700 eur"})
    body = r.json()
    assert r.status_code == 200 and body["fields"]["destination_city"] == "Barcelona, Spain"
    assert body["fields"]["food_preferences"] == ["vegan"] and body["understood"]
