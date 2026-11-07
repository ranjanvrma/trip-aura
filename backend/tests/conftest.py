import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_MODE", "mock")
os.environ.setdefault("AI_ENABLED", "false")
os.environ.setdefault("SEMANTIC_ENABLED", "false")
os.environ["GOOGLE_MAPS_API_KEY"] = ""


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
