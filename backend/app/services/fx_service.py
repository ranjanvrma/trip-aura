"""Currency conversion from two free, keyless sources.

- European Central Bank reference rates (via Frankfurter): about 30 major currencies, preferred where available.
- ExchangeRate-API's open endpoint (open.er-api.com): every other currency (PKR, VND, KES...), updated daily.

Rates are cached in memory for 12 hours. If one source is down the other is still used; if both fail, the lookup
raises an error. A rate is never guessed.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from app.core.errors import ProviderRequestError, TripAuraError

log = logging.getLogger(__name__)
TTL_SECONDS = 12 * 3600
ECB = "ECB reference rate"
OPEN_ER = "ExchangeRate-API rate"
OPEN_ER_ATTRIBUTION = "Exchange rates by ExchangeRate-API (open.er-api.com)"


class FxService:
    def __init__(self, url: str, open_url: str | None = None, timeout: float = 10.0,
                 transport: httpx.BaseTransport | None = None):
        self._url = url
        self._open_url = open_url
        self._http = httpx.Client(timeout=timeout, transport=transport)
        self._rates: dict[str, float] = {}
        self._source: dict[str, str] = {}
        self._date: str | None = None
        self._fetched = 0.0
        self._lock = threading.Lock()

    def _get(self, url: str, params: dict | None = None) -> dict:
        r = self._http.get(url, params=params)
        r.raise_for_status()
        return r.json()

    def _refresh(self) -> None:
        rates: dict[str, float] = {}
        source: dict[str, str] = {}
        errors: list[str] = []
        if self._open_url:
            try:
                data = self._get(self._open_url)
                if data.get("result") != "success":
                    raise ValueError(f"result={data.get('result')}")
                for k, v in data.get("rates", {}).items():
                    rates[k], source[k] = float(v), OPEN_ER
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"open rates: {exc.__class__.__name__}")
        try:
            data = self._get(self._url, {"base": "USD"})
            for k, v in data.get("rates", {}).items():
                rates[k], source[k] = float(v), ECB      # ECB wins where it publishes a rate
            self._date = data.get("date")
        except (httpx.HTTPError, ValueError) as exc:
            errors.append(f"ECB: {exc.__class__.__name__}")
        if not rates:
            raise ProviderRequestError(f"Could not load exchange rates ({'; '.join(errors)}). "
                                       "Plan in USD or try again later.")
        if errors:
            log.warning("Exchange rates partly unavailable: %s", "; ".join(errors))
        rates["USD"], source["USD"] = 1.0, ECB
        self._rates, self._source, self._fetched = rates, source, time.monotonic()
        log.info("Loaded %d FX rates (ECB date %s)", len(rates), self._date)

    def _ensure(self) -> None:
        with self._lock:
            if not self._rates or time.monotonic() - self._fetched > TTL_SECONDS:
                self._refresh()

    def usd_to(self, currency: str) -> float:
        """Units of `currency` per 1 USD."""
        currency = currency.upper()
        if currency == "USD":
            return 1.0
        self._ensure()
        if currency not in self._rates:
            raise TripAuraError(f"No exchange rate is available for {currency} right now. Pick another currency.")
        return self._rates[currency]

    def basis(self, src: str, dst: str) -> str:
        """Which kind of rate a src -> dst conversion uses, for labelling estimates."""
        self._ensure()
        kinds = {self._source.get(c.upper(), ECB) for c in (src, dst)}
        return ECB if kinds == {ECB} else OPEN_ER

    def convert(self, amount: float, src: str, dst: str) -> float:
        if src.upper() == dst.upper():
            return amount
        return amount / self.usd_to(src) * self.usd_to(dst)
