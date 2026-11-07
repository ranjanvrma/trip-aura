def test_health_and_status(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    s = client.get("/api/meta/status").json()
    assert s["data_mode"] == "mock" and s["google"]["active"] is False
    opts = client.get("/api/meta/options").json()
    assert "museums" in opts["interests"] and "jain" in opts["food_preferences"]


def test_create_get_list_delete(client, base_request):
    r = client.post("/api/trips", json=base_request)
    assert r.status_code == 201, r.text
    data = r.json()
    tid = data["trip_id"]
    assert data["data_source"] == "mock" and len(data["days"]) == 2
    assert client.get(f"/api/trips/{tid}").json()["trip_id"] == tid
    assert any(t["id"] == tid for t in client.get("/api/trips").json())
    assert client.post(f"/api/trips/{tid}/regenerate").status_code == 200
    assert client.delete(f"/api/trips/{tid}").status_code == 204
    assert client.get(f"/api/trips/{tid}").status_code == 404


def test_validation_errors(client, base_request):
    bad = {**base_request, "num_days": 0, "budget": -5}
    r = client.post("/api/trips", json=bad)
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


def test_live_progress_alerts(client, base_request):
    tid = client.post("/api/trips", json=base_request).json()["trip_id"]
    r = client.post(f"/api/trips/{tid}/live", json={
        "current": {"lat": 26.95, "lng": 75.80}, "day_number": 1, "client_time": "09:45",
        "planned_mode": "walking", "previous_duration_min": 5, "accuracy_m": 500})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["next_place_name"] and d["straight_line_km"] > 0 and d["options"]
    kinds = {a["kind"] for a in d["alerts"]}
    assert "low_accuracy" in kinds and "traffic_change" in kinds and "better_alternative" in kinds


def test_live_progress_arrived(client, base_request):
    trip = client.post("/api/trips", json=base_request).json()
    first = next(i for i in trip["days"][0]["items"] if i["type"] == "activity")
    loc = first["place"]["location"]
    r = client.post(f"/api/trips/{trip['trip_id']}/live",
                    json={"current": loc, "day_number": 1, "next_item_id": first["id"]})
    assert any(a["kind"] == "arrived" for a in r.json()["alerts"])


def test_route_compare(client):
    r = client.post("/api/routes/compare", json={"city": "Jaipur", "origin": {"lat": 26.916, "lng": 75.809},
                                                 "destination": {"lat": 26.9239, "lng": 75.8267},
                                                 "modes": ["walking", "auto", "cab"]})
    assert r.status_code == 200
    assert {o["mode"] for o in r.json()["options"]} == {"walking", "auto", "cab"}


def test_live_mode_without_key_fails_loudly(monkeypatch, base_request):
    """Live mode must never silently fall back to mock data."""
    from app.core.config import Settings
    from app.core.errors import ProviderNotConfiguredError
    from app.services.providers import build_providers
    import pytest

    with pytest.raises(ProviderNotConfiguredError):
        build_providers(Settings(data_mode="live", google_maps_api_key=""))
