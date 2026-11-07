"""Google provider parsing and error behaviour, using httpx.MockTransport (no network, no key leaks)."""
import json

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ProviderNotConfiguredError, ProviderRequestError
from app.providers.base import CityContext, PlaceQuery
from app.providers.google.client import GoogleClient
from app.providers.google.places import GooglePlacesProvider, _hours, to_place
from app.providers.google.routes import GoogleRoutesProvider, decode_polyline
from app.schemas.common import DataSource, LatLng
from app.schemas.trip import TransportMode

CITY = CityContext(name="Testville", center=LatLng(lat=10, lng=20), country_code="IN", radius_km=10,
                   has_metro=None, source=DataSource.GOOGLE, utc_offset_minutes=330)
SETTINGS = Settings(data_mode="live", google_maps_api_key="test-key-not-real")

SAMPLE_PLACE = {
    "id": "abc123", "displayName": {"text": "City Museum"}, "formattedAddress": "1 Main St",
    "location": {"latitude": 10.01, "longitude": 20.02}, "rating": 4.6, "userRatingCount": 12000,
    "types": ["museum", "tourist_attraction"], "primaryType": "museum",
    "regularOpeningHours": {"periods": [
        {"open": {"day": 1, "hour": 9, "minute": 0}, "close": {"day": 1, "hour": 17, "minute": 30}},
        {"open": {"day": 5, "hour": 18, "minute": 0}, "close": {"day": 6, "hour": 2, "minute": 0}},
    ]},
    "googleMapsUri": "https://maps.google.com/?cid=1",
}


def test_no_key_raises_not_configured():
    with pytest.raises(ProviderNotConfiguredError):
        GoogleClient(Settings(data_mode="live", google_maps_api_key=""))


def test_place_parsing_keeps_real_rating_and_converts_hours():
    p = to_place(SAMPLE_PLACE, tag="famous")
    assert p.id == "g:abc123" and p.source == DataSource.GOOGLE
    assert p.external_rating.provider == DataSource.GOOGLE and p.external_rating.verified
    assert p.external_rating.rating == 4.6 and p.external_rating.review_count == 12000
    assert p.entry_fee is None            # never invented
    assert p.is_famous                    # famous query + many reviews
    assert "museums" in p.categories
    oh = p.opening_hours
    assert oh.weekly[0][0].open == "09:00" and oh.weekly[0][0].close == "17:30"   # Google Monday(1) -> 0
    assert oh.weekly[4][0].close == "24:00" and oh.weekly[5][0].close == "02:00"  # overnight Friday


def test_place_without_rating_is_not_faked():
    raw = {**SAMPLE_PLACE}
    raw.pop("rating"); raw.pop("userRatingCount")
    p = to_place(raw)
    assert p.external_rating.rating is None and not p.external_rating.verified


def test_hours_open_24h_and_missing():
    assert _hours({"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]}).weekly[3][0].close == "24:00"
    assert _hours(None).known is False


def test_search_sends_key_header_and_field_mask():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"places": [SAMPLE_PLACE]})

    client = GoogleClient(SETTINGS, transport=httpx.MockTransport(handler))
    out = GooglePlacesProvider(client).search(CITY, PlaceQuery(text="museums in Testville", tag="museums", kind="attraction"))
    assert len(out) == 1
    assert seen["headers"]["X-Goog-Api-Key"] == "test-key-not-real"
    assert "places.rating" in seen["headers"]["X-Goog-FieldMask"]
    assert seen["body"]["textQuery"] == "museums in Testville"


def test_http_error_is_raised_not_replaced_with_mock():
    client = GoogleClient(SETTINGS, transport=httpx.MockTransport(
        lambda r: httpx.Response(403, json={"error": {"message": "API key not valid"}})))
    with pytest.raises(ProviderRequestError) as e:
        GooglePlacesProvider(client).search(CITY, PlaceQuery(text="x", tag="x", kind="attraction"))
    assert "403" in e.value.message and "API key not valid" in e.value.message


def test_network_error_is_raised():
    def boom(request):
        raise httpx.ConnectError("down")
    client = GoogleClient(SETTINGS, transport=httpx.MockTransport(boom))
    with pytest.raises(ProviderRequestError):
        GoogleRoutesProvider(client).compute_route(LatLng(lat=10, lng=20), LatLng(lat=10.1, lng=20.1),
                                                   TransportMode.CAB, None, CITY)


def test_routes_traffic_aware_request_and_fare():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"routes": [{
            "distanceMeters": 5400, "duration": "960s", "staticDuration": "720s",
            "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC_mqNvxq`@"},
            "travelAdvisory": {"transitFare": {"currencyCode": "INR", "units": "20"}},
        }]})

    client = GoogleClient(SETTINGS, transport=httpx.MockTransport(handler))
    r = GoogleRoutesProvider(client).compute_route(LatLng(lat=10, lng=20), LatLng(lat=10.1, lng=20.1),
                                                   TransportMode.CAB, None, CITY)
    assert seen["body"]["travelMode"] == "DRIVE" and seen["body"]["routingPreference"] == "TRAFFIC_AWARE"
    assert r.distance_km == 5.4 and r.duration_min == 16 and r.duration_without_traffic_min == 12
    assert r.traffic_aware and r.fare.verified and r.fare.amount == 20
    assert len(r.polyline) == 3


def test_transit_mode_filters():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"routes": []})

    client = GoogleClient(SETTINGS, transport=httpx.MockTransport(handler))
    r = GoogleRoutesProvider(client).compute_route(LatLng(lat=10, lng=20), LatLng(lat=10.1, lng=20.1),
                                                   TransportMode.METRO, None, CITY)
    assert seen["body"]["transitPreferences"]["allowedTravelModes"] == ["SUBWAY", "LIGHT_RAIL"]
    assert r.available is False


def test_decode_polyline_reference_example():
    pts = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert [(round(p.lat, 3), round(p.lng, 3)) for p in pts] == [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
