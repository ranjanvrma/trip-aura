"""Provider factory: picks mock, open-data or Google implementations from DATA_MODE.

There is deliberately no automatic fallback between modes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import DataMode, RoutingEngine, Settings, get_settings
from app.providers.base import GeocodingProvider, PlacesProvider, RoutesProvider
from app.schemas.common import DataSource


@dataclass
class ProviderBundle:
    mode: DataMode
    source: DataSource
    places: PlacesProvider
    routes: RoutesProvider
    geocoding: GeocodingProvider
    extras: dict = field(default_factory=dict)   # open mode: {"cities": CityDataService, "enricher_factory": ...}


def _google_client(settings: Settings):
    from app.providers.google.client import GoogleClient

    return GoogleClient(settings)  # raises ProviderNotConfiguredError without a key


def build_providers(settings: Settings) -> ProviderBundle:
    if settings.data_mode == DataMode.LIVE:
        from app.providers.google.geocoding import GoogleGeocodingProvider
        from app.providers.google.places import GooglePlacesProvider
        from app.providers.google.routes import GoogleRoutesProvider

        client = _google_client(settings)
        return ProviderBundle(DataMode.LIVE, DataSource.GOOGLE, GooglePlacesProvider(client),
                              GoogleRoutesProvider(client), GoogleGeocodingProvider(client))

    if settings.data_mode == DataMode.OPEN:
        from app.nlp.registry import get_city_index
        from app.providers.heuristic_routes import HeuristicRoutesProvider
        from app.providers.open.city_store import CityDataService
        from app.providers.open.http import OpenHttp
        from app.providers.open.providers import OpenGeocodingProvider, OpenPlacesProvider, OsrmRoutesProvider

        http = OpenHttp(settings)
        cities = CityDataService(settings, http)
        heuristic = HeuristicRoutesProvider(cities.stations, DataSource.ESTIMATE)
        routes: RoutesProvider = heuristic
        if settings.routing_engine == RoutingEngine.OSRM:
            routes = OsrmRoutesProvider(http, settings.osrm_driving_url, settings.osrm_walking_url, heuristic)
        extras: dict = {"cities": cities}
        if settings.google_configured and settings.google_enrichment:
            from app.providers.google.places import GooglePlacesProvider
            from app.services.enrichment import GoogleEnricher

            google_places = GooglePlacesProvider(_google_client(settings))
            extras["enricher_factory"] = lambda: GoogleEnricher(google_places)
        # the offline GeoNames city index lets the open geocoder skip Nominatim for city names
        return ProviderBundle(DataMode.OPEN, DataSource.OPEN, OpenPlacesProvider(cities), routes,
                              OpenGeocodingProvider(http, get_city_index()), extras)

    from app.providers.mock.providers import MockGeocodingProvider, MockPlacesProvider, MockRoutesProvider

    return ProviderBundle(DataMode.MOCK, DataSource.MOCK, MockPlacesProvider(), MockRoutesProvider(),
                          MockGeocodingProvider())


@lru_cache
def _cached(mode: str, key_present: bool) -> ProviderBundle:
    return build_providers(get_settings())


def get_providers() -> ProviderBundle:
    s = get_settings()
    return _cached(s.data_mode.value, s.google_configured)

