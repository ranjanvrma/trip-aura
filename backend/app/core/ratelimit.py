"""In-memory token-bucket rate limiting (single process, thread-safe, no external store).

Each (route class, client key) pair gets a bucket holding up to `capacity` tokens that refill
evenly over `period` seconds. Limits reset when the process restarts, which is acceptable for a
single small replica; a shared store would be needed to enforce them across several replicas.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

from fastapi import Request

from app.core.config import Settings, get_settings
from app.core.errors import RateLimitedError


@dataclass(frozen=True)
class Limit:
    capacity: int
    period: float  # seconds

    @property
    def rate(self) -> float:
        return self.capacity / self.period


# route class -> limit
LIMITS: dict[str, Limit] = {
    "auth_email": Limit(3, 15 * 60),     # sign-in code requests per email
    "auth_ip": Limit(10, 15 * 60),       # sign-in code requests per IP
    "generate": Limit(6, 60),            # trip create / preview / regenerate per user
    "geo": Limit(120, 60),               # /api/geo/* per IP
    "nlp": Limit(30, 60),                # /api/nlp/* per IP
    "default": Limit(240, 60),           # everything else per IP
}


class RateLimiter:
    def __init__(self, max_buckets: int = 50_000):
        self._buckets: dict[tuple[str, str], tuple[float, float]] = {}   # -> (tokens, last refill)
        self._lock = threading.Lock()
        self._max = max_buckets

    def hit(self, route_class: str, key: str, limit: Limit | None = None, now: float | None = None) -> int:
        """Take one token. Returns 0 when allowed, otherwise the seconds to wait (Retry-After)."""
        limit = limit or LIMITS[route_class]
        now = time.monotonic() if now is None else now
        with self._lock:
            tokens, last = self._buckets.get((route_class, key), (float(limit.capacity), now))
            tokens = min(float(limit.capacity), tokens + (now - last) * limit.rate)
            if tokens >= 1.0:
                self._buckets[(route_class, key)] = (tokens - 1.0, now)
                if len(self._buckets) > self._max:
                    self._prune(now)
                return 0
            self._buckets[(route_class, key)] = (tokens, now)
            return max(1, math.ceil((1.0 - tokens) / limit.rate))

    def _prune(self, now: float) -> None:
        """Drop buckets that have refilled completely (they carry no state)."""
        for k, (tokens, last) in list(self._buckets.items()):
            lim = LIMITS.get(k[0])
            if lim is None or tokens + (now - last) * lim.rate >= lim.capacity:
                del self._buckets[k]

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


limiter = RateLimiter()


def enforce(route_class: str, key: str, message: str) -> None:
    """Take a token for `key` or raise RateLimitedError (no-op when RATE_LIMIT_ENABLED=false)."""
    if get_settings().rate_limit_enabled:
        wait = limiter.hit(route_class, key)
        if wait:
            raise RateLimitedError(wait, message)


def client_ip(request: Request, settings: Settings | None = None) -> str:
    """The socket peer address, or, when proxy headers are trusted, the X-Forwarded-For entry written by the
    outermost trusted proxy. Entries are counted from the right (each proxy appends the address it saw), so a
    client can't spoof its address by sending its own X-Forwarded-For: anything it adds sits further left."""
    settings = settings or get_settings()
    if settings.trust_proxy_headers:
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if hops:
            return hops[-min(settings.trusted_proxy_count, len(hops))][:64]
    return request.client.host if request.client else "unknown"


def ip_route_class(method: str, path: str) -> str:
    """Route class for the per-IP limit applied to every request."""
    if path == "/api/auth/request-code" and method == "POST":
        return "auth_ip"
    if path.startswith("/api/geo/"):
        return "geo"
    if path.startswith("/api/nlp/"):
        return "nlp"
    return "default"
