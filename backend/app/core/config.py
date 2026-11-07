"""Application settings loaded from environment variables (and an optional .env file)."""
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class DataMode(str, Enum):
    MOCK = "mock"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    data_mode: DataMode = DataMode.MOCK

    google_maps_api_key: str = ""
    google_http_timeout_seconds: float = 10.0

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    ai_enabled: bool = False

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'tripaura.db').as_posix()}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"

    # Engine tuning (not secrets; overridable for experiments)
    max_candidate_places: int = Field(default=60, ge=10, le=200)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def google_configured(self) -> bool:
        return bool(self.google_maps_api_key.strip())

    @property
    def ai_available(self) -> bool:
        return self.ai_enabled and bool(self.anthropic_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
