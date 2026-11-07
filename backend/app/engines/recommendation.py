"""Personalised suitability scoring (0-5).

The score is built ONLY from the user's own constraints:
interest match, budget compatibility, distance, transport preferences,
time availability and travel pace. External ratings (Google or mock) are
deliberately NOT an input, so the two numbers stay independent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.geo import haversine_km
from app.engines.pace import PaceProfile, profile_for
from app.schemas.common import LatLng
from app.schemas.place import Place, PlaceKind, SuitabilityScore
from app.schemas.trip import TransportMode, TripRequest

WEIGHTS: dict[str, float] = {
    "interest": 0.30,
    "budget": 0.20,
    "distance": 0.20,
    "transport": 0.10,
    "time": 0.10,
    "pace": 0.10,
}
MOTORISED = {TransportMode.AUTO, TransportMode.CAB, TransportMode.PERSONAL_VEHICLE}
PUBLIC = {TransportMode.METRO, TransportMode.BUS, TransportMode.TRAIN}

# Share of the per-person daily budget planned for each category.
ATTRACTION_SHARE = 0.30
FOOD_SHARE = 0.45


@dataclass
class ScoringContext:
    req: TripRequest
    origin: LatLng
    weekdays: list[int]                      # weekday index (0=Mon) of each trip day
    pace: PaceProfile = field(init=False)
    daily_budget_pp: float = field(init=False)

    def __post_init__(self) -> None:
        self.pace = profile_for(self.req.pace)
        spendable = self.req.budget - self.req.accommodation_cost_total
        self.daily_budget_pp = spendable / self.req.num_days / self.req.travelers

    @property
    def attraction_allowance(self) -> float:
        return self.daily_budget_pp * ATTRACTION_SHARE / max(1, self.pace.max_activities - 1)

    @property
    def meal_allowance(self) -> float:
        return self.daily_budget_pp * FOOD_SHARE / 3


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def affordability(cost: float | None, allowance: float) -> float:
    """1.0 when cost <= allowance, falling linearly to 0 at 3x allowance. Unknown cost -> 0.6."""
    if cost is None:
        return 0.6
    if cost <= 0:
        return 1.0
    if allowance <= 0:
        return 0.0
    if cost <= allowance:
        return 1.0
    return clamp(1 - (cost - allowance) / (2 * allowance))


def distance_component(km: float, scale_km: float) -> float:
    return 1 / (1 + (km / scale_km) ** 2)


def transport_component(km: float, modes: list[TransportMode], max_walk_km: float) -> float:
    mset = set(modes)
    best = 0.0
    if TransportMode.WALKING in mset:
        best = max(best, 1.0 if km <= max_walk_km else clamp(1 - (km - max_walk_km) / (2 * max_walk_km)))
    if mset & MOTORISED:
        best = max(best, 1.0 if km <= 15 else clamp(1 - (km - 15) / 25))
    if mset & PUBLIC:
        best = max(best, 0.85 if km <= 12 else clamp(0.85 - (km - 12) / 20))
    return best


def open_day_ratio(place: Place, weekdays: list[int]) -> float:
    oh = place.opening_hours
    if oh is None or not oh.known:
        return 0.8  # unknown hours: not penalised to zero, but flagged by the scheduler
    open_days = sum(1 for d in weekdays if oh.weekly.get(d))
    return open_days / len(weekdays) if weekdays else 0.0


def interest_component(place: Place, interests: list[str]) -> tuple[float, list[str]]:
    if not interests:
        return 0.6, []
    text = f"{place.name} {place.description or ''}".lower()
    matched = [i for i in interests if i in place.categories or (len(i) > 3 and i.replace("_", " ") in text)]
    if not matched:
        return 0.0, []
    return clamp(0.65 + 0.15 * (len(matched) - 1)), matched


def pace_component(place: Place, pace: PaceProfile, req: TripRequest) -> float:
    mins = place.typical_visit_minutes
    if mins <= pace.max_visit_min * 0.6:
        s = 1.0
    elif mins <= pace.max_visit_min:
        s = 0.8
    else:
        s = clamp(0.8 - (mins - pace.max_visit_min) / pace.max_visit_min)
    if req.pace.value == "relaxed" and place.kind == PlaceKind.PARK:
        s = clamp(s + 0.15)
    return s


def time_component(place: Place, ctx: ScoringContext) -> float:
    usable = ctx.pace.day_end - ctx.pace.day_start - (ctx.pace.breakfast_min + ctx.pace.lunch_min + ctx.pace.dinner_min)
    ratio = place.typical_visit_minutes / max(usable, 60)
    fit = 1.0 if ratio <= 0.25 else clamp(1 - (ratio - 0.25) / 0.45)
    return fit * open_day_ratio(place, ctx.weekdays)


def _fmt_money(amount: float, currency: str) -> str:
    symbol = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(currency, currency + " ")
    return f"{symbol}{amount:,.0f}"


def score_attraction(place: Place, ctx: ScoringContext) -> SuitabilityScore:
    req = ctx.req
    km = haversine_km(ctx.origin.lat, ctx.origin.lng, place.location.lat, place.location.lng)
    interest, matched = interest_component(place, req.interests)
    discovery = False
    if interest == 0.0 and place.is_famous:
        interest, discovery = 0.45, True
    elif place.is_famous:
        interest = clamp(interest + 0.15)

    fee = place.entry_fee.amount if place.entry_fee else None
    comps = {
        "interest": interest,
        "budget": affordability(fee, ctx.attraction_allowance),
        "distance": distance_component(km, ctx.pace.distance_scale_km),
        "transport": transport_component(km, req.transport_modes, ctx.pace.max_walk_km),
        "time": time_component(place, ctx),
        "pace": pace_component(place, ctx.pace, req),
    }
    reasons: list[str] = []
    if matched:
        reasons.append("Matches your interests: " + ", ".join(m.replace("_", " ") for m in matched))
        if place.is_famous:
            reasons.append("One of the city's best-known sights")
    elif discovery:
        reasons.append("Outside your selected interests, but one of the city's best-known sights")
    elif req.interests:
        reasons.append("Weak match with your selected interests")
    if fee == 0:
        reasons.append("Free entry")
    elif fee is not None:
        word = "fits" if comps["budget"] >= 0.99 else "stretches"
        reasons.append(f"Entry {_fmt_money(fee, place.entry_fee.currency)} pp {word} your daily budget (estimate)")
    else:
        reasons.append("Entry fee unknown - check locally")
    reasons.append(f"{km:.1f} km from your accommodation")
    if comps["transport"] >= 0.99 and TransportMode.WALKING in req.transport_modes and km <= ctx.pace.max_walk_km:
        reasons.append("Walkable from your accommodation")
    elif comps["transport"] < 0.5:
        reasons.append("Hard to reach with your preferred transport")
    reasons.append(f"Typical visit ~{place.typical_visit_minutes} min - "
                   + ("suits" if comps["pace"] >= 0.8 else "is long for") + f" a {req.pace.value} pace")
    if comps["time"] < 0.5:
        reasons.append("Limited opening days during your trip")
    return _finalise(comps, reasons, discovery)


def score_food_place(place: Place, ctx: ScoringContext, food_match: float, diet_reasons: list[str],
                     origin: LatLng | None = None) -> SuitabilityScore:
    req = ctx.req
    o = origin or ctx.origin
    km = haversine_km(o.lat, o.lng, place.location.lat, place.location.lng)
    cost = place.avg_cost_per_person.amount if place.avg_cost_per_person else None
    comps = {
        "interest": food_match,
        "budget": affordability(cost, ctx.meal_allowance),
        "distance": distance_component(km, ctx.pace.distance_scale_km * 0.6),
        "transport": transport_component(km, req.transport_modes, ctx.pace.max_walk_km),
        "time": open_day_ratio(place, ctx.weekdays),
        "pace": 1.0 if req.pace.value != "packed" or (place.kind == PlaceKind.CAFE or "street_food" in place.food_categories) else 0.8,
    }
    reasons = list(diet_reasons)
    matched_cats = [c for c in req.food_categories if c in place.food_categories]
    if matched_cats:
        reasons.append("Matches your food preferences: " + ", ".join(c.replace("_", " ") for c in matched_cats))
    if cost is not None:
        word = "within" if comps["budget"] >= 0.99 else "above"
        reasons.append(f"About {_fmt_money(cost, place.avg_cost_per_person.currency)} pp - {word} your per-meal budget")
    else:
        reasons.append("Price not published - estimated from price level")
    reasons.append(f"{km:.1f} km away")
    return _finalise(comps, reasons, False)


def _finalise(comps: dict[str, float], reasons: list[str], discovery: bool) -> SuitabilityScore:
    total = sum(WEIGHTS[k] * comps[k] for k in WEIGHTS)
    return SuitabilityScore(
        score=round(5 * total, 2),
        components={k: round(v, 3) for k, v in comps.items()},
        weights=WEIGHTS,
        reasons=reasons,
        discovery=discovery,
    )
