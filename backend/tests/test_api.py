import httpx
import pytest


def test_health_and_status(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    s = client.get("/api/meta/status").json()
    assert s["data_mode"] == "mock" and s["google"]["active"] is False
    opts = client.get("/api/meta/options").json()
    assert "museums" in opts["interests"] and "jain" in opts["food_preferences"]


def test_preview_generates_without_saving(client, base_request):
    r = client.post("/api/trips/preview", json=base_request)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["data_source"] == "mock" and len(data["days"]) == 2 and data["trip_id"] is None


def test_removed_endpoints_are_gone(client, base_request):
    """Sign-in, server-side saved trips and live tracking were removed; trips are saved in the browser."""
    for method, path, body in [("post", "/api/trips", base_request), ("get", "/api/trips", None),
                               ("get", "/api/trips/1", None), ("post", "/api/trips/1/regenerate", None),
                               ("post", "/api/trips/1/live", {}), ("post", "/api/auth/request-code", {}),
                               ("get", "/api/auth/me", None)]:
        assert client.request(method, path, json=body).status_code in (404, 405), (method, path)


def test_validation_errors(client, base_request):
    bad = {**base_request, "num_days": 0, "budget": -5}
    r = client.post("/api/trips/preview", json=bad)
    assert r.status_code == 422
    fields = {d["field"] for d in r.json()["error"]["details"]}
    assert {"num_days", "budget"} <= fields


def test_unsupported_city_in_mock_mode(client, base_request):
    r = client.post("/api/trips/preview", json={**base_request, "destination_city": "Paris"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unsupported_in_mock_mode"


def test_custom_inputs_accepted(client, base_request):
    body = {**base_request, "interests": ["Street Art", "museums"], "food_preferences": ["vegetarian", "no garlic"]}
    r = client.post("/api/trips/preview", json=body)
    assert r.status_code == 200
    assert r.json()["request"]["interests"] == ["street_art", "museums"]


def test_route_compare(client):
    r = client.post("/api/routes/compare", json={"city": "Jaipur", "origin": {"lat": 26.916, "lng": 75.809},
                                                 "destination": {"lat": 26.9239, "lng": 75.8267},
                                                 "modes": ["walking", "auto", "cab"]})
    assert r.status_code == 200
    assert {o["mode"] for o in r.json()["options"]} == {"walking", "auto", "cab"}


def test_live_mode_without_key_fails_loudly():
    """Live mode must never silently fall back to mock data."""
    from app.core.config import Settings
    from app.core.errors import ProviderNotConfiguredError
    from app.services.providers import build_providers

    with pytest.raises(ProviderNotConfiguredError):
        build_providers(Settings(data_mode="live", google_maps_api_key=""))


def test_hosted_postgres_urls_get_a_driver():
    from app.db.database import normalise_url

    assert normalise_url("postgres://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
    assert normalise_url("postgresql://u:p@host/db?sslmode=require") == "postgresql+psycopg://u:p@host/db?sslmode=require"
    assert normalise_url("sqlite:///tripaura.db") == "sqlite:///tripaura.db"


def test_blank_database_url_uses_default_sqlite():
    from app.core.config import DEFAULT_DATABASE_URL, Settings

    assert Settings(database_url="").database_url == DEFAULT_DATABASE_URL
    assert Settings(database_url="postgres://u:p@h/db").database_url == "postgres://u:p@h/db"


def test_address_suggestions_skip_features_without_coordinates(client, monkeypatch):
    import httpx

    from app.routers import geo

    features = [
        {"properties": {"name": "No geometry"}, "geometry": None},
        {"properties": {"name": "Short"}, "geometry": {"coordinates": [9.1]}},
        {"properties": {"name": "Bad"}, "geometry": {"coordinates": ["x", "y"]}},
        {"properties": None, "geometry": {"coordinates": [-9.14, 38.71]}},
        {"properties": {"name": "Rossio", "city": "Lisbon"}, "geometry": {"coordinates": [-9.1394, 38.7139]}},
    ]
    resp = httpx.Response(200, json={"features": features}, request=httpx.Request("GET", "https://photon.test"))
    monkeypatch.setattr(geo.httpx, "get", lambda *a, **k: resp)
    r = client.get("/api/geo/addresses", params={"q": "rossio"})
    assert r.status_code == 200
    results = r.json()["results"]
    # the nameless point is dropped too: it would show as an empty suggestion
    assert [(x["label"], x["lat"]) for x in results] == [("Rossio, Lisbon", 38.7139)]


def test_address_search_matches_inside_names_and_stays_local(client, monkeypatch):
    from app.routers import geo

    def feat(name, kind, lng, lat):
        props = {"name": name, "osm_value": kind, "city": "Jaipur"}
        return {"properties": props, "geometry": {"coordinates": [lng, lat]}}

    calls = []

    def fake_get(url, params=None, **kw):
        calls.append(params)
        if "bbox" in params:          # the search limited to the destination area is down
            raise httpx.ConnectError("down")
        feats = [feat("Inn", "river", 10.5, 47.3), feat("Innovation Street", "street", 75.80, 26.92),
                 feat("Holiday Inn", "hotel", 75.79, 26.91), feat("Holiday Inn", "hotel", 75.79, 26.91),
                 feat("Golden Inn", "hotel", 75.81, 26.90), feat("City Mall", "mall", 75.78, 26.93)]
        return httpx.Response(200, json={"features": feats}, request=httpx.Request("GET", "https://photon.test"))

    monkeypatch.setattr(geo.httpx, "get", fake_get)
    r = client.get("/api/geo/addresses", params={"q": "inn", "lat": 26.91, "lng": 75.79, "city": "Jaipur, India"})
    assert r.status_code == 200
    names = [x["name"] for x in r.json()["results"]]
    # hotels with "inn" anywhere in the name first, the duplicate merged, the river 6,000 km away dropped
    assert names == ["Holiday Inn", "Golden Inn", "Innovation Street", "City Mall"]
    assert {c["q"] for c in calls} == {"inn", "inn Jaipur"}


def test_trip_style_changes_what_the_plan_spends(client, base_request):
    totals = {}
    for style in ("budget", "mid", "premium"):
        r = client.post("/api/trips/preview", json={**base_request, "budget": 40000, "trip_style": style})
        assert r.status_code == 200, r.text
        data = r.json()
        totals[style] = data["budget"]["planned_total"]
        assert data["budget"]["planned_total"] <= 40000
        notes = " ".join(data["budget"]["notes"])
        assert ("style" in notes) == (style != "mid")
    assert totals["budget"] <= totals["mid"] <= totals["premium"]
    assert totals["budget"] < totals["premium"]


def test_trip_style_scores_meals_for_the_style():
    import datetime as dt

    from app.engines.recommendation import ScoringContext
    from app.schemas.common import LatLng
    from app.schemas.trip import TripRequest

    def ctx(style):
        req = TripRequest(destination_city="Jaipur", accommodation={"type": "hotel", "name_or_address": "MI Road"},
                          start_date=dt.date(2026, 11, 10), num_days=2, budget=12000, currency="INR", trip_style=style)
        return ScoringContext(req=req, origin=LatLng(lat=26.9, lng=75.8), weekdays=[1, 2])

    budget, mid, premium = ctx("budget"), ctx("mid"), ctx("premium")
    allowance = mid.meal_allowance
    assert budget.meal_fit(allowance) < mid.meal_fit(allowance) == 1.0       # a full-price meal stretches a cheap trip
    assert premium.meal_fit(allowance * 0.1) < mid.meal_fit(allowance * 0.1)  # the cheapest places suit premium less
    assert premium.meal_fit(allowance) == 1.0
