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
    mode = s.data_mode
    problems: list[str] = []
    if mode == DataMode.LIVE and not s.google_configured:
        problems.append("DATA_MODE=live but GOOGLE_MAPS_API_KEY is missing - requests will fail until it is set.")
    duckdb_ok = True
    if mode == DataMode.OPEN and s.overture_enabled:
        try:
            import duckdb  # noqa: F401
        except ImportError:
            duckdb_ok = False
            problems.append("The 'duckdb' package is not installed, so the Overture places layer is skipped.")
    return {
        "data_mode": mode.value,
        "google": {
            "configured": s.google_configured,
            "active": s.google_configured and (mode == DataMode.LIVE
                                               or (mode == DataMode.OPEN and s.google_enrichment)),
            "role": {"live": "all places, ratings and routes", "open": "ratings/reviews enrichment",
                     "mock": "not used"}[mode.value],
            "services": {"places": "Places API (New)", "routes": "Routes API", "geocoding": "Geocoding API",
                         "timezone": "Time Zone API"},
        },
        "open_data": {
            "sources": ["Nominatim", "Overture Maps" + ("" if duckdb_ok else " (unavailable)"), "Wikidata",
                        "OpenStreetMap (Overpass)", "Wikivoyage"],
            "routing": s.routing_engine.value,
            "city_cache_days": s.city_cache_days,
        } if mode == DataMode.OPEN else None,
        "nlp": _nlp_status(),
        "ai": {"enabled": s.ai_enabled, "configured": bool(s.anthropic_api_key.strip()), "model": s.anthropic_model},
        "mock_city": "Jaipur" if mode == DataMode.MOCK else None,
        "worldwide": mode != DataMode.MOCK,
        "problems": problems,
    }


def _nlp_status() -> dict:
    from app.nlp.registry import get_city_index, get_semantic   # looked up per call (tests patch the registry)

    return {
        "semantic_matching": get_semantic().status,
        "city_index": "ready" if get_city_index().ready else "loads on first search",
        "features": ["city autocomplete", "address suggestions", "trip description parser",
                     "typo-tolerant interests", "semantic interest matching", "review sentiment"],
    }


@router.get("/options")
def options() -> dict:
    s = get_settings()
    return {
        "interests": PRESET_INTERESTS,
        "food_preferences": PRESET_DIETS,
        "food_categories": PRESET_FOOD_CATEGORIES,
        "transport_modes": [m.value for m in TransportMode],
        "paces": [p.value for p in Pace],
        "accommodation_types": [a.value for a in AccommodationType],
        "currencies": ["INR"] if s.data_mode == DataMode.MOCK else list(SUPPORTED_CURRENCIES),
    }
