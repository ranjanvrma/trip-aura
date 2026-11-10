"""Application settings loaded from environment variables (and an optional backend/.env file)."""
from __future__ import annotations

import logging
import secrets
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'tripaura.db').as_posix()}"
# Used by the legacy, currently disabled account endpoints when no secret is configured.
_PROCESS_SECRET = secrets.token_urlsafe(48)
log = logging.getLogger(__name__)


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
    duckdb_memory_limit: str = "256MB"   # cap for the Overture query (small hosting plans)
    duckdb_threads: int = 2
    city_cache_days: int = Field(default=30, ge=1, le=365)
    # time box for the best-effort OSM layer; its 3 queries run in parallel with the other sources
    osm_time_budget_seconds: float = 25.0
    open_http_timeout_seconds: float = 90.0
    fx_url: str = "https://api.frankfurter.dev/v1/latest"

    routing_engine: RoutingEngine = RoutingEngine.HEURISTIC
    osrm_driving_url: str = "https://router.project-osrm.org/route/v1/driving"
    osrm_walking_url: str = "https://routing.openstreetmap.de/routed-foot/route/v1/foot"

    # ---- NLP / DL -------------------------------------------------------------
    # Local sentence-embedding model (ONNX via fastembed) for semantic interest matching and
    # review sentiment. Downloaded once (~65 MB) into DATA_DIR/models. Falls back to lexical
    # matching when disabled or unavailable.
    semantic_enabled: bool = True
    semantic_model: str = "BAAI/bge-small-en-v1.5"
    data_dir: str = str(BACKEND_DIR / "data")
    geonames_url: str = "https://download.geonames.org/export/dump"
    photon_url: str = "https://photon.komoot.io/api/"

    # ---- AI -----------------------------------------------------------------
    anthropic_api_key: str = ""
    anthropic_model: str = ""   # model id from the provider's docs; required when AI_ENABLED=true
    ai_enabled: bool = False

    # ---- app ----------------------------------------------------------------
    database_url: str = DEFAULT_DATABASE_URL
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # optional regex for extra allowed origins, e.g. Vercel preview URLs: https://trip-aura-.*\.vercel\.app
    cors_origin_regex: str = ""
    log_level: str = "INFO"
    warmup_on_start: bool = True   # preload city index + AI model in the background at startup
    # "development" or "production". Production hides API docs unless DOCS_ENABLED=true.
    app_env: str = "development"
    # None = on in development, off in production
    docs_enabled: bool | None = None

    # ---- auth / security ----------------------------------------------------
    # Legacy account settings retained for database compatibility; account routes are not mounted.
    secret_key: str = ""
    session_days: int = Field(default=7, ge=1, le=90)       # absolute session lifetime
    cookie_secure: bool = True                               # false only for local plain-http development
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"  # "none" always sets Secure
    admin_emails: str = ""                                   # comma list; role re-evaluated at each sign-in
    # Legacy account settings retained for database compatibility; no email is sent.
    resend_api_key: str = ""
    email_from: str = "TripAura <onboarding@resend.dev>"
    # Read the client IP / scheme from X-Forwarded-For / X-Forwarded-Proto. Enable only behind a
    # proxy that overwrites these headers (Azure Container Apps ingress, Vercel rewrites).
    trust_proxy_headers: bool = False
    # How many proxies in front of the app append to X-Forwarded-For: 1 = Azure ingress only, 2 = Vercel rewrite + Azure.
    trusted_proxy_count: int = Field(default=1, ge=1, le=5)
    rate_limit_enabled: bool = True

    # Engine tuning (not secrets; overridable for experiments)
    max_candidate_places: int = Field(default=150, ge=10, le=500)
    max_food_candidates: int = Field(default=800, ge=10, le=3000)

    @field_validator("database_url", mode="before")
    @classmethod
    def _blank_db_means_default(cls, v):
        # `DATABASE_URL=` (empty) in an env file means "use the default SQLite file"
        return v if isinstance(v, str) and v.strip() else DEFAULT_DATABASE_URL

    @field_validator("docs_enabled", mode="before")
    @classmethod
    def _blank_docs_means_auto(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("app_env", "cookie_samesite", mode="before")
    @classmethod
    def _lower(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def docs_on(self) -> bool:
        return (not self.is_production) if self.docs_enabled is None else self.docs_enabled

    @property
    def signing_key(self) -> bytes:
        return (self.secret_key.strip() or _PROCESS_SECRET).encode()

    @property
    def cookie_secure_effective(self) -> bool:
        return self.cookie_secure or self.cookie_samesite == "none"

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def email_configured(self) -> bool:
        return bool(self.resend_api_key.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_origins(self) -> list[str]:
        """Explicit CORS origins. A wildcard is never allowed with credentialed requests."""
        return [o.rstrip("/") for o in self.cors_origin_list if o != "*"]

    def check_startup(self) -> None:
        """Raise on configuration that must not run; warn about weak development defaults."""
        if "*" in self.cors_origin_list:
            log.warning("CORS_ORIGINS contains '*', which is ignored: credentialed requests need explicit origins")

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
