"""Origin checks, CORS, rate limits, security headers, input limits and URL / query sanitising."""
import pytest


def _set_env(monkeypatch, **env):
    from app.core.config import get_settings

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def _forwarded_request(xff: str):
    """A request that arrived from peer 10.0.0.1 with the given X-Forwarded-For header."""
    from starlette.requests import Request

    return Request({"type": "http", "headers": [(b"x-forwarded-for", xff.encode())], "client": ("10.0.0.1", 1234)})


# ------------------------------------------------------------------ origin / CORS
def test_public_endpoints(client, base_request):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/meta/options").status_code == 200
    assert client.post("/api/trips/preview", json=base_request).status_code == 200
    assert client.post("/api/routes/compare", json={"city": "Jaipur", "origin": {"lat": 26.916, "lng": 75.809},
                                                    "destination": {"lat": 26.92, "lng": 75.82}}).status_code == 200


def test_bad_origin_rejected(client, base_request):
    evil = {"Origin": "https://evil.example"}
    r = client.post("/api/trips/preview", json=base_request, headers=evil)
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    assert client.post("/api/nlp/parse-trip", json={"text": "3 days in Rome"}, headers={"Origin": "null"}).status_code == 403
    assert client.post("/api/trips/preview", json=base_request,
                       headers={"Origin": "http://localhost:5173"}).status_code == 200
    assert client.post("/api/trips/preview", json=base_request,
                       headers={"Origin": "http://testserver"}).status_code == 200      # same host
    assert client.get("/api/health", headers=evil).status_code == 200                 # safe method


