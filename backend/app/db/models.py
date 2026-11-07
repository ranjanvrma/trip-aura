from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class CityDataset(Base):
    """Open-data places for one city, loaded on first use and refreshed after CITY_CACHE_DAYS."""

    __tablename__ = "city_datasets"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    built_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JSON)


class Trip(Base):
    """A saved trip request and its latest generated itinerary."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    title: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(120), index=True)
    num_days: Mapped[int] = mapped_column(Integer)
    data_source: Mapped[str] = mapped_column(String(20))
    request_json: Mapped[dict] = mapped_column(JSON)
    itinerary_json: Mapped[dict] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
