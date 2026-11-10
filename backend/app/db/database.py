from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


def normalise_url(url: str) -> str:
    """Hosted Postgres providers (Neon, Render, Supabase) hand out postgres:// URLs; SQLAlchemy
    needs an explicit driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def init_engine(url: str | None = None):
    global _engine, _SessionLocal
    url = normalise_url(url or get_settings().database_url)
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
    else:  # serverless Postgres closes idle connections; check them before use
        kwargs = {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 3, "max_overflow": 2}
    _engine = create_engine(url, **kwargs)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    from app.db import models  # noqa: F401  (register tables)

    Base.metadata.create_all(_engine)
    migrate(_engine)
    return _engine


def migrate(engine) -> None:
    """Small idempotent schema upgrades for databases created by older versions
    (create_all adds missing tables, never missing columns). Fixed SQL only; works on SQLite and Postgres."""
    columns = {c["name"] for c in inspect(engine).get_columns("trips")}
    if "user_id" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE trips ADD COLUMN user_id INTEGER"))
        log.info("Migrated: added trips.user_id")
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_trips_user_id ON trips (user_id)"))


def get_db() -> Iterator[Session]:
    if _SessionLocal is None:
        init_engine()
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
