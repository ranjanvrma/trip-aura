"""Offline city search index for autocomplete and city recognition in free text.

Built from GeoNames `cities15000` (every city with 15,000+ people, ~33k cities,
including alternate/local names such as "Lisboa" or "Bombay"). Licence: CC BY 4.0,
(c) GeoNames. Downloaded once into DATA_DIR/geonames; search is in memory and
typo-tolerant (rapidfuzz).
"""
from __future__ import annotations

import io
import logging
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx
from rapidfuzz import fuzz, process

from app.core.currencies import currency_for_country
from app.core.errors import ProviderRequestError
from app.core.text import fold

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class City:
    geoname_id: int
    name: str
    region: str
    country: str
    country_code: str
    lat: float
    lng: float
    population: int

    @property
    def display(self) -> str:
        parts = [self.name] + ([self.region] if self.region and self.region != self.name else []) + [self.country]
        return ", ".join(parts)

    @property
    def query(self) -> str:
        """String sent to the geocoder for this city."""
        return f"{self.name}, {self.country}"

    def to_dict(self) -> dict:
        return {"id": self.geoname_id, "name": self.name, "region": self.region, "country": self.country,
                "country_code": self.country_code, "lat": self.lat, "lng": self.lng,
                "population": self.population, "display": self.display, "query": self.query,
                "currency": currency_for_country(self.country_code)}


class CityIndex:
    def __init__(self, data_dir: str, base_url: str, user_agent: str, transport: httpx.BaseTransport | None = None):
        self.dir = Path(data_dir) / "geonames"
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.transport = transport
        self.cities: list[City] = []
        self._keys: list[tuple[str, int, bool]] = []   # (folded name variant, city index, is primary name)
        self._names: list[str] = []                    # the variants alone, for fuzzy search
        self._exact: dict[str, int] = {}
        self._lock = threading.Lock()
        self.ready = False

    # ------------------------------------------------------------------ loading
    def _download(self, name: str) -> bytes:
        path = self.dir / name
        if path.exists():
            return path.read_bytes()
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.Client(timeout=60, transport=self.transport, headers={"User-Agent": self.user_agent}) as c:
                r = c.get(f"{self.base_url}/{name}")
                r.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderRequestError(f"Could not download GeoNames {name}: {exc.__class__.__name__}") from exc
        path.write_bytes(r.content)
        log.info("Downloaded GeoNames %s (%d KB)", name, len(r.content) // 1024)
        return r.content

    def load(self) -> None:
        with self._lock:
            if self.ready:
                return
            raw = self._download("cities15000.zip")
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                text = z.read("cities15000.txt").decode("utf-8")
            countries = {}
            for line in self._download("countryInfo.txt").decode("utf-8").splitlines():
                if line and not line.startswith("#"):
                    f = line.split("\t")
                    countries[f[0]] = f[4]
            regions = {}
            for line in self._download("admin1CodesASCII.txt").decode("utf-8").splitlines():
                f = line.split("\t")
                if len(f) >= 2:
                    regions[f[0]] = f[1]
            self.load_from_text(text, countries, regions)

    def load_from_text(self, text: str, countries: dict[str, str], regions: dict[str, str]) -> None:
        cities: list[City] = []
        keys: list[tuple[str, int, bool]] = []   # (variant, city index, is primary name)
        for line in text.splitlines():
            f = line.split("\t")
            if len(f) < 15:
                continue
            cc = f[8]
            city = City(int(f[0]), f[1], regions.get(f"{cc}.{f[10]}", ""), countries.get(cc, cc), cc,
                        float(f[4]), float(f[5]), int(f[14] or 0))
            i = len(cities)
            cities.append(city)
            primary = {fold(f[1]), fold(f[2])}
            alternates = {fold(a) for a in f[3].split(",") if 2 < len(a) < 40} - primary
            keys += [(v, i, True) for v in primary if v] + [(v, i, False) for v in alternates if v]
        exact: dict[str, int] = {}
        for v, i, is_primary in keys:   # most populous city wins; primary names beat alternates
            j = exact.get(v)
            if j is None or (is_primary, cities[i].population) > (False, cities[j].population):
                exact[v] = i
        self.cities, self._keys, self._exact = cities, keys, exact
        self._names = [k for k, _, _ in keys]
        self.ready = True
        log.info("City index ready: %d cities, %d name variants", len(cities), len(keys))

    # ------------------------------------------------------------------- search
    def search(self, q: str, limit: int = 8) -> list[City]:
        if not self.ready:
            self.load()
        qf = fold(q.strip())
        if len(qf) < 2:
            return []
        country_hint = None
        if "," in qf:  # "paris, us" / "london, canada"
            qf, _, country_hint = (s.strip() for s in qf.partition(","))
        scored: dict[int, float] = {}
        for key, i, is_primary in self._keys:
            if key.startswith(qf):
                c = self.cities[i]
                # exact > prefix, primary name > alternate/foreign name, then bigger cities first
                bonus = (2.0 if key == qf else 1.0) * (1.0 if is_primary else 0.6)
                scored[i] = max(scored.get(i, 0), bonus + min(c.population, 40_000_000) / 40_000_000)
        if len(scored) < limit and len(qf) >= 4:
            for _, score, pos in process.extract(qf, self._names, scorer=fuzz.ratio, limit=limit * 4, score_cutoff=80):
                i = self._keys[pos][1]
                c = self.cities[i]
                scored.setdefault(i, score / 100 * 0.9 + min(c.population, 40_000_000) / 80_000_000)
        out = sorted(scored, key=lambda i: -scored[i])
        cities = [self.cities[i] for i in out]
        if country_hint:
            hinted = [c for c in cities if fold(c.country).startswith(country_hint) or fold(c.country_code) == country_hint
                      or fold(c.region).startswith(country_hint)]
            cities = hinted or cities
        return cities[:limit]

    def exact(self, text: str) -> City | None:
        """City whose name or alternate name equals `text` (accent/case-insensitive)."""
        if not self.ready:
            self.load()
        i = self._exact.get(fold(text.strip()))
        return self.cities[i] if i is not None else None

    def best_match(self, text: str) -> City | None:
        res = self.search(text, limit=1)
        return res[0] if res else None
