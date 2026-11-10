from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.routers.deps import Auth, get_itinerary_service, require_auth
from app.routers.trips import _load, _to_itinerary
from app.schemas.location import LiveProgressRequest, LiveProgressResponse
from app.services import location_service
from app.services.itinerary_service import ItineraryService

router = APIRouter(prefix="/api/trips", tags=["location"])


@router.post("/{trip_id}/live", response_model=LiveProgressResponse)
def live_progress(trip_id: int, body: LiveProgressRequest, db: Session = Depends(get_db),
                  auth: Auth = Depends(require_auth),
                  svc: ItineraryService = Depends(get_itinerary_service)) -> LiveProgressResponse:
    """Distance to the next stop plus fresh (traffic-aware in live mode) transport estimates.

    Called by the browser only while the user has live location enabled. Coordinates are not stored.
    """
    itinerary = _to_itinerary(_load(db, trip_id, auth))
    city = svc.city(itinerary.request.destination_city)
    transport = svc.transport_for(itinerary.request, city)
    return location_service.progress(itinerary, body, transport)
