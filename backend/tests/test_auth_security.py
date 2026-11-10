"""Sign-in, sessions, authorization, CSRF, idempotency, rate limits, headers and input hardening."""
import datetime as dt
import json
import logging

import httpx
import pytest

from tests.conftest import USER_EMAIL, login


def _db():
    from app.db import database

    return database._SessionLocal()


def _set_env(monkeypatch, **env):
    from app.core.config import get_settings

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()


def _request_code(c, email=USER_EMAIL):
    return c.post("/api/auth/request-code", json={"email": email})


def _wrong(code: str) -> str:
    """A valid-looking code that differs from `code`."""
    return f"{(int(code) + 1) % 1_000_000:06d}"


def _forwarded_request(xff: str):
    """A request that arrived from peer 10.0.0.1 with the given X-Forwarded-For header."""
    from starlette.requests import Request

    return Request({"type": "http", "headers": [(b"x-forwarded-for", xff.encode())], "client": ("10.0.0.1", 1234)})


# ------------------------------------------------------------------ code flow
def test_code_flow_success(client, mailer):
    r = _request_code(client, "  Traveller@Example.COM ")
    assert r.status_code == 202 and r.json() == {"sent": True, "expires_in": 600}
    assert mailer.sent[-1][0] == USER_EMAIL   # lower-cased and trimmed
    code = mailer.last_code(USER_EMAIL)
    assert len(code) == 6 and code.isdigit()
    r = client.post("/api/auth/verify", json={"email": USER_EMAIL, "code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == USER_EMAIL and body["user"]["role"] == "user" and body["csrf_token"]
    cookie = r.headers["set-cookie"].lower()
    assert "ta_session=" in cookie and "httponly" in cookie and "path=/" in cookie and "samesite=lax" in cookie
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json() == body


def test_only_hashes_are_stored(client, mailer):
    from app.db.models import AuthSession, LoginCode

    _request_code(client)
    code = mailer.last_code(USER_EMAIL)
    with _db() as db:
        row = db.query(LoginCode).one()
        assert code not in row.code_hash and len(row.code_hash) == 64
    client.post("/api/auth/verify", json={"email": USER_EMAIL, "code": code})
    token = client.cookies.get("ta_session")
    with _db() as db:
        s = db.query(AuthSession).one()
        assert token and s.token_hash != token and len(s.token_hash) == 64


def test_wrong_code(client, mailer):
    _request_code(client)
    r = client.post("/api/auth/verify", json={"email": USER_EMAIL, "code": _wrong(mailer.last_code(USER_EMAIL))})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_code"
    assert client.get("/api/auth/me").status_code == 401


def test_code_expiry(client, mailer):
    from app.db.models import LoginCode

    _request_code(client)
    with _db() as db:
        db.query(LoginCode).update({"expires_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)})
        db.commit()
    r = client.post("/api/auth/verify", json={"email": USER_EMAIL, "code": mailer.last_code(USER_EMAIL)})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_code"


def test_attempt_limit_kills_code(client, mailer):
    _request_code(client)
    code = mailer.last_code(USER_EMAIL)
    messages = set()
    for _ in range(5):
        r = client.post("/api/auth/verify", json={"email": USER_EMAIL, "code": _wrong(code)})
        assert r.status_code == 400
        messages.add(r.json()["error"]["message"])
    r = client.post("/api/auth/verify", json={"email": USER_EMAIL, "code": code})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_code"
    assert len(messages) == 1 and r.json()["error"]["message"] in messages   # same message for every case


def test_code_single_use(client, mailer, new_client):
    _request_code(client)
    code = mailer.last_code(USER_EMAIL)
    assert client.post("/api/auth/verify", json={"email": USER_EMAIL, "code": code}).status_code == 200
    r = new_client().post("/api/auth/verify", json={"email": USER_EMAIL, "code": code})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_code"


def test_new_code_invalidates_old(client, mailer):
    _request_code(client)
    first = mailer.last_code(USER_EMAIL)
    _request_code(client)
    second = mailer.last_code(USER_EMAIL)
    if first != second:
        assert client.post("/api/auth/verify", json={"email": USER_EMAIL, "code": first}).status_code == 400
    assert client.post("/api/auth/verify", json={"email": USER_EMAIL, "code": second}).status_code == 200


def test_no_account_enumeration(client, mailer, new_client):
    from app.db.models import User

    login(new_client(), mailer, "known@example.com")
    known = _request_code(client, "known@example.com")
    unknown = _request_code(client, "nobody@example.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    with _db() as db:   # users are created on verify, not on request
        assert db.query(User).filter_by(email="nobody@example.com").first() is None


def test_admin_role_from_admin_emails(admin_client):
    assert admin_client.session_info["user"]["role"] == "admin"


def test_dev_code_logged_when_email_not_configured(client, caplog):
    with caplog.at_level(logging.WARNING):
        r = _request_code(client)
    assert r.status_code == 202
    assert any("DEV ONLY sign-in code for traveller@example.com:" in m for m in caplog.messages)
    assert client.get("/api/meta/status").json()["auth"] == {"email_configured": False, "dev_codes_in_console": True}


def test_production_without_resend_key_is_503(client, monkeypatch):
    _set_env(monkeypatch, APP_ENV="production", RESEND_API_KEY="")
    r = _request_code(client)
    assert r.status_code == 503 and r.json()["error"]["code"] == "email_not_configured"
    assert client.get("/api/meta/status").json()["auth"] == {"email_configured": False,
                                                             "dev_codes_in_console": False}


def test_production_without_secret_key_fails_startup(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import Settings, get_settings
    from app.main import app

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings(app_env="production", secret_key="").check_startup()
    with pytest.raises(RuntimeError, match="32"):
        Settings(app_env="production", secret_key="short").check_startup()
    _set_env(monkeypatch, APP_ENV="production", SECRET_KEY="")
    try:
        with pytest.raises(RuntimeError, match="SECRET_KEY"), TestClient(app):
            pass
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_resend_payload():
    from app.services.email_service import ResendMailer

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "abc"})

    ResendMailer("re_test_key", "TripAura <login@example.com>", transport=httpx.MockTransport(handler)) \
        .send_code("a@example.com", "123456", 10)
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["auth"] == "Bearer re_test_key"
    b = seen["body"]
    assert b["from"] == "TripAura <login@example.com>" and b["to"] == ["a@example.com"]
    assert b["subject"] == "Your TripAura sign-in code"
    assert "123456" in b["text"] and "123456" in b["html"]


def test_resend_failure_is_502(client):
    from app.main import app
    from app.services.email_service import ResendMailer, get_mailer

    failing = ResendMailer("k", "x@example.com", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    app.dependency_overrides[get_mailer] = lambda: failing
    try:
        r = _request_code(client)
    finally:
        app.dependency_overrides.pop(get_mailer, None)
    assert r.status_code == 502 and r.json()["error"]["code"] == "email_failed"


# ------------------------------------------------------------------ sessions
def test_me_unauthenticated(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"


def test_session_expiry(auth_client):
    from app.db.models import AuthSession

    with _db() as db:
        db.query(AuthSession).update({"expires_at": dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)})
        db.commit()
    assert auth_client.get("/api/auth/me").status_code == 401
    with _db() as db:   # expired sessions are cleaned up
        assert db.query(AuthSession).count() == 0


def test_logout(auth_client):
    token = auth_client.cookies.get("ta_session")
    assert auth_client.post("/api/auth/logout", headers={"X-CSRF-Token": ""}).status_code == 403
    r = auth_client.post("/api/auth/logout")
    assert r.status_code == 204
    assert "ta_session=" in r.headers["set-cookie"] and "max-age=0" in r.headers["set-cookie"].lower()
    assert auth_client.get("/api/auth/me").status_code == 401
    auth_client.cookies.set("ta_session", token)   # the old token is dead server-side
    assert auth_client.get("/api/auth/me").status_code == 401


def test_delete_account(auth_client, other_client, base_request):
    from app.db.models import AuthSession, IdempotencyRecord, LoginCode, Trip, User

    other_trip = other_client.post("/api/trips", json=base_request).json()["trip_id"]
    tid = auth_client.post("/api/trips", json=base_request).json()["trip_id"]
    token = auth_client.cookies.get("ta_session")
    assert auth_client.delete("/api/auth/account", headers={"X-CSRF-Token": "nope"}).status_code == 403

    r = auth_client.delete("/api/auth/account")
    assert r.status_code == 204
    assert "ta_session=" in r.headers["set-cookie"] and "max-age=0" in r.headers["set-cookie"].lower()
    with _db() as db:
        assert db.query(User).filter_by(email=USER_EMAIL).first() is None
        assert db.get(Trip, tid) is None
        assert db.get(Trip, other_trip) is not None             # other users untouched
        assert db.query(LoginCode).filter_by(email=USER_EMAIL).count() == 0
        uid = auth_client.session_info["user"]["id"]
        assert db.query(AuthSession).filter_by(user_id=uid).count() == 0
        assert db.query(IdempotencyRecord).filter_by(user_id=uid).count() == 0
        assert db.query(IdempotencyRecord).count() == 1         # the other user's record
    auth_client.cookies.set("ta_session", token)
    assert auth_client.get("/api/auth/me").status_code == 401
    assert other_client.get(f"/api/trips/{other_trip}").status_code == 200


# ------------------------------------------------------------------ authorization
def test_trips_require_session(client, base_request):
    for method, path, body in [("post", "/api/trips", base_request), ("post", "/api/trips/preview", base_request),
                               ("get", "/api/trips", None), ("get", "/api/trips/1", None),
                               ("delete", "/api/trips/1", None), ("post", "/api/trips/1/regenerate", None),
                               ("post", "/api/trips/1/live", {"current": {"lat": 1, "lng": 1}, "day_number": 1})]:
        r = client.request(method, path, json=body)
        assert r.status_code == 401, (method, path)
        assert r.json()["error"]["code"] == "not_authenticated"


def test_public_endpoints_stay_public(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/meta/options").status_code == 200
    assert client.post("/api/routes/compare", json={"city": "Jaipur", "origin": {"lat": 26.916, "lng": 75.809},
                                                    "destination": {"lat": 26.92, "lng": 75.82}}).status_code == 200


def test_owner_only_access_and_admin(auth_client, admin_client, other_client, base_request):
    tid = auth_client.post("/api/trips", json=base_request).json()["trip_id"]
    for r in (other_client.get(f"/api/trips/{tid}"), other_client.delete(f"/api/trips/{tid}"),
              other_client.post(f"/api/trips/{tid}/regenerate"),
              other_client.post(f"/api/trips/{tid}/live",
                                json={"current": {"lat": 26.9, "lng": 75.8}, "day_number": 1})):
        assert r.status_code == 404 and r.json()["error"]["code"] == "trip_not_found"
    assert other_client.get("/api/trips").json() == []
    assert other_client.get("/api/trips?all=true").json() == []          # not an admin: ignored

    assert admin_client.get(f"/api/trips/{tid}").status_code == 200
    assert admin_client.get("/api/trips").json() == []            # own trips by default
    assert [t["id"] for t in admin_client.get("/api/trips?all=true").json()] == [tid]
    assert admin_client.post(f"/api/trips/{tid}/regenerate").status_code == 404   # write: owner only
    assert admin_client.delete(f"/api/trips/{tid}").status_code == 204
    assert auth_client.get(f"/api/trips/{tid}").status_code == 404


def test_legacy_trips_admin_only(auth_client, admin_client, base_request):
    from app.db.models import Trip

    tid = auth_client.post("/api/trips", json=base_request).json()["trip_id"]
    with _db() as db:
        db.get(Trip, tid).user_id = None
        db.commit()
    assert auth_client.get(f"/api/trips/{tid}").status_code == 404
    assert auth_client.get("/api/trips").json() == []
    assert admin_client.get(f"/api/trips/{tid}").status_code == 200


def test_migration_adds_user_id(tmp_path):
    import sqlalchemy as sa

    from app.db import database

    url = f"sqlite:///{tmp_path / 'old.db'}"
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE trips (id INTEGER PRIMARY KEY, title VARCHAR(200))"))
        conn.execute(sa.text("INSERT INTO trips (id, title) VALUES (1, 'old')"))
    eng.dispose()
    try:
        for _ in range(2):   # idempotent
            e = database.init_engine(url)
            cols = {c["name"] for c in sa.inspect(e).get_columns("trips")}
            assert "user_id" in cols
        with e.connect() as conn:
            assert conn.execute(sa.text("SELECT user_id FROM trips WHERE id = 1")).scalar() is None
        e.dispose()
    finally:
        database.init_engine(f"sqlite:///{tmp_path / 'test.db'}")


# ------------------------------------------------------------------ CSRF / origin
def test_csrf_missing_or_wrong(auth_client, base_request):
    tid = auth_client.post("/api/trips", json=base_request).json()["trip_id"]
    for headers in ({"X-CSRF-Token": ""}, {"X-CSRF-Token": "wrong-token"}):
        r = auth_client.delete(f"/api/trips/{tid}", headers=headers)
        assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    assert auth_client.get(f"/api/trips/{tid}", headers={"X-CSRF-Token": ""}).status_code == 200  # safe method


def test_bad_origin_rejected(auth_client, client, base_request):
    evil = {"Origin": "https://evil.example"}
    r = auth_client.post("/api/trips/preview", json=base_request, headers=evil)
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = client.post("/api/auth/request-code", json={"email": "x@example.com"}, headers=evil)
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    r = client.post("/api/auth/verify", json={"email": "x@example.com", "code": "123456"}, headers={"Origin": "null"})
    assert r.status_code == 403
    assert client.post("/api/auth/request-code", json={"email": "x@example.com"},
                       headers={"Origin": "http://localhost:5173"}).status_code == 202
    assert client.post("/api/auth/request-code", json={"email": "y@example.com"},
                       headers={"Origin": "http://testserver"}).status_code == 202   # same host
    assert client.get("/api/health", headers=evil).status_code == 200                # safe method


def test_cors_credentials_with_explicit_origin(client):
    r = client.options("/api/trips", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                                              "Access-Control-Request-Headers": "content-type,x-csrf-token"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert r.headers["access-control-allow-credentials"] == "true"
    r = client.options("/api/trips", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_wildcard_is_dropped():
    from app.core.config import Settings

    assert Settings(cors_origins="*,https://app.example.com/").allowed_origins == ["https://app.example.com"]


# ------------------------------------------------------------------ idempotency
def test_idempotent_replay(auth_client, base_request):
    h = {"X-Idempotency-Key": "create-trip-0001"}
    first = auth_client.post("/api/trips", json=base_request, headers=h)
    assert first.status_code == 201 and "idempotent-replayed" not in first.headers
    again = auth_client.post("/api/trips", json=base_request, headers=h)
    assert again.status_code == 201 and again.headers["idempotent-replayed"] == "true"
    assert again.json()["trip_id"] == first.json()["trip_id"]
    assert len(auth_client.get("/api/trips").json()) == 1      # generated once


def test_idempotency_key_reused_with_other_body(auth_client, base_request):
    h = {"X-Idempotency-Key": "create-trip-0002"}
    assert auth_client.post("/api/trips", json=base_request, headers=h).status_code == 201
    r = auth_client.post("/api/trips", json={**base_request, "num_days": 1}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "idempotency_key_reused"


def test_idempotency_key_required(client, mailer, base_request):
    login(client, mailer, auto_idempotency=False)
    for headers in ({}, {"X-Idempotency-Key": "short"}, {"X-Idempotency-Key": "bad key with spaces"}):
        r = client.post("/api/trips", json=base_request, headers=headers)
        assert r.status_code == 400 and r.json()["error"]["code"] == "idempotency_key_required"
    tid = client.post("/api/trips", json=base_request, headers={"X-Idempotency-Key": "k-12345678"}).json()["trip_id"]
    r = client.post(f"/api/trips/{tid}/regenerate")
    assert r.status_code == 400 and r.json()["error"]["code"] == "idempotency_key_required"
    r = client.post(f"/api/trips/{tid}/regenerate", headers={"X-Idempotency-Key": "regen-0001"})
    assert r.status_code == 200
    r = client.post(f"/api/trips/{tid}/regenerate", headers={"X-Idempotency-Key": "regen-0001"})
    assert r.status_code == 200 and r.headers["idempotent-replayed"] == "true"


def test_idempotency_in_flight(auth_client, base_request):
    from app.schemas.trip import TripRequest
    from app.services.idempotency import Idempotency

    uid = auth_client.session_info["user"]["id"]
    body = TripRequest.model_validate(base_request).model_dump(mode="json")
    with _db() as db:
        assert Idempotency(db, uid, "inflight-0001", "POST /api/trips", body).begin() is None
    r = auth_client.post("/api/trips", json=base_request, headers={"X-Idempotency-Key": "inflight-0001"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "request_in_progress"


def test_failed_generation_releases_key(auth_client, base_request):
    from app.db.models import IdempotencyRecord

    h = {"X-Idempotency-Key": "fails-first-01"}
    r = auth_client.post("/api/trips", json={**base_request, "destination_city": "Paris"}, headers=h)
    assert r.status_code == 422
    with _db() as db:
        assert db.query(IdempotencyRecord).count() == 0


# ------------------------------------------------------------------ rate limits
def test_request_code_rate_limit_per_email(client, mailer):
    for _ in range(3):
        assert _request_code(client).status_code == 202
    r = _request_code(client)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) > 0


def test_request_code_rate_limit_per_ip(client, mailer):
    for i in range(10):
        assert _request_code(client, f"user{i}@example.com").status_code == 202
    r = _request_code(client, "user99@example.com")
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_generation_rate_limit(auth_client, base_request):
    for _ in range(6):
        assert auth_client.post("/api/trips/preview", json=base_request).status_code == 200
    r = auth_client.post("/api/trips/preview", json=base_request)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited" and "retry-after" in r.headers


def test_rate_limit_can_be_disabled(client, mailer, monkeypatch):
    _set_env(monkeypatch, RATE_LIMIT_ENABLED="false")
    for _ in range(5):
        assert _request_code(client).status_code == 202


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
    for r in (client.get("/api/health"), client.get("/api/trips")):
        h = r.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer" and h["cross-origin-opener-policy"] == "same-origin"
        assert h["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
        assert h["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        assert "strict-transport-security" not in h
        assert r.headers["content-type"].startswith("application/json")
    assert client.get("/api/auth/me").headers["cache-control"] == "no-store"
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


def test_samesite_none_forces_secure():
    from app.core.config import Settings

    assert Settings(cookie_secure=False, cookie_samesite="none").cookie_secure_effective is True
    assert Settings(cookie_secure=False, cookie_samesite="lax").cookie_secure_effective is False


# ------------------------------------------------------------------ input limits
def test_input_limits(auth_client, client, base_request):
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
        assert auth_client.post("/api/trips/preview", json=body).status_code == 422, body
    for q in ("a", "x" * 101):
        assert client.get("/api/geo/cities", params={"q": q}).status_code == 422
        assert client.get("/api/geo/addresses", params={"q": q}).status_code == 422
    assert client.get("/api/geo/addresses", params={"q": "abc", "lat": 91, "lng": 0}).status_code == 422
    for email in ("not-an-email", "a@b", "x" * 250 + "@example.com", "a@example.com\r\nBcc: z@example.com"):
        assert client.post("/api/auth/request-code", json={"email": email}).status_code == 422, email
    for code in ("12345", "1234567", "12345a", " 123456"):
        assert client.post("/api/auth/verify", json={"email": USER_EMAIL, "code": code}).status_code == 422
    assert client.post("/api/auth/request-code", json={"email": USER_EMAIL, "admin": True}).status_code == 422
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
