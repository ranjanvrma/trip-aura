"""Budget engine: item costing, per-day/category totals, and savings suggestions.

Verified vs estimated money is tracked separately:
- verified: Money.verified=True (provider-returned fares) or user-supplied amounts
- estimated: everything else (fare tables, price-level tables, demo values)
"""
from __future__ import annotations

from app.core.geo import haversine_km
from app.schemas.common import DataSource, Money
from app.schemas.itinerary import (
    BudgetSuggestion, BudgetSummary, CategoryTotals, DayBudget, DayPlan, ItemType, ItineraryItem,
)
from app.schemas.place import Place, PlaceKind, SuitabilityScore
from app.schemas.trip import TransportMode, TripRequest

# Typical per-person meal cost by Google price level (0-4), used when no price is published.
PRICE_LEVEL_MEAL = {
    "INR": {0: 100, 1: 250, 2: 500, 3: 1200, 4: 2500},
    "USD": {0: 8, 1: 14, 2: 28, 3: 55, 4: 100},
    "EUR": {0: 8, 1: 13, 2: 25, 3: 50, 4: 90},
    "GBP": {0: 7, 1: 12, 2: 22, 3: 45, 4: 80},
}
UNKNOWN_ENTRY_FEE = {"INR": 100, "USD": 15, "EUR": 12, "GBP": 12}
BREAKFAST_FACTOR = 0.6
CHEAP_MODES = {TransportMode.WALKING, TransportMode.METRO, TransportMode.BUS}


def entry_cost(place: Place, req: TripRequest) -> Money:
    if place.entry_fee is not None:
        fee = place.entry_fee
        return fee.model_copy(update={"amount": round(fee.amount * req.travelers, 2)})
    if place.kind == PlaceKind.PARK:
        return Money.estimate(0, req.currency, note="Parks are usually free - entry fee not published")
    return Money.estimate(UNKNOWN_ENTRY_FEE[req.currency] * req.travelers, req.currency,
                          note="Entry fee not available from the provider - typical value assumed")


def meal_cost(place: Place | None, meal: str, req: TripRequest) -> Money:
    factor = BREAKFAST_FACTOR if meal == "breakfast" else 1.0
    if place is not None and place.avg_cost_per_person is not None \
            and place.avg_cost_per_person.currency == req.currency:
        m = place.avg_cost_per_person
        return m.model_copy(update={"amount": round(m.amount * factor * req.travelers, 2)})
    level = place.price_level if place is not None and place.price_level is not None else 1
    base = PRICE_LEVEL_MEAL[req.currency][level]
    who = "restaurant price level" if place is not None and place.price_level is not None else "typical budget meal"
    return Money.estimate(base * factor * req.travelers, req.currency, note=f"Estimated from {who}")


def _is_verified(m: Money) -> bool:
    return m.verified or m.source == DataSource.USER


def day_budget(day_number: int, items: list[ItineraryItem]) -> DayBudget:
    totals = CategoryTotals()
    verified = estimated = 0.0
    for it in items:
        for money, cat in _item_costs(it):
            setattr(totals, cat, round(getattr(totals, cat) + money.amount, 2))
            if _is_verified(money):
                verified += money.amount
            else:
                estimated += money.amount
    return DayBudget(day_number=day_number, totals=totals, total=totals.total(),
                     verified_amount=round(verified, 2), estimated_amount=round(estimated, 2))


def _item_costs(it: ItineraryItem) -> list[tuple[Money, str]]:
    out: list[tuple[Money, str]] = []
    if it.type == ItemType.TRAVEL and it.travel is not None:
        out.append((it.travel.chosen.cost, "transport"))
    elif it.type == ItemType.MEAL and it.cost is not None:
        out.append((it.cost, "food"))
    elif it.type == ItemType.ACTIVITY and it.cost is not None:
        out.append((it.cost, "attractions"))
    return out


