"""Transport speed profiles and heuristic durations. Fares live in engines/costs.py."""
from __future__ import annotations

from dataclasses import dataclass

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
