from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.database import get_db
from app.db.models import Trip
from app.routers.deps import get_itinerary_service
from app.schemas.itinerary import Itinerary
from app.schemas.trip import TripRequest
from app.services.itinerary_service import ItineraryService

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trips", tags=["trips"])


class TripSummary(BaseModel):
    id: int
    title: str
    destination: str
    num_days: int
    data_source: str
    created_at: str


def _title(req: TripRequest) -> str:
    return f"{req.num_days} day{'s' if req.num_days > 1 else ''} in {req.destination_city.title()}"


def _load(db: Session, trip_id: int) -> Trip:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise NotFoundError(f"Trip {trip_id} not found")
    return trip


def _to_itinerary(trip: Trip) -> Itinerary:
    it = Itinerary.model_validate(trip.itinerary_json)
    it.trip_id = trip.id
    return it


@router.post("", response_model=Itinerary, status_code=201)
def create_trip(req: TripRequest, db: Session = Depends(get_db),
                svc: ItineraryService = Depends(get_itinerary_service)) -> Itinerary:
    itinerary = svc.generate(req)
    trip = Trip(title=_title(req), destination=req.destination_city, num_days=req.num_days,
                data_source=itinerary.data_source.value, request_json=req.model_dump(mode="json"),
                itinerary_json=itinerary.model_dump(mode="json"))
    db.add(trip)
    db.commit()
    itinerary.trip_id = trip.id
    log.info("Created trip %s (%s, %s)", trip.id, trip.title, trip.data_source)
    return itinerary


@router.post("/preview", response_model=Itinerary)
def preview_trip(req: TripRequest, svc: ItineraryService = Depends(get_itinerary_service)) -> Itinerary:
    """Generate without saving."""
    return svc.generate(req)


@router.get("", response_model=list[TripSummary])
def list_trips(db: Session = Depends(get_db)) -> list[TripSummary]:
    rows = db.scalars(select(Trip).order_by(Trip.created_at.desc()).limit(50)).all()
    return [TripSummary(id=t.id, title=t.title, destination=t.destination, num_days=t.num_days,
                        data_source=t.data_source, created_at=t.created_at.isoformat()) for t in rows]


@router.get("/{trip_id}", response_model=Itinerary)
def get_trip(trip_id: int, db: Session = Depends(get_db)) -> Itinerary:
    return _to_itinerary(_load(db, trip_id))


@router.post("/{trip_id}/regenerate", response_model=Itinerary)
def regenerate_trip(trip_id: int, db: Session = Depends(get_db),
                    svc: ItineraryService = Depends(get_itinerary_service)) -> Itinerary:
    trip = _load(db, trip_id)
    req = TripRequest.model_validate(trip.request_json)
    itinerary = svc.generate(req)
    trip.itinerary_json = itinerary.model_dump(mode="json")
    trip.data_source = itinerary.data_source.value
    db.commit()
    itinerary.trip_id = trip.id
    return itinerary


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip_id: int, db: Session = Depends(get_db)) -> Response:
    db.delete(_load(db, trip_id))
    db.commit()
    return Response(status_code=204)
