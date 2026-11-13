"""Trip style: how the traveller wants to spend the budget (lowest cost, mid-range, premium).

The budget is always the ceiling. The style decides where inside it the plan aims:
- lowest cost: cheaper meals and entry fees score higher, and transport leans on walking and public transport;
- mid-range: the default balance (the behaviour before trip styles existed);
- premium: better restaurants rather than the cheapest that fit, and faster door-to-door transport.

Only the "budget" component of the suitability score and the transport choice change. The score weights and the
honesty rules (estimates labelled, outside ratings never used in the score) are untouched.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.trip import TripStyle


@dataclass(frozen=True)
class StyleProfile:
    allowance_factor: float      # scales the per-meal and per-sight allowance the cost is judged against
    cheap_floor: float           # premium only: a meal under this share of the allowance fits less well
    time_weight: float           # transport choice: time vs cost vs the traveller's preferred modes
    cost_weight: float
    leg_factor: float            # scales what one transport leg may comfortably cost
    note: str


PROFILES: dict[TripStyle, StyleProfile] = {
    TripStyle.BUDGET: StyleProfile(
        0.5, 0.0, 0.25, 0.55, 0.5, "Lowest-cost style: cheaper meals, free or cheap sights, walking and transit"),
    TripStyle.MID: StyleProfile(1.0, 0.0, 0.45, 0.35, 1.0, "Mid-range style: a balance of cost, comfort and time"),
    TripStyle.PREMIUM: StyleProfile(
        1.0, 0.35, 0.65, 0.15, 1.6, "Premium style: better restaurants and faster transport, within your budget"),
}


