from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import TripNotFoundError
from app.db.database import get_db
from app.db.models import Trip
from app.routers.deps import Auth, generation_limit, get_itinerary_service, require_auth
from app.schemas.itinerary import Itinerary
from app.schemas.trip import TripRequest
from app.services.idempotency import Idempotency, idempotency_key
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


def load_trip(db: Session, trip_id: int, auth: Auth, *, admin_ok: bool = False) -> Trip:
    """The trip if the caller owns it (or is an admin and `admin_ok`). Anything else is a 404, so
    other users' trip ids cannot be probed. Trips without an owner (saved before sign-in existed)
    are reachable by admins only."""
    trip = db.get(Trip, trip_id)
    if trip is None or not (trip.user_id == auth.user.id or (admin_ok and auth.is_admin)):
        raise TripNotFoundError(f"Trip {trip_id} not found")
    return trip


def to_itinerary(trip: Trip) -> Itinerary:
    it = Itinerary.model_validate(trip.itinerary_json)
    it.trip_id = trip.id
    return it


@router.post("", response_model=Itinerary, status_code=201)
def create_trip(req: TripRequest, db: Session = Depends(get_db), auth: Auth = Depends(require_auth),
                key: str = Depends(idempotency_key),
                svc: ItineraryService = Depends(get_itinerary_service)):
    def produce() -> Itinerary:
        generation_limit(auth)
        itinerary = svc.generate(req)
        trip = Trip(title=_title(req), destination=req.destination_city, num_days=req.num_days,
                    data_source=itinerary.data_source.value, request_json=req.model_dump(mode="json"),
                    itinerary_json=itinerary.model_dump(mode="json"), user_id=auth.user.id)
        db.add(trip)
        db.commit()
        itinerary.trip_id = trip.id
        log.info("Created trip %s (%s, %s) for user %s", trip.id, trip.title, trip.data_source, auth.user.id)
        return itinerary

    return Idempotency(db, auth.user.id, key, "POST /api/trips", req.model_dump(mode="json")).run(201, produce)


@router.post("/preview", response_model=Itinerary)
def preview_trip(req: TripRequest, auth: Auth = Depends(require_auth),
                 svc: ItineraryService = Depends(get_itinerary_service)) -> Itinerary:
    """Generate without saving."""
    generation_limit(auth)
    return svc.generate(req)


@router.get("", response_model=list[TripSummary])
def list_trips(all: bool = Query(False, description="Admins only: list every user's trips."),
               db: Session = Depends(get_db), auth: Auth = Depends(require_auth)) -> list[TripSummary]:
    q = select(Trip)
    if not (all and auth.is_admin):
        q = q.where(Trip.user_id == auth.user.id)
    rows = db.scalars(q.order_by(Trip.created_at.desc(), Trip.id.desc()).limit(50)).all()
    return [TripSummary(id=t.id, title=t.title, destination=t.destination, num_days=t.num_days,
                        data_source=t.data_source, created_at=t.created_at.isoformat()) for t in rows]


@router.get("/{trip_id}", response_model=Itinerary)
def get_trip(trip_id: int, db: Session = Depends(get_db), auth: Auth = Depends(require_auth)) -> Itinerary:
    return to_itinerary(load_trip(db, trip_id, auth, admin_ok=True))


@router.post("/{trip_id}/regenerate", response_model=Itinerary)
def regenerate_trip(trip_id: int, db: Session = Depends(get_db), auth: Auth = Depends(require_auth),
                    key: str = Depends(idempotency_key),
                    svc: ItineraryService = Depends(get_itinerary_service)):
    trip = load_trip(db, trip_id, auth)

    def produce() -> Itinerary:
        generation_limit(auth)
        itinerary = svc.generate(TripRequest.model_validate(trip.request_json))
        trip.itinerary_json = itinerary.model_dump(mode="json")
        trip.data_source = itinerary.data_source.value
        db.commit()
        itinerary.trip_id = trip.id
        return itinerary

    return Idempotency(db, auth.user.id, key, f"POST /api/trips/{trip_id}/regenerate", {}).run(200, produce)


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip_id: int, db: Session = Depends(get_db), auth: Auth = Depends(require_auth)) -> Response:
    db.delete(load_trip(db, trip_id, auth, admin_ok=True))
    db.commit()
    return Response(status_code=204)
