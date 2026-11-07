from __future__ import annotations

from fastapi import APIRouter

from app.core.config import DataMode, get_settings
from app.schemas.trip import (
    PRESET_DIETS, PRESET_FOOD_CATEGORIES, PRESET_INTERESTS, SUPPORTED_CURRENCIES, AccommodationType, Pace, TransportMode,
)

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/status")
def status() -> dict:
    s = get_settings()
    live = s.data_mode == DataMode.LIVE
    return {
        "data_mode": s.data_mode.value,
        "google": {
            "configured": s.google_configured,
            "active": live and s.google_configured,
            "services": {"places": "Places API (New)", "routes": "Routes API", "geocoding": "Geocoding API",
                         "timezone": "Time Zone API"},
        },
        "ai": {"enabled": s.ai_enabled, "configured": bool(s.anthropic_api_key.strip()), "model": s.anthropic_model},
        "mock_city": "Jaipur" if not live else None,
        "problems": (["DATA_MODE=live but GOOGLE_MAPS_API_KEY is missing - requests will fail until it is set."]
                     if live and not s.google_configured else []),
    }


@router.get("/options")
def options() -> dict:
    return {
        "interests": PRESET_INTERESTS,
        "food_preferences": PRESET_DIETS,
        "food_categories": PRESET_FOOD_CATEGORIES,
        "transport_modes": [m.value for m in TransportMode],
        "paces": [p.value for p in Pace],
        "accommodation_types": [a.value for a in AccommodationType],
        "currencies": list(SUPPORTED_CURRENCIES),
    }
