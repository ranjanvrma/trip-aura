"""X-Idempotency-Key handling for POSTs that generate trips.

The first request with a key reserves a row (status NULL = in flight), runs, and stores its status
and JSON response. A retry with the same user, key, endpoint and body gets the stored response
back; the same key with another body is refused. Records expire after 24 h.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from fastapi import Header
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import IdempotencyKeyRequiredError, IdempotencyKeyReusedError, RequestInProgressError
from app.db.models import IdempotencyRecord
from app.core.timeutil import as_utc, utc_now

HEADER = "X-Idempotency-Key"
TTL = dt.timedelta(hours=24)
STALE_IN_FLIGHT = dt.timedelta(minutes=10)   # a reservation this old belongs to a crashed request
_KEY = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def idempotency_key(x_idempotency_key: str | None = Header(default=None)) -> str:
    """FastAPI dependency: the validated X-Idempotency-Key header."""
    if x_idempotency_key is None or not _KEY.match(x_idempotency_key):
        raise IdempotencyKeyRequiredError(
            f"Send an {HEADER} header (8-128 characters: letters, digits, '-' or '_') with this request")
    return x_idempotency_key


def body_hash(body: Any) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class Idempotency:
    """Usage: run(status, produce), or begin() -> replay response or None; then finish(...) or abort()."""

    def __init__(self, db: Session, user_id: int, key: str, endpoint: str, body: Any):
        self.db, self.user_id, self.key, self.endpoint = db, user_id, key, endpoint
        self.hash = body_hash(body)
        self.record: IdempotencyRecord | None = None

    def _existing(self) -> IdempotencyRecord | None:
        return self.db.scalars(select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == self.user_id, IdempotencyRecord.key == self.key,
            IdempotencyRecord.endpoint == self.endpoint)).first()

    def begin(self) -> JSONResponse | None:
        t = utc_now()
        self.db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.created_at < t - TTL))
        self.db.commit()
        old = self._existing()
        if old is not None and old.status_code is None and as_utc(old.created_at) < t - STALE_IN_FLIGHT:
            self.db.delete(old)
            self.db.commit()
            old = None
        if old is None:
            rec = IdempotencyRecord(user_id=self.user_id, key=self.key, endpoint=self.endpoint,
                                    body_hash=self.hash, created_at=t)
            self.db.add(rec)
            try:
                self.db.commit()
                self.record = rec
                return None
            except IntegrityError:   # a concurrent request reserved the key first
                self.db.rollback()
                old = self._existing()
                if old is None:
                    raise RequestInProgressError("A request with this idempotency key is in progress") from None
        if old.body_hash != self.hash:
            raise IdempotencyKeyReusedError("This idempotency key was already used with a different request")
        if old.status_code is None:
            raise RequestInProgressError("A request with this idempotency key is still in progress")
        return JSONResponse(status_code=old.status_code, content=old.response_json,
                            headers={"Idempotent-Replayed": "true"})

    def run(self, status_code: int, produce: Callable[[], BaseModel]) -> BaseModel | JSONResponse:
        """The stored response for a retry; otherwise produce() once and store its result.
        Any failure (including client disconnects) releases the key so the request can be retried."""
        replay = self.begin()
        if replay is not None:
            return replay
        try:
            result = produce()
            self.finish(status_code, result.model_dump(mode="json"))
        except BaseException:
            self.abort()
            raise
        return result

    def finish(self, status_code: int, response_json: Any) -> None:
        if self.record is None:
            return
        self.record.status_code = status_code
        self.record.response_json = response_json
        self.db.commit()

    def abort(self) -> None:
        """Release the reservation so the client can retry after a failure."""
        if self.record is None:
            return
        try:
            self.db.rollback()
            self.db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.id == self.record.id))
            self.db.commit()
        finally:
            self.record = None
