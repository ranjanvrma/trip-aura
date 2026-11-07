from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import DataSource, LatLng, Money


class PlaceKind(str, Enum):
    ATTRACTION = "attraction"
    PARK = "park"
    RESTAURANT = "restaurant"
    CAFE = "cafe"
    ACCOMMODATION = "accommodation"
    OTHER = "other"


class TimeRange(BaseModel):
    open: str   # "HH:MM"
    close: str  # "HH:MM"; "24:00" allowed


class OpeningHours(BaseModel):
    """weekly[0] = Monday ... weekly[6] = Sunday. A missing/empty day means closed.

    known=False means the provider did not report hours; the scheduler then
    assumes typical hours and adds a warning instead of pretending to know.
    """

    known: bool = True
    weekly: dict[int, list[TimeRange]] = Field(default_factory=dict)
    source: DataSource = DataSource.MOCK


class ExternalRating(BaseModel):
    """A third-party rating. NEVER merged with the suitability score.

    provider="google" + verified=True  -> fetched from the Google Places API.
    provider="mock"   + verified=False -> demo dataset value, NOT a Google rating.
    """

    provider: DataSource
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    verified: bool = False
    label: str


class SuitabilityScore(BaseModel):
    """Our own 0-5 personalised score. Independent of any external rating."""

    score: float = Field(ge=0, le=5)
    components: dict[str, float]   # each 0..1
    weights: dict[str, float]
    reasons: list[str]
    discovery: bool = False        # recommended although outside the user's interests


class Review(BaseModel):
    text: str
    rating: float | None = None
    source: DataSource


class DietInfo(BaseModel):
    vegetarian_only: bool = False
    vegetarian_options: bool = False
    vegan_options: bool = False
    jain_options: bool = False
    egg_options: bool = False
    non_veg: bool = False
    known: bool = True   # False when the provider gave no dietary information
    source: DataSource = DataSource.MOCK


class Place(BaseModel):
    id: str
    name: str
    kind: PlaceKind
    categories: list[str] = Field(default_factory=list)   # normalised interest tags
    location: LatLng
    address: str | None = None
    description: str | None = None
    external_rating: ExternalRating | None = None
    price_level: int | None = Field(default=None, ge=0, le=4)
    price_level_estimated: bool = False   # True when inferred from the type of place, not reported
    entry_fee: Money | None = None
    avg_cost_per_person: Money | None = None
    typical_visit_minutes: int = 60
    opening_hours: OpeningHours | None = None
    is_famous: bool = False
    best_time: list[str] = Field(default_factory=list)   # "morning" | "afternoon" | "evening"
    diet: DietInfo | None = None
    food_categories: list[str] = Field(default_factory=list)
    cuisines: list[str] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)
    google_maps_uri: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)   # e.g. {"osm": "n123", "wikidata": "Q1", "google": "..."}
    prominence: int | None = None   # Wikipedia language editions covering the place (Wikidata sitelinks)
    source: DataSource
