from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import LatLng
from app.schemas.itinerary import TransportOption
from app.schemas.trip import TransportMode


class LiveProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current: LatLng
    accuracy_m: float | None = Field(default=None, ge=0, le=1_000_000)
    day_number: int = Field(ge=1, le=14)
    next_item_id: str | None = Field(default=None, max_length=100,
                                     description="Item the user is heading to; auto-detected if omitted.")
    planned_mode: TransportMode | None = None
    previous_duration_min: float | None = Field(
        default=None, ge=0, le=24 * 60, description="Last estimate shown to the user, used to detect traffic changes."
    )
    client_time: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$",
                                    description="Local 'HH:MM' on the device; used to pick the next stop.")


class TransportAlert(BaseModel):
    kind: str   # "better_alternative" | "traffic_change" | "arrived" | "low_accuracy"
    message: str
    suggested_mode: TransportMode | None = None


class LiveProgressResponse(BaseModel):
    next_item_id: str | None
    next_place_name: str | None
    next_location: LatLng | None
    straight_line_km: float | None
    options: list[TransportOption]
    recommended: TransportOption | None
    alerts: list[TransportAlert]
    checked_at: str
    data_source: str
