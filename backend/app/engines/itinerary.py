"""Itinerary engine: selects, orders and schedules places into day plans.

Two passes per day:
1. PLAN (cheap): a route search on a graph whose nodes are the day's candidate places and the accommodation and
   whose edges are estimated travel times. Each stop is worth
       suitability - travel penalty - waiting penalty + time-of-day fit (+ notability, must-see, anchor)
   and a route must respect opening hours, the lunch window and the pace's day length. A beam search keeps the
   best partial routes at each step (keeping one is exactly the old greedy choice, which is always tried too, so
   on this measure the search can only match or beat it). The wider search pads each leg (SEARCH_PAD), because its
   tighter routes would otherwise break once real travel and meal detours are known. A 2-opt pass then removes
   crossings when that stays feasible.
2. MATERIALISE: real legs from the routes service (mock or Google, with
   traffic) replace the estimates; meals, rests and costs are attached. A stop
   that no longer fits after real travel times is dropped and reported.
"""
from __future__ import annotations

import datetime as dt
import heapq
import math
import re
from dataclasses import dataclass, field

from app.core.geo import haversine_km
from app.core.timeutil import hm_to_min, min_to_hm, period_of
from app.engines import budget as budget_engine
from app.engines.food import FoodEngine, is_open_for
from app.engines.pace import DINNER_WINDOW, LUNCH_WINDOW
from app.engines.quality import is_minor_park, looks_like_sight, notability, reader_share
from app.engines.recommendation import ScoringContext, open_day_ratio, score_attraction
from app.engines.transport import TransportEngine
from app.schemas.common import DataSource, LatLng
from app.schemas.itinerary import DayPlan, ItemType, ItineraryItem, UnscheduledPlace
from app.schemas.place import Place, PlaceKind, SuitabilityScore

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MIN_SCORE = 1.5
MIN_EXTERNAL_RATING = 3.3
MAX_WAIT_MIN = 60
NOTABLE_BONUS = 0.5    # up to this much utility for a place the open data knows well (Wikidata, two sources)
READERS_BONUS = 0.6    # up to this much more for a place many people read about on Wikipedia (reader_share)
MINOR_PARKS_PER_DAY = 1  # neighbourhood and sector parks: one a day at most, so a day is not five parks
MUST_SEE_BONUS = 3.0   # outweighs any score and any sensible detour, so a must-see is placed first
FAR_FROM_HOME_MIN = 40   # beyond this, dinner is taken near the accommodation, not by the last sight
LUNCH_BY = LUNCH_WINDOW[1]                # with lunch still to come, a sight must end by this time
LATEST_LUNCH_START = LUNCH_WINDOW[1] + 30  # so lunch starts by this, after the walk or ride to the restaurant
EARLY_LUNCH = LUNCH_WINDOW[0] - 60        # lunch may move this early to make room for a long sight
DEFAULT_HOURS = (9 * 60, 18 * 60)   # assumed when the provider has no opening hours
SEARCH_POOL = 16    # places a day's route search considers: the greedy route's, must-sees, the anchor, the best others
SEARCH_WIDTH = 16   # partial routes kept at each step of the search
SEARCH_PAD = 10     # minutes of slack per leg in the wider search: its routes are tighter than the greedy one's
ANCHOR_WEIGHT = 1.5   # a day's route that includes its anchor (its main sight) is worth this much more
# the search's route replaces the greedy one only when it is clearly better (about another stop, or a much better
# one): a near tie can swap a famous sight for two minor ones, which is no gain to the traveller
SEARCH_MARGIN = 0.3


@dataclass
class Candidate:
    place: Place
    score: SuitabilityScore

    @property
    def loc(self) -> LatLng:
        return self.place.location


