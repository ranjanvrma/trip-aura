"""HTTP client for open-data services (Nominatim, Overpass, Wikimedia).

Follows the services' usage policies: identifying User-Agent, at most one
Nominatim request per second, and failover across Overpass mirrors. Errors are
raised as ProviderRequestError; nothing is replaced with mock data.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import ProviderRequestError

log = logging.getLogger(__name__)


class OpenHttp:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._http = httpx.Client(
            timeout=settings.open_http_timeout_seconds, transport=transport,
            headers={"User-Agent": settings.open_user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )
        self._nominatim_lock = threading.Lock()
        self._last_nominatim = 0.0

    def get_json(self, url: str, params: dict[str, Any] | None = None, *, what: str,
                 timeout: float | None = None) -> Any:
        try:
            r = self._http.get(url, params=params, **({"timeout": timeout} if timeout else {}))
        except httpx.HTTPError as exc:
            raise ProviderRequestError(f"{what}: could not connect ({exc.__class__.__name__})") from exc
        if r.status_code >= 400:
            raise ProviderRequestError(f"{what}: HTTP {r.status_code}", details={"url": url})
        try:
            return r.json()
        except ValueError as exc:
            raise ProviderRequestError(f"{what}: invalid JSON response") from exc

    def nominatim(self, path: str, params: dict[str, Any]) -> Any:
        with self._nominatim_lock:  # usage policy: max 1 request/second
            wait = 1.1 - (time.monotonic() - self._last_nominatim)
            if wait > 0:
                time.sleep(wait)
            try:
                return self.get_json(f"{self.settings.nominatim_url.rstrip('/')}/{path}",
                                     {**params, "format": "jsonv2"}, what="Nominatim geocoding", timeout=15)
            finally:
                self._last_nominatim = time.monotonic()

    def overpass(self, query: str, deadline: float | None = None) -> dict:
        """Tries each mirror in turn; stops when `deadline` (time.monotonic()) has passed."""
        errors: list[str] = []
        for url in self.settings.overpass_url_list:
            t0 = time.monotonic()
            remaining = (deadline - t0) if deadline is not None else self.settings.open_http_timeout_seconds
            if remaining < 5:
                errors.append("time budget used up")
                break
            try:
                # httpx timeouts are per phase, so a slow connect must not be allowed the whole budget as well
                limit = min(65.0, remaining)
                r = self._http.post(url, data={"data": query}, timeout=httpx.Timeout(limit, connect=min(8.0, limit)))
            except httpx.HTTPError as exc:
                errors.append(f"{url}: {exc.__class__.__name__}")
                log.warning("Overpass mirror %s failed: %s", url, exc.__class__.__name__)
                continue
            if r.status_code == 200:
                try:
                    data = r.json()
                except ValueError:
                    errors.append(f"{url}: invalid JSON")
                    continue
                remark = data.get("remark", "")
                if "runtime error" in remark or "timed out" in remark:
                    errors.append(f"{url}: {remark[:120]}")
                    continue
                log.info("Overpass %s answered in %.1fs (%d elements)", url, time.monotonic() - t0,
                         len(data.get("elements", [])))
                return data
            errors.append(f"{url}: HTTP {r.status_code}")
            log.warning("Overpass mirror %s returned %s", url, r.status_code)
        raise ProviderRequestError("OpenStreetMap (Overpass) is unavailable right now: " + "; ".join(errors))
