"""Application settings loaded from environment variables (and an optional backend/.env file)."""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class DataMode(str, Enum):
    MOCK = "mock"   # bundled Jaipur demo dataset
    OPEN = "open"   # worldwide open data (OSM, Overture, Wikidata, Wikivoyage) + optional Google enrichment
    LIVE = "live"   # Google Maps Platform only


class RoutingEngine(str, Enum):
    HEURISTIC = "heuristic"   # distance x speed profiles (labelled as estimates)
    OSRM = "osrm"             # OSRM servers for walking/driving distances and times


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    data_mode: DataMode = DataMode.OPEN

    google_maps_api_key: str = ""
    google_http_timeout_seconds: float = 10.0
    # In open mode, enrich scheduled places with Google ratings/reviews when a key is set.
    google_enrichment: bool = True

    # ---- open data ----------------------------------------------------------
    # Identify the app to OSM/Wikimedia services. Their policies require a contact URL or email;
    # Wikimedia returns HTTP 403 without one. Point this at your own deployment/repo.
    open_user_agent: str = "TripAura/0.1 (+https://github.com/ranjanvrma/trip-aura)"
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    overpass_urls: str = ("https://overpass-api.de/api/interpreter,"
                          "https://overpass.private.coffee/api/interpreter,"
                          "https://overpass.kumi.systems/api/interpreter")
    overture_enabled: bool = True
    overture_release: str = ""          # empty = discover the latest release from the STAC catalog
    wikivoyage_enabled: bool = True
    city_cache_days: int = Field(default=30, ge=1, le=365)
    osm_time_budget_seconds: float = 90.0   # total time allowed for the best-effort OSM layer per city
    open_http_timeout_seconds: float = 90.0
    fx_url: str = "https://api.frankfurter.dev/v1/latest"

    routing_engine: RoutingEngine = RoutingEngine.HEURISTIC
    osrm_driving_url: str = "https://router.project-osrm.org/route/v1/driving"
    osrm_walking_url: str = "https://routing.openstreetmap.de/routed-foot/route/v1/foot"

    # ---- AI -----------------------------------------------------------------
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    ai_enabled: bool = False

    # ---- app ----------------------------------------------------------------
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'tripaura.db').as_posix()}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"

    # Engine tuning (not secrets; overridable for experiments)
    max_candidate_places: int = Field(default=150, ge=10, le=500)
    max_food_candidates: int = Field(default=800, ge=10, le=3000)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def overpass_url_list(self) -> list[str]:
        return [u.strip() for u in self.overpass_urls.split(",") if u.strip()]

    @property
    def google_configured(self) -> bool:
        return bool(self.google_maps_api_key.strip())

    @property
    def ai_available(self) -> bool:
        return self.ai_enabled and bool(self.anthropic_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
