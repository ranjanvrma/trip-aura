"""Currency conversion via the Frankfurter API (European Central Bank reference rates, no key).

Rates are cached in memory for 12 hours. A failed lookup raises an error; it is never
replaced by a guessed rate.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from app.core.errors import ProviderRequestError, TripAuraError

log = logging.getLogger(__name__)
TTL_SECONDS = 12 * 3600


class FxService:
    def __init__(self, url: str, timeout: float = 10.0, transport: httpx.BaseTransport | None = None):
        self._url = url
        self._http = httpx.Client(timeout=timeout, transport=transport)
        self._rates: dict[str, float] = {}
        self._date: str | None = None
        self._fetched = 0.0
        self._lock = threading.Lock()

    def _refresh(self) -> None:
        try:
            r = self._http.get(self._url, params={"base": "USD"})
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderRequestError(f"Could not load exchange rates ({exc.__class__.__name__}). "
                                       "Plan in USD or try again later.") from exc
        self._rates = {"USD": 1.0, **{k: float(v) for k, v in data.get("rates", {}).items()}}
        self._date = data.get("date")
        self._fetched = time.monotonic()
        log.info("Loaded %d FX rates (ECB date %s)", len(self._rates), self._date)

    def usd_to(self, currency: str) -> float:
        """Units of `currency` per 1 USD."""
        currency = currency.upper()
        if currency == "USD":
            return 1.0
        with self._lock:
            if not self._rates or time.monotonic() - self._fetched > TTL_SECONDS:
                self._refresh()
        if currency not in self._rates:
            raise TripAuraError(f"Currency {currency} is not supported by the exchange-rate source")
        return self._rates[currency]

    def convert(self, amount: float, src: str, dst: str) -> float:
        if src.upper() == dst.upper():
            return amount
        return amount / self.usd_to(src) * self.usd_to(dst)

    @property
    def rate_date(self) -> str | None:
        return self._date
