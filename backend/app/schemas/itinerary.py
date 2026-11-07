from __future__ import annotations

import datetime as dt
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.common import DataSource, LatLng, Money
from app.schemas.place import Place, SuitabilityScore
from app.schemas.trip import TransportMode, TripRequest


class TransportOption(BaseModel):
    mode: TransportMode
    distance_km: float
    duration_min: float
    cost: Money
    practical: bool
    score: float = Field(description="Practicality score 0..1 (higher is better).")
    note: str | None = None
    traffic_aware: bool = False
    source: DataSource
    polyline: list[LatLng] = Field(default_factory=list)


class TravelLeg(BaseModel):
    from_name: str
    to_name: str
    origin: LatLng
    destination: LatLng
    chosen: TransportOption
    alternatives: list[TransportOption] = Field(default_factory=list)
    recommendation_reason: str


class ItemType(str, Enum):
    START = "start"
    ACTIVITY = "activity"
    MEAL = "meal"
    REST = "rest"
    TRAVEL = "travel"
    END = "end"


class ItineraryItem(BaseModel):
    id: str
    type: ItemType
    period: str
    start: str
    end: str
    duration_min: int
    title: str
    place: Place | None = None
    suitability: SuitabilityScore | None = None
    meal_type: str | None = None
    cost: Money | None = None
    travel: TravelLeg | None = None
    notes: list[str] = Field(default_factory=list)


class CategoryTotals(BaseModel):
    food: float = 0
    transport: float = 0
    attractions: float = 0
    accommodation: float = 0

    def total(self) -> float:
        return round(self.food + self.transport + self.attractions + self.accommodation, 2)


class DayBudget(BaseModel):
    day_number: int
    totals: CategoryTotals
    total: float
    verified_amount: float
    estimated_amount: float


class DayPlan(BaseModel):
    day_number: int
    date: dt.date
    weekday: str
    items: list[ItineraryItem]
    budget: DayBudget
    warnings: list[str] = Field(default_factory=list)


class DishSuggestion(BaseModel):
    name: str
    status: str = Field(description='"popular" (backed by review evidence) or "suggestion" (no evidence)')
    evidence: list[str] = Field(default_factory=list)
    evidence_source: DataSource | None = None
    mention_count: int = 0


class FoodRecommendation(BaseModel):
    place: Place
    suitability: SuitabilityScore
    meal_types: list[str]
    dishes: list[DishSuggestion]
    diet_match: list[str]


class BudgetSuggestion(BaseModel):
    kind: str   # "free_attraction" | "cheaper_transport" | "cheaper_food" | "drop_activity"
    message: str
    estimated_saving: float
    item_id: str | None = None
    alternative_place_id: str | None = None


class BudgetSummary(BaseModel):
    currency: str
    total_budget: float
    planned_total: float
    remaining: float
    over_budget: bool
    by_category: CategoryTotals
    per_day: list[DayBudget]
    verified_total: float
    estimated_total: float
    suggestions: list[BudgetSuggestion] = Field(default_factory=list)
    applied_optimizations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class UnscheduledPlace(BaseModel):
    place: Place
    reason: str


class Itinerary(BaseModel):
    trip_id: int | None = None
    data_source: DataSource
    generated_at: dt.datetime
    request: TripRequest
    accommodation: Place
    days: list[DayPlan]
    food_recommendations: list[FoodRecommendation]
    popular_dishes: list[DishSuggestion] = Field(default_factory=list)
    budget: BudgetSummary
    unscheduled: list[UnscheduledPlace] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disclaimers: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    ai_status: str = "disabled"
