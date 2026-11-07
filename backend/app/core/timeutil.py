"""Minutes-since-midnight helpers. The scheduler works in integer minutes."""
from __future__ import annotations


def hm_to_min(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)


def min_to_hm(minutes: int) -> str:
    minutes = int(round(minutes))
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def period_of(minute: int) -> str:
    if minute < 12 * 60:
        return "morning"
    if minute < 17 * 60:
        return "afternoon"
    return "evening"
