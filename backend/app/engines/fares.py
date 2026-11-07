"""Transport speed profiles and fare tables.

All values here are ESTIMATES used when a provider does not return a real fare
(Google returns fares only for some transit routes; never for cabs or autos).
Every Money produced here has verified=False and source="estimate".
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app.schemas.common import DataSource, Money
from app.schemas.trip import TransportMode


@dataclass(frozen=True)
class ModeProfile:
    speed_kmh: float          # average in-motion urban speed
    overhead_min: float       # waiting / pickup / parking / station access
    detour_factor: float      # road distance vs straight line
    traffic_sensitive: bool
    per_person: bool          # fare charged per traveller (True) or per vehicle (False)
    capacity: int             # travellers per vehicle when per_person is False


MODE_PROFILES: dict[TransportMode, ModeProfile] = {
    TransportMode.WALKING: ModeProfile(4.5, 0, 1.25, False, True, 99),
    TransportMode.METRO: ModeProfile(32, 10, 1.2, False, True, 99),
    TransportMode.BUS: ModeProfile(15, 10, 1.35, True, True, 99),
    TransportMode.TRAIN: ModeProfile(40, 15, 1.3, False, True, 99),
    TransportMode.AUTO: ModeProfile(20, 3, 1.3, True, False, 3),
    TransportMode.CAB: ModeProfile(24, 6, 1.3, True, False, 4),
    TransportMode.PERSONAL_VEHICLE: ModeProfile(25, 6, 1.3, True, False, 5),
}

# (base, per_km, minimum, maximum or None) in the given currency.
FARE_TABLES: dict[str, dict[TransportMode, tuple[float, float, float, float | None]]] = {
    "INR": {
        TransportMode.WALKING: (0, 0, 0, 0),
        TransportMode.METRO: (8, 2.5, 10, 35),
        TransportMode.BUS: (10, 1.0, 10, 40),
        TransportMode.TRAIN: (15, 0.6, 15, None),
        TransportMode.AUTO: (30, 15, 40, None),
        TransportMode.CAB: (60, 18, 100, None),
        TransportMode.PERSONAL_VEHICLE: (30, 6, 30, None),   # fuel + one parking fee
    },
    "USD": {
        TransportMode.WALKING: (0, 0, 0, 0),
        TransportMode.METRO: (2.5, 0, 2.5, 3.5),
        TransportMode.BUS: (2.0, 0, 2.0, 3.0),
        TransportMode.TRAIN: (3.0, 0.25, 3.0, None),
        TransportMode.AUTO: (3.0, 1.2, 5.0, None),
        TransportMode.CAB: (4.0, 1.8, 8.0, None),
        TransportMode.PERSONAL_VEHICLE: (5.0, 0.2, 5.0, None),
    },
    "EUR": {
        TransportMode.WALKING: (0, 0, 0, 0),
        TransportMode.METRO: (2.0, 0, 2.0, 3.5),
        TransportMode.BUS: (2.0, 0, 2.0, 3.0),
        TransportMode.TRAIN: (3.0, 0.2, 3.0, None),
        TransportMode.AUTO: (3.0, 1.1, 5.0, None),
        TransportMode.CAB: (4.0, 1.7, 8.0, None),
        TransportMode.PERSONAL_VEHICLE: (4.0, 0.2, 4.0, None),
    },
    "GBP": {
        TransportMode.WALKING: (0, 0, 0, 0),
        TransportMode.METRO: (2.8, 0, 2.8, 4.0),
        TransportMode.BUS: (1.75, 0, 1.75, 2.0),
        TransportMode.TRAIN: (3.0, 0.25, 3.0, None),
        TransportMode.AUTO: (3.0, 1.0, 5.0, None),
        TransportMode.CAB: (4.0, 1.6, 7.0, None),
        TransportMode.PERSONAL_VEHICLE: (4.0, 0.2, 4.0, None),
    },
}


def estimate_fare(mode: TransportMode, distance_km: float, currency: str, travelers: int = 1) -> Money:
    base, per_km, minimum, maximum = FARE_TABLES[currency][mode]
    unit = max(minimum, base + per_km * distance_km) if mode != TransportMode.WALKING else 0.0
    if maximum is not None:
        unit = min(unit, maximum)
    profile = MODE_PROFILES[mode]
    multiplier = travelers if profile.per_person else math.ceil(travelers / profile.capacity)
    note = "per person fare table" if profile.per_person else f"per vehicle (x{multiplier})"
    return Money.estimate(unit * multiplier, currency, note=f"Estimated {mode.value} cost, {note}")


def simulated_traffic_multiplier(minute_of_day: int) -> float:
    """Deterministic time-of-day congestion used ONLY in mock mode (labelled as simulated)."""
    h = minute_of_day / 60
    if 8.5 <= h < 10.5 or 17.5 <= h < 20.5:
        return 1.45
    if 12 <= h < 15:
        return 1.15
    return 1.0


def heuristic_duration_min(mode: TransportMode, straight_km: float, traffic: float = 1.0) -> tuple[float, float]:
    """Returns (distance_km, duration_min) from a straight-line distance."""
    p = MODE_PROFILES[mode]
    dist = straight_km * p.detour_factor
    moving = dist / p.speed_kmh * 60
    if p.traffic_sensitive:
        moving *= traffic
    return dist, moving + p.overhead_min
