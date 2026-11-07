from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.engines.transport import choose
from app.routers.deps import get_itinerary_service
from app.schemas.common import LatLng
from app.schemas.itinerary import TransportOption
from app.schemas.trip import TransportMode, TripRequest
from app.services.itinerary_service import ItineraryService

router = APIRouter(prefix="/api/routes", tags=["routes"])


class RouteRequest(BaseModel):
    city: str
    origin: LatLng
    destination: LatLng
    modes: list[TransportMode] = Field(default_factory=list)
    currency: str = "INR"
    travelers: int = Field(default=1, ge=1, le=20)
    departure: dt.datetime | None = None


class RouteResponse(BaseModel):
    options: list[TransportOption]
    recommended: TransportOption
    reason: str


@router.post("/compare", response_model=RouteResponse)
def compare(body: RouteRequest, svc: ItineraryService = Depends(get_itinerary_service)) -> RouteResponse:
    """Compare transport modes between two points (used by the map for ad-hoc routes)."""
    req = TripRequest.model_validate({
        "accommodation": {"name_or_address": "route-compare", "location": body.origin.model_dump()},
        "destination_city": body.city, "num_days": 1, "budget": 1_000_000, "currency": body.currency,
        "travelers": body.travelers, "transport_modes": [m.value for m in body.modes],
    })
    city = svc.city(body.city)
    engine = svc.transport_for(req, city)
    options = engine.options(body.origin, body.destination, body.departure, fresh=True)
    best, reason = choose(options, engine.preferred)
    return RouteResponse(options=options, recommended=best, reason=reason)
