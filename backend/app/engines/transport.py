"""Transport recommendation engine.

For a leg it gathers candidate modes (user preferences + walking for short hops
+ one fallback when nothing preferred is practical), asks the routes service
for each, prices them, and picks the most practical by time, cost and
preference.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from app.core.errors import TripAuraError
from app.core.geo import haversine_km
from app.engines.costs import CostModel
from app.engines.fares import heuristic_duration_min
from app.engines.pace import PaceProfile
from app.providers.base import CityContext, RouteResult
from app.schemas.common import DataSource, LatLng, Money
from app.schemas.itinerary import TransportOption, TravelLeg
from app.schemas.trip import TransportMode, TripRequest
from app.services.routes_service import RoutesService

log = logging.getLogger(__name__)
LABEL = {
    TransportMode.WALKING: "Walk", TransportMode.METRO: "Metro", TransportMode.BUS: "Bus",
    TransportMode.TRAIN: "Train", TransportMode.CAB: "Cab", TransportMode.AUTO: "Auto-rickshaw",
    TransportMode.PERSONAL_VEHICLE: "Own vehicle",
}
FALLBACK_ORDER = [TransportMode.AUTO, TransportMode.CAB, TransportMode.BUS]


@dataclass
class TransportWeights:
    time: float = 0.45
    cost: float = 0.35
    preference: float = 0.20


def score_options(options: list[TransportOption], preferred: set[TransportMode], weights: TransportWeights,
                  leg_allowance: float | None = None) -> None:
    """Fill in TransportOption.score in place (0..1).

    Cost is judged against `leg_allowance` (what the budget comfortably allows per leg),
    so a generous budget does not force long walks just because walking is free.
    """
    practical = [o for o in options if o.practical] or options
    fastest = min(o.duration_min for o in practical) if practical else 1
    priciest = max(o.cost.amount for o in practical) if practical else 0
    ref = leg_allowance if leg_allowance and leg_allowance > 0 else priciest
    for o in options:
        t = max(fastest, 1) / max(o.duration_min, 1)
        c = 1.0 if ref <= 0 else max(0.0, 1 - o.cost.amount / ref)
        p = 1.0 if o.mode in preferred else 0.4
        s = weights.time * t + weights.cost * c + weights.preference * p
        if o.mode == TransportMode.WALKING and o.practical and o.distance_km <= 1.0:
            s += 0.15  # short walks: no waiting, free
        o.score = round(min(1.0, s) if o.practical else s * 0.3, 3)


def choose(options: list[TransportOption], preferred: set[TransportMode]) -> tuple[TransportOption, str]:
    if not options:
        raise TripAuraError("No transport option could be computed for this leg")
    pref_practical = [o for o in options if o.practical and o.mode in preferred]
    pool = pref_practical or [o for o in options if o.practical] or options
    best = max(pool, key=lambda o: o.score)
    cost = "free" if best.cost.amount == 0 else f"~{best.cost.amount:,.0f} {best.cost.currency}"
    if pref_practical:
        others = [o for o in pref_practical if o is not best]
        why = "best balance of time and cost" if others else "the only practical option among your preferences"
        reason = f"{LABEL[best.mode]}: {why} ({best.duration_min:.0f} min, {cost})."
    elif best.practical:
        reason = (f"None of your preferred modes is practical here; {LABEL[best.mode]} is suggested "
                  f"({best.duration_min:.0f} min, {cost}).")
    else:
        reason = f"No practical option found; {LABEL[best.mode]} is the least bad ({best.duration_min:.0f} min)."
    return best, reason


class TransportEngine:
    def __init__(self, routes: RoutesService, city: CityContext, req: TripRequest, pace: PaceProfile,
                 weights: TransportWeights | None = None, costs: CostModel | None = None):
        self.routes = routes
        self.city = city
        self.req = req
        self.pace = pace
        self.weights = weights or TransportWeights()
        self.preferred = set(req.transport_modes)
        self.costs = costs or CostModel.build("IN" if req.currency == "INR" else "US", req.currency)
        # ~25% of the daily spend for transport, spread over ~6 legs a day
        daily = (req.budget - req.accommodation_cost_total) / req.num_days
        self.leg_allowance = daily * 0.25 / 6

    # ---- planning-time estimate (no provider calls) ----------------------------
    def quick_minutes(self, a: LatLng, b: LatLng) -> float:
        km = haversine_km(a.lat, a.lng, b.lat, b.lng)
        best = None
        for mode in self.preferred | {TransportMode.WALKING}:
            if mode == TransportMode.WALKING and km > self.pace.max_walk_km:
                continue
            if mode == TransportMode.TRAIN and km < 8:
                continue
            _, minutes = heuristic_duration_min(mode, km, 1.15)
            best = minutes if best is None else min(best, minutes)
        if best is None:  # only walking preferred and too far: assume a fallback auto/cab
            _, best = heuristic_duration_min(TransportMode.AUTO, km, 1.15)
        return best

    # ---- provider-backed options ----------------------------------------------
    def _candidate_modes(self, km: float) -> list[TransportMode]:
        modes = list(self.req.transport_modes)
        if TransportMode.WALKING not in modes and km <= 1.2:
            modes.insert(0, TransportMode.WALKING)
        return modes

    def _to_option(self, r: RouteResult, travelers: int) -> TransportOption:
        if not r.available:
            return TransportOption(mode=r.mode, distance_km=round(r.distance_km, 2), duration_min=0,
                                   cost=Money.estimate(0, self.req.currency, note="Not available on this route"),
                                   practical=False, score=0.0, note=r.note or "Not available on this route",
                                   traffic_aware=False, source=r.source)
        if r.fare is not None:
            fare = self.costs.to_trip_currency(r.fare)
            cost = fare.model_copy(update={"amount": round(fare.amount * travelers, 2)})
        else:
            cost = self.costs.fare(r.mode, r.distance_km, travelers)
        practical = r.available
        note = r.note
        if r.mode == TransportMode.WALKING and r.distance_km > self.pace.max_walk_km:
            practical = False
            note = f"{r.distance_km:.1f} km is a long walk for a {self.req.pace.value} pace"
        if r.available and r.duration_min > 150:
            practical = False
            note = "Journey longer than 2.5 hours"
        return TransportOption(
            mode=r.mode, distance_km=round(r.distance_km, 2), duration_min=round(r.duration_min, 1), cost=cost,
            practical=practical, score=0.0, note=note, traffic_aware=r.traffic_aware, source=r.source,
            polyline=r.polyline,
        )

    def options(self, origin: LatLng, dest: LatLng, departure: dt.datetime | None, *, fresh: bool = False,
                include_fallback: bool = True) -> list[TransportOption]:
        km = haversine_km(origin.lat, origin.lng, dest.lat, dest.lng)
        modes = self._candidate_modes(km)
        out: list[TransportOption] = []
        for mode in modes:
            r = self.routes.route(origin, dest, mode, departure, self.city, fresh=fresh)
            out.append(self._to_option(r, self.req.travelers))
        if include_fallback and not any(o.practical for o in out):
            for mode in FALLBACK_ORDER:
                if mode not in modes:
                    r = self.routes.route(origin, dest, mode, departure, self.city, fresh=fresh)
                    opt = self._to_option(r, self.req.travelers)
                    opt.note = (opt.note + "; " if opt.note else "") + "not in your preferences"
                    out.append(opt)
                    if opt.practical:
                        break
        score_options(out, self.preferred, self.weights, self.leg_allowance)
        return out

    def build_leg(self, from_name: str, to_name: str, origin: LatLng, dest: LatLng,
                  departure: dt.datetime | None) -> TravelLeg:
        opts = self.options(origin, dest, departure)
        chosen, reason = choose(opts, self.preferred)
        alts = sorted([o for o in opts if o is not chosen and o.distance_km > 0], key=lambda o: -o.score)
        # keep the polyline only on the chosen option to keep payloads small
        for a in alts:
            a.polyline = []
        return TravelLeg(from_name=from_name, to_name=to_name, origin=origin, destination=dest,
                         chosen=chosen, alternatives=alts, recommendation_reason=reason)


def zero_leg(name: str, at: LatLng, currency: str, source: DataSource) -> TravelLeg:
    opt = TransportOption(mode=TransportMode.WALKING, distance_km=0, duration_min=0,
                          cost=Money.estimate(0, currency), practical=True, score=1, source=source)
    return TravelLeg(from_name=name, to_name=name, origin=at, destination=at, chosen=opt,
                     recommendation_reason="Same location")