@dataclass(slots=True)
class _Node:
    """A place as a node of one day's planning graph, with everything a search step needs worked out once."""
    c: Candidate
    id: str
    loc: LatLng
    base: float          # what the visit is worth before travel, waiting and order are counted
    minutes: int         # length of the visit
    ranges: list[tuple[int, int]]   # opening ranges that day
    latest: int          # the latest the visit may end
    minor: bool          # a minor park (MINOR_PARKS_PER_DAY)
    must: bool
    park: bool
    anchor: bool
    anchor_km: float     # distance to the day's anchor
    cats: frozenset[str]
    best_time: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Route:
    """A partial day route in the planning search: the stops so far, where and when it ends, and its value."""
    seq: tuple[_Node, ...]
    t: float
    loc: LatLng
    lunch: bool
    value: float
    ids: frozenset[str]
    minor: int = 0       # minor parks so far
    musts: int = 0       # must-sees so far
    park: bool = False   # a park is in the route
    anchored: bool = False   # the anchor is in the route


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


def day_ranges(place: Place, weekday: int) -> list[tuple[int, int]]:
    """Opening ranges on `weekday` in minutes, sorted; the assumed default when the hours are not known."""
    oh = place.opening_hours
    if oh is None or not oh.known:
        return [DEFAULT_HOURS]
    return sorted((hm_to_min(r.open), hm_to_min(r.close)) for r in oh.weekly.get(weekday, []))


def fit_window(ranges: list[tuple[int, int]], arrive: int, duration: int) -> tuple[int, int] | None:
    for o, c in ranges:
        start = max(arrive, o)
        if start + duration <= c:
            return start, start + duration
    return None


def open_window(place: Place, weekday: int, arrive: int, duration: int) -> tuple[int, int] | None:
    """Earliest (start, end) on `weekday` at/after `arrive` that fits `duration`, or None."""
    return fit_window(day_ranges(place, weekday), arrive, duration)


def rank_attractions(places: list[Place], ctx: ScoringContext, constraints: PlanConstraints) -> tuple[list[Candidate], list[UnscheduledPlace]]:
    ranked: list[Candidate] = []
    rejected: list[UnscheduledPlace] = []
    for p in places:
        if open_day_ratio(p, ctx.weekdays) == 0:
            rejected.append(UnscheduledPlace(place=p, reason="Closed on all days of your trip"))
            continue
        if p.id in ctx.must_see:
            # asked for by name: no rating, fee or score threshold applies; the score is still shown as it is
            s = ctx.attraction_scores.get(p.id) or score_attraction(p, ctx)
            ctx.attraction_scores[p.id] = s
            ranked.append(Candidate(p, s.model_copy(update={"reasons": ["On your must-see list"] + s.reasons})))
            continue
        if not looks_like_sight(p):   # a neighbourhood, junction, shop or rental: not even "also worth considering"
            continue
        er = p.external_rating
        if er and er.rating is not None and er.rating < MIN_EXTERNAL_RATING and (er.review_count or 0) >= 20:
            rejected.append(UnscheduledPlace(place=p, reason=f"Low {er.provider.value} rating ({er.rating})"))
            continue
        if constraints.max_entry_fee_pp is not None and p.entry_fee \
                and ctx.costs.to_trip_currency(p.entry_fee).amount > constraints.max_entry_fee_pp:
            rejected.append(UnscheduledPlace(place=p, reason="Entry fee above the budget-fit limit"))
            continue
        s = ctx.attraction_scores.get(p.id)
        if s is None:
            s = ctx.attraction_scores[p.id] = score_attraction(p, ctx)
        if s.score < MIN_SCORE:
            rejected.append(UnscheduledPlace(place=p, reason=f"Low suitability for you ({s.score}/5)"))
            continue
        ranked.append(Candidate(p, s))
    # must-sees first, so a near-duplicate of one never replaces it
    ranked.sort(key=lambda c: (c.place.id not in ctx.must_see, -c.score.score, c.place.name))
    return _drop_near_duplicates(ranked, keep=ctx.must_see), rejected


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]


def _missed_reason(reason: str) -> str:
    reason = _lower_first(reason)
    return reason if reason.startswith("did not fit") else "did not fit: " + reason


def _stems(name: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]+", name.lower()) if len(w) >= 5}


