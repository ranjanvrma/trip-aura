from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    # Owner. NULL for trips saved before sign-in existed; those are visible to admins only.
    # (No FK constraint so the column can be added to existing databases with a plain ALTER TABLE.)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(10), default="user")   # "user" | "admin"
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LoginCode(Base):
    """A one-time sign-in code. Only an HMAC of the code is stored."""

    __tablename__ = "login_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    """Server-side session. The cookie holds a random token; only its SHA-256 is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)


class IdempotencyRecord(Base):
    """Stored response of a POST made with X-Idempotency-Key (kept 24 h).

    status_code is NULL while the first request is still running."""

    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("user_id", "key", "endpoint", name="uq_idempotency_user_key_endpoint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    key: Mapped[str] = mapped_column(String(128))
    endpoint: Mapped[str] = mapped_column(String(200))
    body_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
