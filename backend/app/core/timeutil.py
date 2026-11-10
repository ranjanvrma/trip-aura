"""Time helpers: UTC timestamps for stored records, and minutes-since-midnight for the scheduler."""
from __future__ import annotations

import datetime as dt


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def as_utc(t: dt.datetime) -> dt.datetime:
    """SQLite returns naive datetimes; everything is stored in UTC."""
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


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
