"""Trip generation. Trips are not stored on the server: the browser keeps saved trips (see frontend lib/localTrips.ts)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.routers.deps import get_itinerary_service
from app.schemas.itinerary import Itinerary
from app.schemas.trip import TripRequest
from app.services.itinerary_service import ItineraryService

router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.post("/preview", response_model=Itinerary)
def preview_trip(req: TripRequest, svc: ItineraryService = Depends(get_itinerary_service)) -> Itinerary:
    """Generate an itinerary without saving it. Rate limited per IP ("generate" class in request_guard)."""
    return svc.generate(req)
