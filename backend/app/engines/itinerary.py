"""Itinerary engine: selects, orders and schedules places into day plans.

Two passes per day:
1. PLAN (cheap): greedy construction using straight-line travel estimates.
   At each step the next stop maximises
       suitability - travel penalty - waiting penalty + time-of-day fit
   subject to opening hours, meal windows and the pace's day length; then a
   2-opt pass removes crossing routes when that stays feasible.
2. MATERIALISE: real legs from the routes service (mock or Google, with
   traffic) replace the estimates; meals, rests and costs are attached. A stop
   that no longer fits after real travel times is dropped and reported.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from app.core.geo import haversine_km
from app.core.timeutil import hm_to_min, min_to_hm, period_of
from app.engines import budget as budget_engine
from app.engines.food import FoodEngine
from app.engines.pace import DINNER_WINDOW, LUNCH_WINDOW
from app.engines.recommendation import ScoringContext, open_day_ratio, score_attraction
from app.engines.transport import TransportEngine
from app.schemas.common import DataSource, LatLng
from app.schemas.itinerary import DayPlan, ItemType, ItineraryItem, UnscheduledPlace
from app.schemas.place import Place, PlaceKind, SuitabilityScore

log = logging.getLogger(__name__)
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MIN_SCORE = 1.5
MIN_EXTERNAL_RATING = 3.3
MAX_WAIT_MIN = 60
DEFAULT_HOURS = (9 * 60, 18 * 60)   # assumed when the provider has no opening hours


@dataclass
class Candidate:
    place: Place
    score: SuitabilityScore

    @property
    def loc(self) -> LatLng:
        return self.place.location


@dataclass
class PlanConstraints:
    """Tightened by the budget optimiser."""
    max_entry_fee_pp: float | None = None
    max_meal_cost_pp: float | None = None
    max_activities: int | None = None


@dataclass
class PlanResult:
    days: list[DayPlan]
    unscheduled: list[UnscheduledPlace]
    spare: list[Candidate]
    warnings: list[str] = field(default_factory=list)


def open_window(place: Place, weekday: int, arrive: int, duration: int) -> tuple[int, int] | None:
    """Earliest (start, end) on `weekday` at/after `arrive` that fits `duration`, or None."""
    oh = place.opening_hours
    ranges: list[tuple[int, int]]
    if oh is None or not oh.known:
        ranges = [DEFAULT_HOURS]
    else:
        ranges = [(hm_to_min(r.open), hm_to_min(r.close)) for r in oh.weekly.get(weekday, [])]
    for o, c in sorted(ranges):
        start = max(arrive, o)
        if start + duration <= c:
            return start, start + duration
    return None


def rank_attractions(places: list[Place], ctx: ScoringContext, constraints: PlanConstraints) -> tuple[list[Candidate], list[UnscheduledPlace]]:
    ranked: list[Candidate] = []
    rejected: list[UnscheduledPlace] = []
    for p in places:
        if open_day_ratio(p, ctx.weekdays) == 0:
            rejected.append(UnscheduledPlace(place=p, reason="Closed on all days of your trip"))
            continue
        er = p.external_rating
        if er and er.rating is not None and er.rating < MIN_EXTERNAL_RATING and (er.review_count or 0) >= 20:
            rejected.append(UnscheduledPlace(place=p, reason=f"Low {er.provider.value} rating ({er.rating})"))
            continue
        if constraints.max_entry_fee_pp is not None and p.entry_fee and p.entry_fee.amount > constraints.max_entry_fee_pp:
            rejected.append(UnscheduledPlace(place=p, reason="Entry fee above the budget-fit limit"))
            continue
        s = score_attraction(p, ctx)
        if s.score < MIN_SCORE:
            rejected.append(UnscheduledPlace(place=p, reason=f"Low suitability for you ({s.score}/5)"))
            continue
        ranked.append(Candidate(p, s))
    ranked.sort(key=lambda c: (-c.score.score, c.place.name))
    return ranked, rejected


class ItineraryEngine:
    def __init__(self, ctx: ScoringContext, accommodation: Place, transport: TransportEngine, food: FoodEngine,
                 data_source: DataSource, constraints: PlanConstraints | None = None):
        self.ctx = ctx
        self.req = ctx.req
        self.pace = ctx.pace
        self.home = accommodation
        self.transport = transport
        self.food = food
        self.source = data_source
        self.c = constraints or PlanConstraints()
        self.max_acts = min(self.pace.max_activities, self.c.max_activities or 99)

    # ------------------------------------------------------------------ planning
    def _latest_activity_end(self) -> int:
        # leave time for dinner and the trip back before the pace's day end
        return self.pace.day_end - self.pace.dinner_min - 30

    def _simulate(self, seq: list[Candidate], weekday: int) -> tuple[bool, float]:
        """Quick feasibility check of an ordered sequence. Returns (feasible, travel minutes)."""
        t = self.pace.day_start + self.pace.breakfast_min + 10
        loc = self.home.location
        lunch = False
        travel_total = 0.0
        for c in seq:
            if not lunch and t >= LUNCH_WINDOW[0]:
                t += self.pace.lunch_min + self.pace.rest_after_lunch + 10
                lunch = True
            travel = self.transport.quick_minutes(loc, c.loc)
            travel_total += travel
            w = open_window(c.place, weekday, int(t + travel + self.pace.buffer_min), c.place.typical_visit_minutes)
            if w is None or w[0] - (t + travel) > MAX_WAIT_MIN or w[1] > self._latest_activity_end():
                return False, travel_total
            if not lunch and w[1] > LUNCH_WINDOW[1] + 30:
                return False, travel_total
            t, loc = w[1], c.loc
        travel_total += self.transport.quick_minutes(loc, self.home.location)
        return True, travel_total

    def _plan_day(self, weekday: int, pool: list[Candidate], used: set[str], want_park: bool) -> list[Candidate]:
        t = self.pace.day_start + self.pace.breakfast_min + 10
        loc = self.home.location
        lunch = False
        seq: list[Candidate] = []
        # Day anchor: the best remaining place open today. The day is built around it so
        # high-value but distant sights (e.g. a hill fort) are not crowded out by nearby ones.
        open_today = [c for c in pool if c.place.id not in used
                      and open_window(c.place, weekday, 0, c.place.typical_visit_minutes) is not None]
        # Anchor = best place ignoring distance (the day travels to it); famous and longer
        # (major) sights make better anchors than quick photo stops.
        def anchor_key(c: Candidate) -> float:
            dist_neutral = c.score.score + 5 * c.score.weights["distance"] * (1 - c.score.components["distance"])
            return dist_neutral + (0.5 if c.place.is_famous else 0) + c.place.typical_visit_minutes / 300

        anchor = max(open_today, key=anchor_key, default=None)
        while len(seq) < self.max_acts:
            if not lunch and t >= LUNCH_WINDOW[0]:
                t += self.pace.lunch_min + self.pace.rest_after_lunch + 10
                lunch = True
            best: tuple[float, Candidate, tuple[int, int]] | None = None
            for c in pool:
                if c.place.id in used:
                    continue
                travel = self.transport.quick_minutes(loc, c.loc)
                arrive = int(t + travel + self.pace.buffer_min)
                w = open_window(c.place, weekday, arrive, c.place.typical_visit_minutes)
                if w is None or w[1] > self._latest_activity_end():
                    continue
                wait = w[0] - arrive
                if wait > MAX_WAIT_MIN:
                    continue
                if not lunch and w[1] > LUNCH_WINDOW[1] + 30 and w[0] < LUNCH_WINDOW[0]:
                    continue  # would swallow lunch time
                travel_weight = 0.25 if not seq else 0.6
                u = c.score.score / 5 - travel_weight * travel / 60 - 0.3 * wait / 60
                if anchor is not None:
                    if c is anchor:
                        u += 0.6
                    elif anchor in seq:
                        u -= 0.04 * haversine_km(c.loc.lat, c.loc.lng, anchor.loc.lat, anchor.loc.lng)
                if period_of(w[0]) in c.place.best_time:
                    u += 0.1
                if want_park and c.place.kind == PlaceKind.PARK and not any(s.place.kind == PlaceKind.PARK for s in seq):
                    u += 0.08
                if seq and set(c.place.categories[:2]) == set(seq[-1].place.categories[:2]):
                    u -= 0.05  # variety
                if best is None or u > best[0]:
                    best = (u, c, w)
            if best is None:
                break
            _, c, w = best
            seq.append(c)
            used.add(c.place.id)
            t, loc = w[1], c.loc
        return self._two_opt(seq, weekday)

    def _two_opt(self, seq: list[Candidate], weekday: int) -> list[Candidate]:
        if len(seq) < 3:
            return seq
        ok, best_cost = self._simulate(seq, weekday)
        if not ok:
            return seq
        improved = True
        while improved:
            improved = False
            for i in range(len(seq) - 1):
                for j in range(i + 1, len(seq)):
                    cand = seq[:i] + seq[i:j + 1][::-1] + seq[j + 1:]
                    feasible, cost = self._simulate(cand, weekday)
                    if feasible and cost < best_cost - 1:
                        seq, best_cost, improved = cand, cost, True
        return seq

    # -------------------------------------------------------------- materialise
    def _dt(self, date: dt.date, minute: int) -> dt.datetime:
        minute = max(0, min(int(minute), 23 * 60 + 59))
        return dt.datetime.combine(date, dt.time(minute // 60, minute % 60))

    def _materialise(self, day_number: int, date: dt.date, seq: list[Candidate], used_food: set[str],
                     dropped: list[UnscheduledPlace]) -> DayPlan:
        weekday = date.weekday()
        items: list[ItineraryItem] = []
        warnings: list[str] = []
        state = {"t": self.pace.day_start, "loc": self.home.location, "name": self.home.name, "n": 0}

        def add(item_type: ItemType, title: str, start: int, end: int, **kw) -> ItineraryItem:
            state["n"] += 1
            it = ItineraryItem(id=f"d{day_number}-{state['n']}", type=item_type, period=period_of(start),
                               start=min_to_hm(start), end=min_to_hm(end), duration_min=int(end - start),
                               title=title, **kw)
            items.append(it)
            return it

        def travel_to(name: str, loc: LatLng) -> None:
            if haversine_km(state["loc"].lat, state["loc"].lng, loc.lat, loc.lng) < 0.05:
                state["loc"], state["name"] = loc, name
                return
            leg = self.transport.build_leg(state["name"], name, state["loc"], loc, self._dt(date, state["t"]))
            start = state["t"]
            end = start + leg.chosen.duration_min
            add(ItemType.TRAVEL, f"{leg.chosen.mode.value.replace('_', ' ').title()} to {name}", int(start),
                int(round(end)), travel=leg, cost=leg.chosen.cost)
            state["t"] = end + min(self.pace.buffer_min, max(2.0, leg.chosen.duration_min / 2))
            state["loc"], state["name"] = loc, name

        def meal(kind: str, duration: int) -> None:
            radius = 1.5 if kind == "breakfast" else 3.0
            pick = self.food.pick(kind, state["loc"], int(state["t"] + 10), weekday, used_food, max_km=radius,
                                  max_cost=self.c.max_meal_cost_pp, duration=duration)
            if pick is None:
                pick = self.food.pick(kind, state["loc"], int(state["t"] + 10), weekday, set(), max_km=radius,
                                      max_cost=self.c.max_meal_cost_pp, duration=duration)
            if pick is None:
                cost = budget_engine.meal_cost(None, kind, self.req)
                label = "at your accommodation" if state["name"] == self.home.name else f"near {state['name']}"
                add(ItemType.MEAL, f"{kind.title()} {label}", int(state["t"]), int(state["t"] + duration),
                    meal_type=kind, cost=cost,
                    notes=["No restaurant matching your food preferences was found nearby - cost is an estimate."])
                state["t"] += duration
                return
            cand, score = pick
            used_food.add(cand.place.id)
            travel_to(cand.place.name, cand.place.location)
            add(ItemType.MEAL, f"{kind.title()} at {cand.place.name}", int(state["t"]), int(state["t"] + duration),
                place=cand.place, suitability=score, meal_type=kind,
                cost=budget_engine.meal_cost(cand.place, kind, self.req),
                notes=[f"Diet info: {cand.check.confidence}"] + (cand.check.reasons[:2]))
            state["t"] += duration

        add(ItemType.START, f"Start at {self.home.name}", self.pace.day_start, self.pace.day_start, place=self.home)
        meal("breakfast", self.pace.breakfast_min)
        lunch_done = False

        def maybe_lunch(force: bool = False) -> None:
            nonlocal lunch_done
            if lunch_done or not (force or state["t"] >= LUNCH_WINDOW[0]):
                return
            meal("lunch", self.pace.lunch_min)
            lunch_done = True
            if self.pace.rest_after_lunch > 0:
                self._rest(add, state, weekday, used_food)

        for c in seq:
            maybe_lunch()
            prev = (state["t"], state["loc"], state["name"], len(items))
            travel_to(c.place.name, c.loc)
            w = open_window(c.place, weekday, int(state["t"]), c.place.typical_visit_minutes)
            if w is None or w[0] - state["t"] > MAX_WAIT_MIN or w[1] > self._latest_activity_end():
                # does not fit with real travel times: roll back the leg and report it
                state["t"], state["loc"], state["name"] = prev[0], prev[1], prev[2]
                del items[prev[3]:]
                dropped.append(UnscheduledPlace(place=c.place, reason="Did not fit after real travel times / opening hours"))
                continue
            if w[0] - state["t"] >= 10:
                add(ItemType.REST, f"Wait for {c.place.name} to open", int(state["t"]), w[0],
                    notes=["Short break before opening time"])
            notes = []
            if c.place.opening_hours is None or not c.place.opening_hours.known:
                notes.append("Opening hours not published - assumed 09:00-18:00, please verify.")
            if c.score.discovery:
                notes.append("Suggested beyond your interests: a well-known sight worth seeing.")
            add(ItemType.ACTIVITY, c.place.name, w[0], w[1], place=c.place, suitability=c.score,
                cost=budget_engine.entry_cost(c.place, self.req), notes=notes)
            state["t"] = w[1]

        maybe_lunch(force=True)
        if state["t"] < DINNER_WINDOW[0] - 45:
            free_start = int(state["t"])
            add(ItemType.REST, "Free time / relax", free_start, DINNER_WINDOW[0] - 15,
                notes=["Unplanned time for shopping, a cafe stop or rest at your accommodation."])
            state["t"] = DINNER_WINDOW[0] - 15
        meal("dinner", self.pace.dinner_min)

        if self.req.return_to_accommodation:
            travel_to(self.home.name, self.home.location)
        add(ItemType.END, f"Back at {self.home.name}" if self.req.return_to_accommodation else "End of day",
            int(state["t"]), int(state["t"]), place=self.home if self.req.return_to_accommodation else None)
        if state["t"] > self.pace.day_end + 30:
            warnings.append(f"Day ends late ({min_to_hm(int(state['t']))}); consider removing an activity.")
        if not any(i.type == ItemType.ACTIVITY for i in items):
            warnings.append("No attractions could be scheduled for this day.")

        db = budget_engine.day_budget(day_number, items)
        return DayPlan(day_number=day_number, date=date, weekday=WEEKDAYS[weekday], items=items, budget=db,
                       warnings=warnings)

    def _rest(self, add, state, weekday: int, used_food: set[str]) -> None:
        """Post-lunch rest: a nearby open park if there is one, otherwise a plain break."""
        dur = self.pace.rest_after_lunch
        t = int(state["t"])
        parks = [p for p in self._parks
                 if p.id not in self._used_parks
                 and haversine_km(state["loc"].lat, state["loc"].lng, p.location.lat, p.location.lng) < 1.5
                 and open_window(p, weekday, t + 15, dur) is not None]
        if parks:
            park = min(parks, key=lambda p: haversine_km(state["loc"].lat, state["loc"].lng, p.location.lat, p.location.lng))
            self._used_parks.add(park.id)
            add(ItemType.REST, f"Rest at {park.name}", t, t + dur, place=park,
                cost=budget_engine.entry_cost(park, self.req), notes=["Relaxed break in a nearby park or garden"])
        else:
            add(ItemType.REST, "Rest break", t, t + dur, notes=["Break after lunch - a cafe or shaded spot nearby"])
        state["t"] = t + dur

    # ------------------------------------------------------------------- public
    def build(self, attractions: list[Place]) -> PlanResult:
        ranked, rejected = rank_attractions(attractions, self.ctx, self.c)
        self._parks = [c.place for c in ranked if c.place.kind == PlaceKind.PARK]
        self._used_parks: set[str] = set()
        used: set[str] = set()
        used_food: set[str] = set()
        dropped: list[UnscheduledPlace] = []
        days: list[DayPlan] = []
        start = self.req.effective_start_date
        want_park = self.req.pace.value != "packed"
        for i in range(self.req.num_days):
            date = start + dt.timedelta(days=i)
            seq = self._plan_day(date.weekday(), ranked, used, want_park)
            for c in seq:
                self._used_parks.add(c.place.id)
            days.append(self._materialise(i + 1, date, seq, used_food, dropped))

        scheduled = {it.place.id for d in days for it in d.items if it.place}
        spare = [c for c in ranked if c.place.id not in scheduled]
        unscheduled: list[UnscheduledPlace] = []
        seen: set[str] = set()
        for u in dropped + [UnscheduledPlace(place=c.place, reason="Good match but did not fit in your days")
                            for c in spare[:8]] + rejected[:5]:
            if u.place.id not in seen and u.place.id not in scheduled:
                seen.add(u.place.id)
                unscheduled.append(u)
        warnings = []
        if not ranked:
            warnings.append("No attractions matched your preferences and constraints.")
        return PlanResult(days=days, unscheduled=unscheduled, spare=spare, warnings=warnings)


def accommodation_place(name: str, loc: LatLng, address: str, source: DataSource, kind_label: str) -> Place:
    return Place(id="accommodation", name=name, kind=PlaceKind.ACCOMMODATION, location=loc, address=address,
                 description=f"Your {kind_label.replace('_', ' ')}", source=source)
