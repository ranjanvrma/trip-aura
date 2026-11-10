from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utc_now
from app.db.database import Base


class CityDataset(Base):
    """Open-data places for one city, loaded on first use and refreshed after CITY_CACHE_DAYS."""

    __tablename__ = "city_datasets"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    built_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JSON)