def summarize(days: list[DayPlan], req: TripRequest) -> BudgetSummary:
    cat = CategoryTotals()
    verified = estimated = 0.0
    per_day = []
    for d in days:
        db = day_budget(d.day_number, d.items)
        d.budget = db
        per_day.append(db)
        for k in ("food", "transport", "attractions"):
            setattr(cat, k, round(getattr(cat, k) + getattr(db.totals, k), 2))
        verified += db.verified_amount
        estimated += db.estimated_amount
    notes = []
    if req.accommodation_cost_total > 0:
        cat.accommodation = req.accommodation_cost_total
        verified += req.accommodation_cost_total
        notes.append("Accommodation cost is the amount you entered.")
    else:
        notes.append("Accommodation is not included (no accommodation cost entered).")
    planned = cat.total()
    notes.append("Estimated amounts come from fare tables, price levels or demo data - confirm locally.")
    return BudgetSummary(
        currency=req.currency, total_budget=req.budget, planned_total=planned,
        remaining=round(req.budget - planned, 2), over_budget=planned > req.budget, by_category=cat,
        per_day=per_day, verified_total=round(verified, 2), estimated_total=round(estimated, 2), notes=notes,
    )


def suggest_savings(days: list[DayPlan], req: TripRequest, spare_attractions: list[tuple[Place, SuitabilityScore]],
                    cheaper_food: callable | None = None, limit: int = 10) -> list[BudgetSuggestion]:
    """Concrete ways to cut cost, largest saving first."""
    out: list[BudgetSuggestion] = []
    used_alt: set[str] = set()
    for d in days:
        for it in d.items:
            if it.type == ItemType.TRAVEL and it.travel:
                cur = it.travel.chosen
                cheaper = [a for a in it.travel.alternatives
                           if a.practical and a.cost.amount < cur.cost.amount and a.duration_min <= cur.duration_min + 20]
                if cheaper:
                    alt = min(cheaper, key=lambda a: a.cost.amount)
                    out.append(BudgetSuggestion(
                        kind="cheaper_transport", item_id=it.id,
                        estimated_saving=round(cur.cost.amount - alt.cost.amount, 2),
                        message=(f"Day {d.day_number}: take {alt.mode.value.replace('_', ' ')} instead of "
                                 f"{cur.mode.value.replace('_', ' ')} to {it.travel.to_name} "
                                 f"(+{max(0, alt.duration_min - cur.duration_min):.0f} min)."),
                    ))
            elif it.type == ItemType.ACTIVITY and it.place and it.cost and it.cost.amount > 0:
                alts = [(p, s) for p, s in spare_attractions
                        if p.id not in used_alt and (p.entry_fee is not None and p.entry_fee.amount == 0)
                        and haversine_km(p.location.lat, p.location.lng, it.place.location.lat, it.place.location.lng) < 6
                        and (it.suitability is None or s.score >= it.suitability.score - 1.0)]
                if alts:
                    p, s = max(alts, key=lambda ps: ps[1].score)
                    used_alt.add(p.id)
                    out.append(BudgetSuggestion(
                        kind="free_attraction", item_id=it.id, alternative_place_id=p.id,
                        estimated_saving=it.cost.amount,
                        message=f"Day {d.day_number}: swap {it.place.name} for free {p.name} (suitability {s.score:.1f}/5).",
                    ))
            elif it.type == ItemType.MEAL and it.place and it.cost and cheaper_food is not None:
                alt = cheaper_food(it, d)
                if alt is not None:
                    alt_place, alt_cost = alt
                    if alt_cost < it.cost.amount * 0.8:
                        out.append(BudgetSuggestion(
                            kind="cheaper_food", item_id=it.id, alternative_place_id=alt_place.id,
                            estimated_saving=round(it.cost.amount - alt_cost, 2),
                            message=f"Day {d.day_number}: {it.meal_type} at {alt_place.name} instead of {it.place.name}.",
                        ))
    out.sort(key=lambda s: -s.estimated_saving)
    return out[:limit]
