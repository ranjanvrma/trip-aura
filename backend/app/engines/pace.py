"""Pace profiles: how long days are, how many activities fit, how much rest."""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.trip import Pace


@dataclass(frozen=True)
class PaceProfile:
    day_start: int            # minutes since midnight
    day_end: int              # latest time to be back at the accommodation
    max_activities: int
    rest_after_lunch: int     # minutes
    buffer_min: int           # slack added after each travel leg
    max_walk_km: float        # walking beyond this is impractical for this pace
    distance_scale_km: float  # distance at which suitability's distance component halves
    breakfast_min: int
    lunch_min: int
    dinner_min: int
    max_visit_min: int        # visits longer than this feel heavy for this pace


PACE_PROFILES: dict[Pace, PaceProfile] = {
    Pace.RELAXED: PaceProfile(9 * 60 + 30, 21 * 60, 3, 60, 15, 1.5, 7.0, 45, 75, 90, 150),
    Pace.MODERATE: PaceProfile(9 * 60, 21 * 60 + 30, 5, 30, 10, 2.5, 10.0, 40, 60, 75, 180),
    Pace.PACKED: PaceProfile(8 * 60, 22 * 60 + 30, 7, 0, 5, 3.0, 13.0, 30, 45, 60, 240),
}

LUNCH_WINDOW = (12 * 60 + 30, 14 * 60 + 30)
DINNER_WINDOW = (19 * 60, 21 * 60 + 30)


def profile_for(pace: Pace) -> PaceProfile:
    return PACE_PROFILES[pace]
