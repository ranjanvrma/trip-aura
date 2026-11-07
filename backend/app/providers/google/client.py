"""Thin HTTP wrapper shared by the Google Maps Platform providers.

Raises ProviderNotConfiguredError when no key is set and ProviderRequestError on
any HTTP/network/API-status failure. It never falls back to mock data.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import ProviderNotConfiguredError, ProviderRequestError

log = logging.getLogger(__name__)


class GoogleClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        if not settings.google_configured:
            raise ProviderNotConfiguredError(
                "DATA_MODE=live but GOOGLE_MAPS_API_KEY is not set. Add the key to backend/.env "
                "or switch DATA_MODE=mock to use the demo dataset."
            )
        self._key = settings.google_maps_api_key.strip()
        self._http = httpx.Client(timeout=settings.google_http_timeout_seconds, transport=transport)

    @property
    def key(self) -> str:
        return self._key

    def post(self, url: str, body: dict[str, Any], field_mask: str) -> dict[str, Any]:
        headers = {"X-Goog-Api-Key": self._key, "X-Goog-FieldMask": field_mask, "Content-Type": "application/json"}
        return self._send("POST", url, headers=headers, json=body)

    def get(self, url: str, params: dict[str, Any], field_mask: str | None = None) -> dict[str, Any]:
        headers = {"X-Goog-Api-Key": self._key}
        if field_mask:
            headers["X-Goog-FieldMask"] = field_mask
        return self._send("GET", url, headers=headers, params=params)

    def _send(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            log.error("Google request failed: %s %s (%s)", method, url, exc.__class__.__name__)
            raise ProviderRequestError(f"Could not reach Google Maps Platform: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            message = _error_message(resp)
            log.error("Google API error %s on %s: %s", resp.status_code, url, message)
            raise ProviderRequestError(
                f"Google Maps Platform returned HTTP {resp.status_code}: {message}",
                details={"status": resp.status_code, "url": url},
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderRequestError("Google Maps Platform returned a non-JSON response") from exc


def _error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        err = data.get("error", {})
        if isinstance(err, dict):
            return str(err.get("message") or err.get("status") or data)[:300]
        return str(data.get("error_message") or err)[:300]
    except ValueError:
        return resp.text[:300]
