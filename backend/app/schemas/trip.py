from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.currencies import SUPPORTED_CURRENCIES
from app.schemas.common import LatLng


class Pace(str, Enum):
    RELAXED = "relaxed"
    MODERATE = "moderate"
    PACKED = "packed"


class TransportMode(str, Enum):
    WALKING = "walking"
    METRO = "metro"
    BUS = "bus"
    TRAIN = "train"
    CAB = "cab"
    AUTO = "auto"
    PERSONAL_VEHICLE = "personal_vehicle"


class AccommodationType(str, Enum):
    HOTEL = "hotel"
    AIRBNB = "airbnb"
    HOSTEL = "hostel"
    DORM = "dorm"
    PRIVATE_PROPERTY = "private_property"
    ADDRESS = "address"
    OTHER = "other"


class AccommodationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: AccommodationType = AccommodationType.HOTEL
    name_or_address: str = Field(min_length=2, max_length=300)
    location: LatLng | None = Field(default=None, description="Optional exact coordinates; skips geocoding.")


PRESET_INTERESTS = [
    "museums", "monuments", "cultural_centres", "nature", "parks", "shopping",
    "architecture", "photography", "adventure", "history", "religious_sites",
    "art", "markets", "wildlife", "nightlife",
]
PRESET_DIETS = ["vegetarian", "vegan", "non_vegetarian", "jain", "eggetarian"]
PRESET_FOOD_CATEGORIES = ["cafes", "street_food", "local_cuisine", "budget_restaurants", "fine_dining"]


ShortText = Annotated[str, Field(max_length=100)]


def _norm_list(values: list[str]) -> list[str]:
    out: list[str] = []
    for v in values:
        v = v.strip().lower().replace(" ", "_").replace("-", "_")
        if v and v not in out:
            out.append(v[:60])
    return out


class TripRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accommodation: AccommodationInput
    destination_city: str = Field(min_length=2, max_length=120)
    start_date: dt.date | None = None
    num_days: int = Field(ge=1, le=14)
    travelers: int = Field(default=1, ge=1, le=20)
    budget: float = Field(gt=0, le=1e10, allow_inf_nan=False, description="Total trip budget in `currency`.")
    currency: str = Field(default="INR", max_length=10)
    accommodation_cost_total: float = Field(default=0, ge=0, le=1e10, allow_inf_nan=False, description="Counted against the budget if > 0.")
    interests: list[ShortText] = Field(default_factory=list, max_length=20)
    food_preferences: list[ShortText] = Field(default_factory=list, max_length=10)
    food_categories: list[ShortText] = Field(default_factory=list, max_length=10)
    transport_modes: list[TransportMode] = Field(default_factory=list, max_length=len(TransportMode))
    pace: Pace = Pace.MODERATE
    return_to_accommodation: bool = True
    fit_to_budget: bool = Field(default=False, description="Automatically swap to cheaper options when over budget.")

    @field_validator("interests", "food_preferences", "food_categories")
    @classmethod
    def _normalise(cls, v: list[str]) -> list[str]:
        return _norm_list(v)

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {', '.join(SUPPORTED_CURRENCIES)}")
        return v

    @model_validator(mode="after")
    def _defaults(self) -> "TripRequest":
        if not self.transport_modes:
            self.transport_modes = [TransportMode.WALKING, TransportMode.AUTO, TransportMode.CAB, TransportMode.BUS]
        if self.accommodation_cost_total >= self.budget:
            raise ValueError("accommodation_cost_total must be lower than the total budget")
        return self

    @property
    def effective_start_date(self) -> dt.date:
        return self.start_date or dt.date.today()
