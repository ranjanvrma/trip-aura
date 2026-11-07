from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.itinerary_service import ItineraryService
from app.services.providers import get_providers


@lru_cache
def _service(mode: str, key_present: bool) -> ItineraryService:
    return ItineraryService(get_providers(), get_settings())


def get_itinerary_service() -> ItineraryService:
    s = get_settings()
    return _service(s.data_mode.value, s.google_configured)
