"""Pure geometry helpers used by engines (no network)."""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def degree_span(lat: float, radius_km: float) -> tuple[float, float]:
    """(delta latitude, delta longitude) in degrees covering `radius_km` around latitude `lat`."""
    return radius_km / 111.0, radius_km / (111.0 * max(0.2, math.cos(math.radians(lat))))


def interpolate(a: tuple[float, float], b: tuple[float, float], steps: int = 8) -> list[tuple[float, float]]:
    return [(a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps) for i in range(steps + 1)]
