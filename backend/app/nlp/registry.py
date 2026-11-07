"""Process-wide NLP singletons (lazy)."""
from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.nlp.city_index import CityIndex
from app.nlp.semantic import SemanticMatcher


@lru_cache
def get_city_index() -> CityIndex:
    s = get_settings()
    return CityIndex(s.data_dir, s.geonames_url, s.open_user_agent)


@lru_cache
def get_semantic() -> SemanticMatcher:
    s = get_settings()
    return SemanticMatcher(s.semantic_model, s.data_dir, enabled=s.semantic_enabled)
