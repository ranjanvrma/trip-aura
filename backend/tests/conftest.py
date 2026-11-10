import os
import re
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_MODE", "mock")
os.environ.setdefault("AI_ENABLED", "false")
os.environ.setdefault("SEMANTIC_ENABLED", "false")
os.environ.setdefault("WARMUP_ON_START", "false")
os.environ["GOOGLE_MAPS_API_KEY"] = ""
# auth / security: local plain-http test client, fixed signing key, never real email
os.environ["APP_ENV"] = "development"
os.environ["COOKIE_SECURE"] = "false"
os.environ["COOKIE_SAMESITE"] = "lax"
os.environ["SECRET_KEY"] = "test-secret-key-0123456789-abcdefghijklmnop"
os.environ["RESEND_API_KEY"] = ""
os.environ["ADMIN_EMAILS"] = "admin@example.com"
os.environ["TRUST_PROXY_HEADERS"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "true"
os.environ.pop("DOCS_ENABLED", None)

USER_EMAIL = "traveller@example.com"
ADMIN_EMAIL = "admin@example.com"
GENERATION_PATH = re.compile(r"^/api/trips(/\d+/regenerate)?$")


@pytest.fixture
def base_request() -> dict:
    return {
        "accommodation": {"type": "hotel", "name_or_address": "Hotel on MI Road"},
        "destination_city": "Jaipur",
        "start_date": "2026-11-10",  # a Tuesday
        "num_days": 2,
        "budget": 12000,
        "currency": "INR",
        "interests": ["museums", "monuments", "photography"],
        "food_preferences": ["vegetarian"],
        "food_categories": ["street_food", "local_cuisine"],
        "transport_modes": ["walking", "auto", "metro"],
        "pace": "moderate",
    }


@pytest.fixture
def mock_service():
    from app.core.config import Settings
    from app.services.itinerary_service import ItineraryService
    from app.services.providers import build_providers

    settings = Settings(data_mode="mock", ai_enabled=False, google_maps_api_key="")
    return ItineraryService(build_providers(settings), settings)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.core.ratelimit import limiter

    limiter.reset()
    yield
    limiter.reset()


class FakeMailer:
    """Captures sign-in codes instead of sending email."""

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send_code(self, email: str, code: str, expires_minutes: int) -> None:
        self.sent.append((email, code))

    def last_code(self, email: str) -> str:
        return next(c for e, c in reversed(self.sent) if e == email)


@pytest.fixture
def mailer():
    from app.main import app
    from app.services.email_service import get_mailer

    fake = FakeMailer()
    app.dependency_overrides[get_mailer] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_mailer, None)


def login(c, mailer: FakeMailer, email: str = USER_EMAIL, auto_idempotency: bool = True):
    """Sign `c` in through the real code flow; keeps the cookie and sends the CSRF header by default.

    With auto_idempotency, trip create/regenerate POSTs get a fresh X-Idempotency-Key unless one is set."""
    r = c.post("/api/auth/request-code", json={"email": email})
    assert r.status_code == 202, r.text
    r = c.post("/api/auth/verify", json={"email": email, "code": mailer.last_code(email)})
    assert r.status_code == 200, r.text
    data = r.json()
    c.headers["X-CSRF-Token"] = data["csrf_token"]
    if auto_idempotency:
        def add_key(request):
            if request.method == "POST" and GENERATION_PATH.match(request.url.path) \
                    and "x-idempotency-key" not in request.headers:
                request.headers["X-Idempotency-Key"] = uuid.uuid4().hex
        c.event_hooks = {**c.event_hooks, "request": [*c.event_hooks.get("request", []), add_key]}
    return data


@pytest.fixture
def new_client(client):
    """Factory for extra clients (own cookie jar) on the same app and database."""
    from fastapi.testclient import TestClient

    from app.main import app

    def make(**kwargs):
        return TestClient(app, **kwargs)
    return make


@pytest.fixture
def auth_client(client, mailer):
    """`client` signed in as an ordinary user."""
    client.session_info = login(client, mailer)
    return client


@pytest.fixture
def admin_client(new_client, mailer):
    c = new_client()
    c.session_info = login(c, mailer, ADMIN_EMAIL)
    return c


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.db import database
    from app.main import app

    database.init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
