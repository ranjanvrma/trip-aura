"""Worldwide cost model for estimates (fares, meals, unknown entry fees).

How an estimate is built:
1. If a hand-curated local table exists for the destination country (currently India, INR),
   it is used and converted to the trip currency.
2. Otherwise US reference prices are scaled by an approximate country price index and
   converted from USD to the trip currency (ECB reference rates, or ExchangeRate-API for other currencies).

Every value produced here is an ESTIMATE (verified=False, source="estimate").
The price index is a rough, hand-maintained approximation of relative tourist costs
(US = 1.0); it is not a measured statistic.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.engines.fares import MODE_PROFILES
from app.schemas.common import Money
from app.schemas.trip import TransportMode

FareRow = tuple[float, float, float, float | None]  # base, per_km, minimum, maximum

# US reference prices (USD)
US_FARES: dict[TransportMode, FareRow] = {
    TransportMode.WALKING: (0, 0, 0, 0),
    TransportMode.METRO: (2.75, 0, 2.75, 3.5),
    TransportMode.BUS: (2.0, 0, 2.0, 3.0),
    TransportMode.TRAIN: (3.0, 0.25, 3.0, None),
    TransportMode.AUTO: (2.0, 1.0, 3.0, None),        # tuk-tuk / auto-rickshaw / moto-taxi style
    TransportMode.CAB: (4.0, 1.8, 8.0, None),
    TransportMode.PERSONAL_VEHICLE: (5.0, 0.2, 5.0, None),  # fuel + one parking fee
}
US_MEAL_BY_LEVEL = {0: 6.0, 1: 14.0, 2: 28.0, 3: 60.0, 4: 110.0}
US_UNKNOWN_ENTRY_FEE = 15.0

# Hand-curated local tables: country -> prices in that table's own currency.
CURATED: dict[str, dict] = {
    "IN": {
        "currency": "INR",
        "fares": {
            TransportMode.WALKING: (0, 0, 0, 0),
            TransportMode.METRO: (8, 2.5, 10, 35),
            TransportMode.BUS: (10, 1.0, 10, 40),
            TransportMode.TRAIN: (15, 0.6, 15, None),
            TransportMode.AUTO: (30, 15, 40, None),
            TransportMode.CAB: (60, 18, 100, None),
            TransportMode.PERSONAL_VEHICLE: (30, 6, 30, None),
        },
        "meal": {0: 100, 1: 250, 2: 500, 3: 1200, 4: 2500},
        "entry": 100,
    },
}

# Approximate relative price level for travellers (US = 1.0). Hand-maintained, rough.
COUNTRY_PRICE_INDEX: dict[str, float] = {
    "US": 1.0, "CA": 0.9, "MX": 0.5, "BR": 0.5, "AR": 0.45, "CL": 0.6, "CO": 0.4, "PE": 0.45, "CR": 0.7,
    "GB": 0.95, "IE": 1.0, "FR": 0.9, "DE": 0.85, "NL": 0.95, "BE": 0.9, "LU": 1.0, "CH": 1.4, "AT": 0.9,
    "IT": 0.8, "ES": 0.7, "PT": 0.65, "GR": 0.65, "DK": 1.1, "SE": 0.9, "NO": 1.1, "FI": 0.95, "IS": 1.2,
    "PL": 0.5, "CZ": 0.6, "HU": 0.5, "RO": 0.45, "BG": 0.4, "HR": 0.6, "RS": 0.45, "SI": 0.65, "SK": 0.55,
    "EE": 0.65, "LV": 0.55, "LT": 0.55, "TR": 0.45, "GE": 0.4, "AM": 0.4, "RU": 0.45, "UA": 0.35,
    "IL": 1.0, "AE": 0.85, "SA": 0.7, "QA": 0.85, "JO": 0.6, "EG": 0.25, "MA": 0.4, "TN": 0.35,
    "ZA": 0.45, "KE": 0.4, "TZ": 0.4, "NG": 0.35, "GH": 0.4, "ET": 0.3,
    "IN": 0.25, "PK": 0.2, "BD": 0.25, "LK": 0.3, "NP": 0.25, "MV": 0.8,
    "CN": 0.55, "HK": 0.95, "MO": 0.85, "TW": 0.6, "JP": 0.75, "KR": 0.75, "MN": 0.4,
    "SG": 1.0, "MY": 0.4, "TH": 0.4, "VN": 0.3, "ID": 0.35, "PH": 0.4, "KH": 0.35, "LA": 0.3, "MM": 0.3,
    "AU": 1.0, "NZ": 0.95, "FJ": 0.6,
}
DEFAULT_PRICE_INDEX = 0.7


@dataclass
class CostModel:
    currency: str                       # trip currency
    country_code: str | None
    fares: dict[TransportMode, FareRow]  # in trip currency
    meal_by_level: dict[int, float]      # per person, trip currency
    unknown_entry_fee: float             # per person, trip currency
    basis: str                           # human-readable description of the basis
    notes: list[str] = field(default_factory=list)
    fx: object | None = None             # FxService, used to convert prices quoted in other currencies

    # ---- construction ---------------------------------------------------------
    @classmethod
    def build(cls, country_code: str | None, currency: str, fx=None) -> "CostModel":
        """`fx` is an FxService-like object (usd_to / convert). Only needed when converting."""
        cc = (country_code or "").upper() or None
        currency = currency.upper()
        curated = CURATED.get(cc or "")
        if curated:
            src = curated["currency"]
            k = 1.0 if src == currency else fx.convert(1.0, src, currency)
            return cls(
                currency=currency, country_code=cc,
                fares={m: _scale(row, k) for m, row in curated["fares"].items()},
                meal_by_level={lvl: v * k for lvl, v in curated["meal"].items()},
                unknown_entry_fee=curated["entry"] * k,
                basis=f"curated {cc} price table" + ("" if k == 1.0 else f" converted {src}->{currency}"),
                fx=fx,
            )
        notes = []
        index = COUNTRY_PRICE_INDEX.get(cc or "")
        if index is None:
            index = DEFAULT_PRICE_INDEX
            notes.append(f"No price index for country '{cc or 'unknown'}'; a generic level ({index}) is used.")
        k = index * (1.0 if currency == "USD" else fx.usd_to(currency))
        return cls(
            currency=currency, country_code=cc,
            fares={m: _scale(row, k) for m, row in US_FARES.items()},
            meal_by_level={lvl: v * k for lvl, v in US_MEAL_BY_LEVEL.items()},
            unknown_entry_fee=US_UNKNOWN_ENTRY_FEE * k,
            basis=f"US reference prices x {index} price index ({cc or 'unknown'})"
                  + ("" if currency == "USD" else f", converted USD->{currency}"),
            notes=notes, fx=fx,
        )

    @classmethod
    def fallback(cls, currency: str) -> "CostModel":
        """Used when a caller passes no cost model: the curated India table for INR trips, US prices otherwise."""
        return cls.build("IN" if currency == "INR" else "US", currency)

    # ---- estimates --------------------------------------------------------------
    def fare(self, mode: TransportMode, distance_km: float, travelers: int = 1) -> Money:
        base, per_km, minimum, maximum = self.fares[mode]
        unit = 0.0 if mode == TransportMode.WALKING else max(minimum, base + per_km * distance_km)
        if maximum is not None:
            unit = min(unit, maximum)
        profile = MODE_PROFILES[mode]
        multiplier = travelers if profile.per_person else math.ceil(travelers / profile.capacity)
        who = "per person" if profile.per_person else f"per vehicle (x{multiplier})"
        return Money.estimate(unit * multiplier, self.currency,
                              note=f"Estimated {mode.value.replace('_', ' ')} cost, {who}; {self.basis}")

    def meal(self, level: int | None) -> float:
        return self.meal_by_level[level if level is not None else 1]

    def to_trip_currency(self, m: Money) -> Money:
        """Same Money if already in the trip currency; otherwise converted and marked as an estimate."""
        if m.currency.upper() == self.currency:
            return m
        if m.amount == 0:
            return m.model_copy(update={"currency": self.currency})
        if self.fx is None:
            raise ValueError(f"Cannot convert {m.currency} to {self.currency} without exchange rates")
        amount = self.fx.convert(m.amount, m.currency, self.currency)
        return Money(amount=round(amount, 2), currency=self.currency, verified=False, source=m.source,
                     note=f"{m.amount:g} {m.currency} converted at {self.fx.basis(m.currency, self.currency)}" + (f"; {m.note}" if m.note else ""))


def _scale(row: FareRow, k: float) -> FareRow:
    base, per_km, minimum, maximum = row
    return (base * k, per_km * k, minimum * k, None if maximum is None else maximum * k)
