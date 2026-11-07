"""Provider factory: picks mock or Google implementations from DATA_MODE.

There is deliberately no automatic fallback between the two.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import DataMode, Settings, get_settings
from app.providers.base import GeocodingProvider, PlacesProvider, RoutesProvider
from app.schemas.common import DataSource


@dataclass
class ProviderBundle:
    mode: DataMode
    source: DataSource
    places: PlacesProvider
    routes: RoutesProvider
    geocoding: GeocodingProvider


def build_providers(settings: Settings) -> ProviderBundle:
    if settings.data_mode == DataMode.LIVE:
        from app.providers.google.client import GoogleClient
        from app.providers.google.geocoding import GoogleGeocodingProvider
        from app.providers.google.places import GooglePlacesProvider
        from app.providers.google.routes import GoogleRoutesProvider

        client = GoogleClient(settings)  # raises ProviderNotConfiguredError without a key
        return ProviderBundle(DataMode.LIVE, DataSource.GOOGLE, GooglePlacesProvider(client),
                              GoogleRoutesProvider(client), GoogleGeocodingProvider(client))

    from app.providers.mock.providers import MockGeocodingProvider, MockPlacesProvider, MockRoutesProvider

    return ProviderBundle(DataMode.MOCK, DataSource.MOCK, MockPlacesProvider(), MockRoutesProvider(),
                          MockGeocodingProvider())


@lru_cache
def _cached(mode: str, key_present: bool) -> ProviderBundle:
    return build_providers(get_settings())


def get_providers() -> ProviderBundle:
    s = get_settings()
    return _cached(s.data_mode.value, s.google_configured)
