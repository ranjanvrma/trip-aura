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
