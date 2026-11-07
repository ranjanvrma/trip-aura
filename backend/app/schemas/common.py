from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DataSource(str, Enum):
    """Where a value came from. Shown to the user next to every number."""

    GOOGLE = "google"        # returned by a Google Maps Platform API call
    MOCK = "mock"            # bundled demo dataset - not real-world data
    ESTIMATE = "estimate"    # computed by our heuristics (e.g. fare tables)
    USER = "user"            # supplied by the user
    OPEN = "open_data"       # itinerary built from open datasets (see attributions)
    OSM = "osm"              # OpenStreetMap contributors (ODbL)
    OVERTURE = "overture"    # Overture Maps Foundation places (CDLA-Permissive-2.0 / Apache-2.0)
    WIKIDATA = "wikidata"    # Wikidata (CC0)
    WIKIVOYAGE = "wikivoyage"  # Wikivoyage travel guide (CC BY-SA 4.0)


class LatLng(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

    def as_tuple(self) -> tuple[float, float]:
        return (self.lat, self.lng)


class Money(BaseModel):
    amount: float = Field(ge=0)
    currency: str
    verified: bool = False   # True only when a provider returned an actual price
    source: DataSource = DataSource.ESTIMATE
    note: str | None = None

    @classmethod
    def estimate(
        cls,
        amount: float,
        currency: str,
        note: str | None = None,
        source: DataSource = DataSource.ESTIMATE,
    ) -> "Money":
        return cls(amount=round(max(amount, 0.0), 2), currency=currency, verified=False, source=source, note=note)