def _drop_near_duplicates(ranked: list[Candidate], max_m: float = 150, keep: set[str] | frozenset[str] = frozenset()
                          ) -> list[Candidate]:
    """Open data can list one sight twice under different spellings ("Lahori Gate" / "Lahore Gate").
    Keep the better-ranked one when two candidates are this close and share a name stem."""
    kept: list[Candidate] = []
    for c in ranked:
        if c.place.id in keep:   # asked for by the traveller: never folded into another place
            kept.append(c)
            continue
        stems = _stems(c.place.name)
        if any(haversine_km(c.loc.lat, c.loc.lng, k.loc.lat, k.loc.lng) * 1000 <= max_m and stems & _stems(k.place.name)
               for k in kept):
            continue
        kept.append(c)
    return kept


class ItineraryEngine:
    def __init__(self, ctx: ScoringContext, accommodation: Place, transport: TransportEngine, food: FoodEngine,
                 constraints: PlanConstraints | None = None):
        self.ctx = ctx
        self.req = ctx.req
        self.pace = ctx.pace
        self.home = accommodation
        self.transport = transport
        self.food = food
        self.c = constraints or PlanConstraints()
        self.max_acts = min(self.pace.max_activities, self.c.max_activities or 99)
        self.search_width = SEARCH_WIDTH   # 1 gives the plain greedy route (tests compare the two)
        self.search_pad = SEARCH_PAD
        # planning-pass estimates: first activity after breakfast, the lunch + rest block, and the
        # latest activity end that still leaves time for dinner and the trip back
        self.first_activity = self.pace.day_start + self.pace.breakfast_min + 10
        self.lunch_block = self.pace.lunch_min + self.pace.rest_after_lunch + 10
        self.latest_activity_end = self.pace.day_end - self.pace.dinner_min - 30
        self._notability: dict[str, float] = {}
        self._minor_parks: dict[str, bool] = {}
        self._quick: dict[tuple[float, float, float, float], float] = {}   # the graph's edges, filled as needed

    def _minutes(self, a: LatLng, b: LatLng) -> float:
        key = (a.lat, a.lng, b.lat, b.lng)
        m = self._quick.get(key)
        if m is None:
            m = self._quick[key] = self.transport.quick_minutes(a, b)
        return m

    def _notable(self, place: Place) -> float:
        n = self._notability.get(place.id)
        if n is None:
            n = self._notability[place.id] = notability(place)
        return n

    def _minor(self, place: Place) -> bool:
        m = self._minor_parks.get(place.id)
        if m is None:
            m = self._minor_parks[place.id] = is_minor_park(place)
        return m

    def home_minutes(self, loc: LatLng) -> float:
        return self._minutes(loc, self.home.location)

    def latest_end(self, c: Candidate) -> int:
        """Latest a visit here may end. A stay far from the sights gets dinner near the stay (see _materialise),
        so the trip home comes before dinner, and the day must still end by day_end."""
        back = self.home_minutes(c.loc) + self.pace.buffer_min
        if not self.req.return_to_accommodation or back <= FAR_FROM_HOME_MIN:
            return self.latest_activity_end
        return int(self.pace.day_end - self.pace.dinner_min - back - 20)

    # ------------------------------------------------------------------ planning
    def _simulate(self, seq: list[Candidate], weekday: int) -> tuple[bool, float]:
        """Quick feasibility check of an ordered sequence. Returns (feasible, travel minutes)."""
        t = self.first_activity
        loc = self.home.location
        lunch = False
        travel_total = 0.0
        for c in seq:
            if not lunch and t >= LUNCH_WINDOW[0]:
                t += self.lunch_block
                lunch = True
            travel = self._minutes(loc, c.loc)
            travel_total += travel
            w = open_window(c.place, weekday, int(t + travel + self.pace.buffer_min), c.place.typical_visit_minutes)
            if w is None or w[0] - (t + travel) > MAX_WAIT_MIN or w[1] > self.latest_end(c):
                return False, travel_total
            if not lunch and w[1] > LUNCH_WINDOW[1] + 30:
                return False, travel_total
            t, loc = w[1], c.loc
        travel_total += self._minutes(loc, self.home.location)
        return True, travel_total

    def _plan_day(self, weekday: int, pool: list[Candidate], used: set[str], want_park: bool,
                  must_quota: int = 0) -> list[Candidate]:
        """`must_quota`: how many must-see places this day should take, so they spread over the trip."""
        must = self.ctx.must_see
        open_today = [c for c in pool if c.place.id not in used
                      and open_window(c.place, weekday, 0, c.place.typical_visit_minutes) is not None]

        # Day anchor: the best remaining place open today, ignoring distance (the day travels to it). The day is
        # built around it so high-value but distant sights (a hill fort) are not crowded out by nearby ones;
        # famous and longer (major) sights make better anchors than quick photo stops.
        def anchor_key(c: Candidate) -> float:
            dist_neutral = c.score.score + 5 * c.score.weights["distance"] * (1 - c.score.components["distance"])
            return (dist_neutral + (0.5 if c.place.is_famous else 0) + c.place.typical_visit_minutes / 300
                    + self._notable(c.place) + 2 * reader_share(c.place) - (1.0 if self._minor(c.place) else 0.0))

        musts_today = [c for c in open_today if c.place.id in must] if must_quota else []
        anchor = max(musts_today or open_today, key=anchor_key, default=None)
        nodes = [self._node(c, weekday, anchor) for c in open_today]
        # keeping one route per step is the greedy route; its stops seed the graph, so the wider search can't lose it
        greedy = self._search(nodes, 1, must_quota, want_park)
        best = greedy
        if self.search_width > 1:
            wide = self._search(self._search_pool(nodes, greedy, anchor), self.search_width, must_quota, want_park,
                                self.search_pad)
            if self._final(wide) > self._final(greedy) + SEARCH_MARGIN:
                best = wide
        seq = [n.c for n in best.seq]
        used.update(c.place.id for c in seq)
        return self._two_opt(seq, weekday)

    def _node(self, c: Candidate, weekday: int, anchor: Candidate | None) -> _Node:
        p = c.place
        return _Node(
            c=c, id=p.id, loc=c.loc,
            base=c.score.score / 5 + NOTABLE_BONUS * self._notable(p) + READERS_BONUS * reader_share(p),
            minutes=p.typical_visit_minutes, ranges=day_ranges(p, weekday), latest=self.latest_end(c),
            minor=self._minor(p), must=p.id in self.ctx.must_see, park=p.kind == PlaceKind.PARK,
            anchor=c is anchor,
            anchor_km=haversine_km(c.loc.lat, c.loc.lng, anchor.loc.lat, anchor.loc.lng) if anchor else 0.0,
            cats=frozenset(p.categories[:2]), best_time=tuple(p.best_time))

    def _search_pool(self, nodes: list[_Node], greedy: _Route, anchor: Candidate | None) -> list[_Node]:
        """The graph's nodes for one day: the greedy route's stops, the must-sees and the anchor, then the most
        valuable other places, valued by score and notability less the travel from the anchor (or the stay)."""
        hub = anchor.loc if anchor is not None else self.home.location

        def worth(n: _Node) -> float:
            return n.base - 0.6 * self._minutes(hub, n.loc) / 60 - (0.3 if n.minor else 0.0)

        pool = {n.id: n for n in greedy.seq}
        pool.update((n.id, n) for n in nodes if n.must or n.anchor)
        for n in sorted(nodes, key=worth, reverse=True):
            if len(pool) >= SEARCH_POOL:
                break
            pool.setdefault(n.id, n)
        return list(pool.values())

    def _final(self, route: _Route) -> float:
        """A whole day's value: its stops' worth less the trip back to the stay at the end. The day is built
        around its anchor, so a route without it (more small stops nearer the stay) does not win on count alone."""
        back = self._minutes(route.loc, self.home.location) if self.req.return_to_accommodation and route.seq else 0
        return route.value - 0.6 * back / 60 + (ANCHOR_WEIGHT if route.anchored else 0.0)

    def _search(self, nodes: list[_Node], width: int, must_quota: int, want_park: bool, pad: int = 0) -> _Route:
        """Beam search over routes through `nodes`: extend every kept route by every node that still fits, keep
        the `width` most valuable, and return the best whole day seen. Two routes that visit the same places and
        end at the same one leave the same choices open, so only the better of them is kept. `pad` adds minutes
        to every leg and to the start, so a route still fits once real travel times and meal detours are known."""
        start = _Route((), self.first_activity + pad, self.home.location, False, 0.0, frozenset())
        frontier, best = [start], start
        best_value = self._final(start)
        for _ in range(self.max_acts):
            # score every extension first and build routes only for the best few: most are never kept
            moves: list[tuple[float, int, int, _Route, _Node, float, int, bool]] = []
            for route in frontier:
                for n in nodes:
                    if n.id in route.ids:
                        continue
                    gain = self._gain(route, n, must_quota, want_park, pad)
                    if gain is None:
                        continue
                    u, end, lunch = gain
                    rank = route.value + u + (ANCHOR_WEIGHT if route.anchored or n.anchor else 0.0)
                    moves.append((rank, -end, len(moves), route, n, u, end, lunch))
            if not moves:
                break
            frontier, seen = [], set()
            for _rank, _end, _i, route, n, u, end, lunch in heapq.nlargest(2 * width, moves, key=lambda m: m[:3]):
                ids = route.ids | {n.id}
                if (ids, n.id) in seen:   # same places, same last stop: the better-ranked one is already kept
                    continue
                seen.add((ids, n.id))
                frontier.append(_Route(route.seq + (n,), end, n.loc, lunch, route.value + u, ids,
                                       route.minor + n.minor, route.musts + n.must, route.park or n.park,
                                       route.anchored or n.anchor))
                if len(frontier) == width:
                    break
            for r in frontier:
                v = self._final(r)
                if v > best_value + 1e-9:
                    best, best_value = r, v
        return best

    def _gain(self, route: _Route, n: _Node, must_quota: int, want_park: bool, pad: int = 0
              ) -> tuple[float, int, bool] | None:
        """What visiting `n` after `route` is worth, when that visit ends and whether lunch is behind by then; None
        when the visit does not fit (opening hours, a long wait, the end of the day, lunch time, the daily limit
        on minor parks)."""
        t, lunch, seq = route.t, route.lunch, route.seq
        if not lunch and t >= LUNCH_WINDOW[0]:
            t += self.lunch_block
            lunch = True
        if n.minor and not n.must and route.minor >= MINOR_PARKS_PER_DAY:
            return None
        travel = self._minutes(route.loc, n.loc)
        arrive = int(t + travel + self.pace.buffer_min + pad)
        w = fit_window(n.ranges, arrive, n.minutes)
        if w is None or w[1] > n.latest:
            return None
        wait = w[0] - arrive
        if wait > MAX_WAIT_MIN:
            return None
        if not lunch and w[1] > LUNCH_WINDOW[1] + 30 and w[0] < LUNCH_WINDOW[0]:
            return None   # would swallow lunch time
        u = n.base - (0.6 if seq else 0.25) * travel / 60 - 0.3 * wait / 60
        if n.anchor:
            u += 0.6
        elif route.anchored:
            u -= 0.04 * n.anchor_km
        if n.must and route.musts < must_quota:
            u += MUST_SEE_BONUS
        if n.best_time and period_of(w[0]) in n.best_time:
            u += 0.1
        if want_park and n.park and not route.park:
            u += 0.08
        if seq and n.cats == seq[-1].cats:
            u -= 0.05  # variety
        return u, w[1], lunch

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
            pick = None
            # places that are open when we set off, but shut before the meal would end once travel is counted
            closing: set[str] = set()
            for _ in range(4):
                # prefer a restaurant not used yet; repeat one if needed
                for exclude in (used_food | closing, closing):
                    pick = self.food.pick(kind, state["loc"], int(state["t"] + 10), weekday, exclude, max_km=radius,
                                          max_cost=self.c.max_meal_cost_pp, duration=duration)
                    if pick is not None:
                        break
                if pick is None:
                    break
                there = pick[0].place
                arrive = state["t"] + self.transport.quick_minutes(state["loc"], there.location) + self.pace.buffer_min
                if is_open_for(there, weekday, int(arrive), duration):
                    break
                closing.add(there.id)
                pick = None
            if pick is None:
                cost = budget_engine.meal_cost(None, kind, self.req, self.ctx.costs)
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
                cost=budget_engine.meal_cost(cand.place, kind, self.req, self.ctx.costs),
                notes=[f"Diet info: {cand.check.confidence}"] + cand.check.reasons[:2])
            state["t"] += duration

        add(ItemType.START, f"Start at {self.home.name}", self.pace.day_start, self.pace.day_start, place=self.home)
        meal("breakfast", self.pace.breakfast_min)
        lunch_done = False

        def maybe_lunch(force: bool = False, earliest: int = LUNCH_WINDOW[0]) -> None:
            nonlocal lunch_done
            if lunch_done or not (force or state["t"] >= earliest):
                return
            if state["t"] < earliest:   # a day with nothing left to see: lunch still waits for lunchtime
                add(ItemType.REST, "Free time", int(state["t"]), earliest,
                    notes=["Nothing is planned for this part of the day."])
                state["t"] = earliest
            meal("lunch", self.pace.lunch_min)
            lunch_done = True
            if self.pace.rest_after_lunch > 0:
                self._rest(add, state, weekday, travel_to)

        def visit(c: Candidate) -> str:
            """Travel to a sight and add the visit: 'ok', 'nofit' (opening hours or the end of the day), or
            'lunch' (it would end after LUNCH_BY with lunch still to come). Anything but 'ok' is rolled back."""
            prev = (state["t"], state["loc"], state["name"], len(items))
            travel_to(c.place.name, c.loc)
            w = open_window(c.place, weekday, int(state["t"]), c.place.typical_visit_minutes)
            result = "ok"
            if w is None or w[0] - state["t"] > MAX_WAIT_MIN or w[1] > self.latest_end(c):
                result = "nofit"
            elif not lunch_done and (w[1] > LUNCH_BY
                                     or (prev[0] >= LUNCH_WINDOW[0] - 30 and w[1] > LUNCH_WINDOW[0] + 60)):
                # it would end after LUNCH_BY, or it is nearly lunchtime and this visit would run well into it
                result = "lunch"
            if result != "ok":
                state["t"], state["loc"], state["name"] = prev[0], prev[1], prev[2]
                del items[prev[3]:]
                return result
            if w[0] - state["t"] >= 10:
                add(ItemType.REST, f"Wait for {c.place.name} to open", int(state["t"]), w[0],
                    notes=["Short break before opening time"])
            notes = []
            if c.place.opening_hours is None or not c.place.opening_hours.known:
                notes.append("Opening hours not published - assumed 09:00-18:00, please verify.")
            if c.score.discovery:
                notes.append("Suggested beyond your interests: a well-known sight worth seeing.")
            add(ItemType.ACTIVITY, c.place.name, w[0], w[1], place=c.place, suitability=c.score,
                cost=budget_engine.entry_cost(c.place, self.req, self.ctx.costs), notes=notes)
            state["t"] = w[1]
            return "ok"

        for c in seq:
            maybe_lunch()
            result = visit(c)
            if result == "lunch" and state["t"] >= EARLY_LUNCH:
                maybe_lunch(force=True, earliest=EARLY_LUNCH)   # an early lunch first, then the long visit
                result = visit(c)
            if result != "ok":
                why = ("Would have pushed lunch past "
                       f"{min_to_hm(LUNCH_BY)}" if result == "lunch"
                       else "Did not fit after real travel times / opening hours")
                dropped.append(UnscheduledPlace(place=c.place, reason=why))

        maybe_lunch(force=True)
        # far from the stay: go back first and have dinner nearby, so the evening does not end with a long ride
        far = self.req.return_to_accommodation and self.home_minutes(state["loc"]) > FAR_FROM_HOME_MIN
        if far:
            travel_to(self.home.name, self.home.location)
        if state["t"] < DINNER_WINDOW[0] - 45:
            add(ItemType.REST, "Free time / relax", int(state["t"]), DINNER_WINDOW[0] - 15,
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
            warnings.append(f"No attractions could be scheduled for day {day_number}.")

        db = budget_engine.day_budget(day_number, items)
        return DayPlan(day_number=day_number, date=date, weekday=WEEKDAYS[weekday], items=items, budget=db,
                       warnings=warnings)

    def _rest(self, add, state, weekday: int, travel_to) -> None:
        """Post-lunch rest: a nearby open park if there is one (with the walk or ride there), otherwise a plain
        break."""
        dur = self.pace.rest_after_lunch
        here = state["loc"]

        def km(p: Place) -> float:
            return haversine_km(here.lat, here.lng, p.location.lat, p.location.lng)

        def open_on_arrival(p: Place) -> bool:
            arrive = state["t"] + self.transport.quick_minutes(here, p.location) + self.pace.buffer_min
            return open_window(p, weekday, int(arrive), dur) is not None

        parks = [p for p in self._parks
                 if p.id not in self._used_parks and p.id not in self._visited and km(p) < 1.5 and open_on_arrival(p)]
        if parks:
            park = min(parks, key=km)
            self._used_parks.add(park.id)
            self._visited.add(park.id)   # a park rested in is not offered again as a sight on a later day
            travel_to(park.name, park.location)
            t = int(state["t"])
            add(ItemType.REST, f"Rest at {park.name}", t, t + dur, place=park,
                cost=budget_engine.entry_cost(park, self.req, self.ctx.costs),
                notes=["Relaxed break in a nearby park or garden"])
        else:
            t = int(state["t"])
            add(ItemType.REST, "Rest break", t, t + dur, notes=["Break after lunch - a cafe or shaded spot nearby"])
        state["t"] = t + dur

    # ------------------------------------------------------------------- public
    def build(self, attractions: list[Place]) -> PlanResult:
        ranked, rejected = rank_attractions(attractions, self.ctx, self.c)
        self._parks = [c.place for c in ranked if c.place.kind == PlaceKind.PARK and c.place.id not in self.ctx.must_see]
        self._used_parks: set[str] = set()
        used: set[str] = set()
        self._visited = used
        used_food: set[str] = set()
        dropped: list[UnscheduledPlace] = []
        days: list[DayPlan] = []
        start = self.req.effective_start_date
        want_park = self.req.pace.value != "packed"
        must = self.ctx.must_see
        for i in range(self.req.num_days):
            date = start + dt.timedelta(days=i)
            left = sum(c.place.id in must and c.place.id not in used for c in ranked)
            quota = math.ceil(left / (self.req.num_days - i)) if left else 0
            seq = self._plan_day(date.weekday(), ranked, used, want_park, quota)
            for c in seq:
                self._used_parks.add(c.place.id)
            before = len(dropped)
            days.append(self._materialise(i + 1, date, seq, used_food, dropped))
            for u in dropped[before:]:
                if u.place.id in must:
                    used.discard(u.place.id)

        scheduled = {it.place.id for d in days for it in d.items if it.place}
        spare = [c for c in ranked if c.place.id not in scheduled]
        unscheduled: list[UnscheduledPlace] = []
        seen: set[str] = set()
        warnings: list[str] = []
        # a must-see that is not in the plan is always reported, first, with the reason
        why = {u.place.id: u.reason for u in dropped}
        no_slot = "no free time on a day when it is open"
        missed = [(c.place, _missed_reason(why.get(c.place.id, no_slot)))
                  for c in ranked if c.place.id in must and c.place.id not in scheduled]
        missed += [(u.place, "is " + _lower_first(u.reason)) for u in rejected if u.place.id in must]
        for place, reason in missed:
            unscheduled.append(UnscheduledPlace(place=place, reason=f"On your must-see list, but {reason}"))
            warnings.append(f"{place.name} is on your must-see list but {reason}.")
            seen.add(place.id)
        for u in dropped + [UnscheduledPlace(place=c.place, reason="Good match but did not fit in your days")
                            for c in spare[:8]] + rejected[:5]:
            if u.place.id not in seen and u.place.id not in scheduled:
                seen.add(u.place.id)
                unscheduled.append(u)
        if not ranked:
            warnings.append("No attractions matched your preferences and constraints.")
        return PlanResult(days=days, unscheduled=unscheduled, spare=spare, warnings=warnings)


def accommodation_place(name: str, loc: LatLng, address: str, source: DataSource, kind_label: str) -> Place:
    return Place(id="accommodation", name=name, kind=PlaceKind.ACCOMMODATION, location=loc, address=address,
                 description=f"Your {kind_label.replace('_', ' ')}", source=source)
