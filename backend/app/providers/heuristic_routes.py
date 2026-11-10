"""Heuristic route estimates: straight-line distance x detour factor and mode speed profiles.

Used by mock mode (with the demo metro network) and open mode (with stations from
OpenStreetMap). Results are labelled as estimates; traffic is a typical
time-of-day slowdown, not live data.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from app.core.geo import haversine_km, interpolate
from app.engines.fares import MODE_PROFILES, heuristic_duration_min, simulated_traffic_multiplier
from app.providers.base import CityContext, RouteResult
from app.schemas.common import DataSource, LatLng
from app.schemas.trip import TransportMode

STATION_REACH_KM = {"metro": 1.5, "train": 2.0}
# "rail" = station whose type is unknown (from Overture); usable for metro and train estimates
MODE_KINDS = {"metro": ("metro", "rail"), "train": ("train", "rail")}


class HeuristicRoutesProvider:
    def __init__(self, stations_for: Callable[[CityContext], list[dict]], source: DataSource,
                 traffic_label: str = "typical rush-hour slowdown (estimate, not live traffic)",
                 traffic_is_simulated: bool = False):
        self.stations_for = stations_for
        self.source = source
        self.traffic_label = traffic_label
        self.traffic_is_simulated = traffic_is_simulated   # mock mode marks its traffic as "simulated"

    def _nearest(self, stations: list[dict], kind: str, p: LatLng) -> tuple[dict | None, float]:
        best, best_d = None, 1e9
        for s in stations:
            if s["kind"] not in MODE_KINDS[kind]:
                continue
            d = haversine_km(p.lat, p.lng, s["lat"], s["lng"])
            if d < best_d:
                best, best_d = s, d
        return best, best_d

    def compute_route(self, origin: LatLng, destination: LatLng, mode: TransportMode,
                      departure: dt.datetime | None, city: CityContext) -> RouteResult:
        straight = haversine_km(origin.lat, origin.lng, destination.lat, destination.lng)
        minute = (departure.hour * 60 + departure.minute) if departure else 11 * 60
        traffic = simulated_traffic_multiplier(minute)
        line = [LatLng(lat=a, lng=b) for a, b in interpolate(origin.as_tuple(), destination.as_tuple(), 6)]

        if mode in (TransportMode.METRO, TransportMode.TRAIN):
            kind = "metro" if mode == TransportMode.METRO else "train"
            stations = self.stations_for(city)
            s1, d1 = self._nearest(stations, kind, origin)
            s2, d2 = self._nearest(stations, kind, destination)
            reach = STATION_REACH_KM[kind]
            if s1 is None:
                return RouteResult.unavailable(mode, self.source, f"No {kind} stations mapped in this city", straight)
            if d1 > reach or d2 > reach or s1["name"] == s2["name"]:
                return RouteResult.unavailable(mode, self.source, f"No {kind} station within {reach} km of both ends",
                                               straight)
            if mode == TransportMode.TRAIN and straight < 8:
                return RouteResult.unavailable(mode, self.source, "Train not useful for short intra-city hops", straight)
            walk = (d1 + d2) * 1.25 / MODE_PROFILES[TransportMode.WALKING].speed_kmh * 60
            dist, dur = heuristic_duration_min(mode, straight)
            unverified = " - station type not verified" if "rail" in (s1["kind"], s2["kind"]) else ""
            return RouteResult(mode, round(dist + d1 + d2, 2), round(dur + walk, 1), None, False, line, self.source,
                               note=f"{kind.title()} {s1['name']} -> {s2['name']} incl. walking to stations (estimate; "
                                    f"assumes a direct line{unverified})")

        dist, dur = heuristic_duration_min(mode, straight, traffic)
        _, free_flow = heuristic_duration_min(mode, straight, 1.0)
        sensitive = MODE_PROFILES[mode].traffic_sensitive
        note = "Estimate from distance and typical speeds"
        if sensitive and traffic > 1:
            note = f"{note}; x{traffic:.2f} {self.traffic_label}"
        if mode == TransportMode.BUS:
            note += "; bus routes not verified"
        return RouteResult(
            mode, round(dist, 2), round(dur, 1), round(free_flow, 1) if sensitive else None,
            traffic_aware=sensitive and self.traffic_is_simulated, polyline=line, source=self.source, note=note,
        )