def test_cors_explicit_origins_without_credentials(client):
    r = client.options("/api/trips/preview", headers={"Origin": "http://localhost:5173",
                                                      "Access-Control-Request-Method": "POST",
                                                      "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in r.headers      # no cookies: the API is stateless
    r = client.options("/api/trips/preview", headers={"Origin": "https://evil.example",
                                                      "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_wildcard_is_dropped():
    from app.core.config import Settings

    assert Settings(cors_origins="*,https://app.example.com/").allowed_origins == ["https://app.example.com"]


# ------------------------------------------------------------------ rate limits
def test_generation_rate_limit_per_ip(client, base_request):
    for _ in range(6):
        assert client.post("/api/trips/preview", json=base_request).status_code == 200
    r = client.post("/api/trips/preview", json=base_request)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) > 0


def test_nlp_rate_limit_per_ip(client):
    # 30 per minute; the bucket refills while the loop runs, so allow a few extra calls before the 429
    codes = [client.post("/api/nlp/parse-trip", json={"text": "2 days in Jaipur"}).status_code for _ in range(40)]
    assert codes[:30] == [200] * 30 and 429 in codes[30:]


def test_rate_limit_can_be_disabled(client, base_request, monkeypatch):
    _set_env(monkeypatch, RATE_LIMIT_ENABLED="false")
    for _ in range(8):
        assert client.post("/api/trips/preview", json=base_request).status_code == 200


def test_forwarded_for_only_when_trusted():
    from app.core.config import Settings
    from app.core.ratelimit import client_ip

    req = _forwarded_request("203.0.113.9, 10.0.0.1")
    assert client_ip(req, Settings(trust_proxy_headers=False)) == "10.0.0.1"
    # one trusted proxy: the entry it appended (rightmost) is the client
    assert client_ip(req, Settings(trust_proxy_headers=True)) == "10.0.0.1"
    # two trusted proxies (Vercel rewrite + Azure ingress): second from the right
    assert client_ip(req, Settings(trust_proxy_headers=True, trusted_proxy_count=2)) == "203.0.113.9"


def test_forwarded_for_spoofing_is_ignored():
    from app.core.config import Settings
    from app.core.ratelimit import client_ip

    # the client sent its own "1.2.3.4"; the trusted proxy appended the real peer address
    assert client_ip(_forwarded_request("1.2.3.4, 198.51.100.7"), Settings(trust_proxy_headers=True)) == "198.51.100.7"


def test_token_bucket_refills():
    from app.core.ratelimit import Limit, RateLimiter

    lim, rl = Limit(2, 60), RateLimiter()
    assert rl.hit("t", "k", lim, now=0) == 0 and rl.hit("t", "k", lim, now=0) == 0
    assert rl.hit("t", "k", lim, now=0) == 30
    assert rl.hit("t", "k", lim, now=31) == 0


# ------------------------------------------------------------------ headers
def test_security_headers(client):
    for r in (client.get("/api/health"), client.get("/api/does-not-exist")):
        h = r.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer" and h["cross-origin-opener-policy"] == "same-origin"
        assert h["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
        assert h["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        assert "strict-transport-security" not in h
        assert r.headers["content-type"].startswith("application/json")
    docs = client.get("/docs")
    assert docs.status_code == 200 and "cdn.jsdelivr.net" in docs.headers["content-security-policy"]


def test_hsts_only_on_https(client, new_client, monkeypatch):
    assert "strict-transport-security" in new_client(base_url="https://testserver").get("/api/health").headers
    fwd = {"X-Forwarded-Proto": "https"}
    assert "strict-transport-security" not in client.get("/api/health", headers=fwd).headers
    _set_env(monkeypatch, TRUST_PROXY_HEADERS="true")
    h = client.get("/api/health", headers=fwd).headers
    assert h["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_docs_disabled_in_production(client, monkeypatch):
    _set_env(monkeypatch, APP_ENV="production")
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    _set_env(monkeypatch, DOCS_ENABLED="true")
    assert client.get("/openapi.json").status_code == 200


# ------------------------------------------------------------------ input limits
def test_input_limits(client, base_request, monkeypatch):
    # the per-IP generation limit runs before validation; switch it off to see every 422
    _set_env(monkeypatch, RATE_LIMIT_ENABLED="false")
    cases = [
        {**base_request, "interests": [f"i{n}" for n in range(21)]},
        {**base_request, "interests": ["x" * 101]},
        {**base_request, "unexpected": True},
        {**base_request, "accommodation": {"name_or_address": "x" * 301}},
        {**base_request, "accommodation": {"name_or_address": "Hotel", "extra": 1}},
        {**base_request, "destination_city": "x" * 121},
        {**base_request, "budget": 1e12},
    ]
    for body in cases:
        assert client.post("/api/trips/preview", json=body).status_code == 422, body
    for q in ("a", "x" * 101):
        assert client.get("/api/geo/cities", params={"q": q}).status_code == 422
        assert client.get("/api/geo/addresses", params={"q": q}).status_code == 422
    assert client.get("/api/geo/addresses", params={"q": "abc", "lat": 91, "lng": 0}).status_code == 422
    assert client.post("/api/nlp/parse-trip", json={"text": "x" * 2001}).status_code == 422


# ------------------------------------------------------------------ URL / identifier sanitising
def test_safe_http_url():
    from app.core.urls import safe_http_url, wikidata_qid

    assert safe_http_url("https://example.com/a?b=1") == "https://example.com/a?b=1"
    assert safe_http_url(" http://example.com ") == "http://example.com"
    for bad in ("javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,x", "//evil.example",
                "ftp://example.com", "https://", "https://exa mple.com", "http://a.com/\nx", None, 5, ""):
        assert safe_http_url(bad) is None, bad
    assert wikidata_qid("Q42") == "Q42" and wikidata_qid("Q42;Q7") == "Q42"
    assert wikidata_qid("Q42}") is None and wikidata_qid("x") is None


def test_place_and_osm_urls_are_sanitised():
    from app.providers.open.osm import element_to_place
    from app.schemas.place import Place

    p = Place(id="x", name="x", kind="attraction", location={"lat": 1, "lng": 1}, source="osm",
              google_maps_uri="javascript:alert(1)")
    assert p.google_maps_uri is None
    el = {"type": "node", "id": 1, "lat": 1.0, "lon": 2.0,
          "tags": {"name": "Cafe X", "amenity": "cafe", "website": "javascript:alert(document.cookie)",
                   "wikidata": "Q1\"]; evil"}}
    place = element_to_place(el, set())
    assert place.description is None and "wikidata" not in place.external_ids
    el["tags"]["website"] = "https://cafe.example"
    assert element_to_place(el, set()).description == "https://cafe.example"


def test_query_builders_reject_unsafe_values():
    from app.providers.open import osm, overture

    assert overture.safe_release("2025-10-22.0") == "2025-10-22.0"
    for bad in ("2025-10-22'; DROP TABLE x; --", "../../etc", ""):
        with pytest.raises(ValueError):
            overture.safe_release(bad)
    assert overture.safe_memory_limit("256MB") == "256MB"
    with pytest.raises(ValueError):
        overture.safe_memory_limit("256MB'; INSTALL x; --")
    with pytest.raises(ValueError):
        osm.build_queries(float("nan"), 1.0, 5, 2)
    q = osm.build_queries(41.9, 12.5, 5, 2)
    assert all("41.85" in v or "41.88" in v for v in q.values())
