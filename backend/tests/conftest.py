import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_MODE", "mock")
os.environ.setdefault("AI_ENABLED", "false")
os.environ.setdefault("SEMANTIC_ENABLED", "false")
os.environ.setdefault("WARMUP_ON_START", "false")
os.environ["GOOGLE_MAPS_API_KEY"] = ""
# security: development mode, real per-IP rate limits, proxy headers not trusted
os.environ["APP_ENV"] = "development"
os.environ["TRUST_PROXY_HEADERS"] = "false"
os.environ["RATE_LIMIT_ENABLED"] = "true"
os.environ.pop("DOCS_ENABLED", None)


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


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client on a fresh SQLite database (the app's startup creates the tables)."""
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.main import app

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture
def new_client(client):
    """Factory for extra clients (e.g. another base URL) on the same app and database."""
    from fastapi.testclient import TestClient

    from app.main import app

    return lambda **kw: TestClient(app, **kw)
