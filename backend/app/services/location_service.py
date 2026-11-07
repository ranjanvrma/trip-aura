"""Live-location service: distance to the next stop, refreshed estimates and alerts.

The browser sends coordinates only while the user has live location switched
on; nothing is stored server-side.
"""
from __future__ import annotations

import datetime as dt

from app.core.errors import NotFoundError
from app.core.geo import haversine_km
from app.core.timeutil import hm_to_min
from app.engines.transport import LABEL, TransportEngine, choose
from app.schemas.itinerary import Itinerary, ItemType, ItineraryItem
from app.schemas.location import LiveProgressRequest, LiveProgressResponse, TransportAlert

BETTER_RATIO = 0.75       # alternative must be at least 25% faster ...
MIN_SAVING_MIN = 5        # ... and save at least 5 minutes
TRAFFIC_CHANGE = 0.20     # 20% change in duration triggers a traffic alert
ARRIVED_KM = 0.08


def _next_item(items: list[ItineraryItem], req: LiveProgressRequest) -> ItineraryItem | None:
    stops = [i for i in items if i.type in (ItemType.ACTIVITY, ItemType.MEAL, ItemType.END) and i.place is not None]
    if req.next_item_id:
        for i in stops:
            if i.id == req.next_item_id:
                return i
        raise NotFoundError(f"Item {req.next_item_id} not found on day {req.day_number}")
    if req.client_time:
        now = hm_to_min(req.client_time)
        upcoming = [i for i in stops if hm_to_min(i.end) > now]
        return upcoming[0] if upcoming else None
    return stops[0] if stops else None


def _planned_mode(items: list[ItineraryItem], target: ItineraryItem):
    idx = items.index(target)
    for i in reversed(items[:idx]):
        if i.type == ItemType.TRAVEL and i.travel:
            return i.travel.chosen.mode
        if i.type in (ItemType.ACTIVITY, ItemType.MEAL):
            return None
    return None


def progress(it: Itinerary, req: LiveProgressRequest, transport: TransportEngine) -> LiveProgressResponse:
    day = next((d for d in it.days if d.day_number == req.day_number), None)
    if day is None:
        raise NotFoundError(f"Day {req.day_number} not in this itinerary")
    target = _next_item(day.items, req)
    now = dt.datetime.now()
    alerts: list[TransportAlert] = []
    if req.accuracy_m and req.accuracy_m > 200:
        alerts.append(TransportAlert(kind="low_accuracy",
                                     message=f"Location accuracy is low (~{req.accuracy_m:.0f} m); estimates may be off."))
    if target is None or target.place is None:
        return LiveProgressResponse(next_item_id=None, next_place_name=None, next_location=None, straight_line_km=None,
                                    options=[], recommended=None, alerts=alerts, checked_at=now.isoformat(timespec="seconds"),
                                    data_source=it.data_source.value)

    dest = target.place.location
    km = haversine_km(req.current.lat, req.current.lng, dest.lat, dest.lng)
    if km <= ARRIVED_KM:
        alerts.append(TransportAlert(kind="arrived", message=f"You have arrived at {target.place.name}."))
        return LiveProgressResponse(next_item_id=target.id, next_place_name=target.place.name, next_location=dest,
                                    straight_line_km=round(km, 3), options=[], recommended=None, alerts=alerts,
                                    checked_at=now.isoformat(timespec="seconds"), data_source=it.data_source.value)

    options = transport.options(req.current, dest, now, fresh=True)
    recommended, _ = choose(options, transport.preferred)
    planned_mode = req.planned_mode or _planned_mode(day.items, target)
    planned = next((o for o in options if o.mode == planned_mode), None) if planned_mode else None

    if planned is not None and recommended.mode != planned.mode:
        faster = recommended.duration_min <= planned.duration_min * BETTER_RATIO \
            and planned.duration_min - recommended.duration_min >= MIN_SAVING_MIN
        if not planned.practical or faster:
            why = "is no longer practical" if not planned.practical else \
                f"now takes {planned.duration_min:.0f} min vs {recommended.duration_min:.0f} min"
            alerts.append(TransportAlert(
                kind="better_alternative", suggested_mode=recommended.mode,
                message=f"{LABEL[planned.mode]} {why}. Consider {LABEL[recommended.mode]} to {target.place.name}.",
            ))
    ref = planned or recommended
    if req.previous_duration_min and req.previous_duration_min > 0:
        change = (ref.duration_min - req.previous_duration_min) / req.previous_duration_min
        if abs(change) >= TRAFFIC_CHANGE:
            direction = "longer" if change > 0 else "shorter"
            alerts.append(TransportAlert(
                kind="traffic_change", suggested_mode=recommended.mode if recommended is not ref else None,
                message=(f"Travel time to {target.place.name} is now {ref.duration_min:.0f} min "
                         f"({abs(change) * 100:.0f}% {direction} than before)."),
            ))
    return LiveProgressResponse(
        next_item_id=target.id, next_place_name=target.place.name, next_location=dest,
        straight_line_km=round(km, 3), options=options, recommended=recommended, alerts=alerts,
        checked_at=now.isoformat(timespec="seconds"), data_source=it.data_source.value,
    )
