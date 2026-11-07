"""Orchestrates a trip: geocode -> discover -> score -> schedule -> budget -> enrich -> (optional) AI."""
from __future__ import annotations

import datetime as dt
import logging

from app.core.config import DataMode, Settings
from app.core.errors import UnsupportedInMockModeError
from app.core.timeutil import hm_to_min
from app.engines import budget as budget_engine
from app.engines.costs import CostModel
from app.engines.food import FoodEngine, _dish_allowed, city_popular_dishes
from app.engines.itinerary import ItineraryEngine, PlanConstraints, PlanResult, accommodation_place
from app.engines.pace import profile_for
from app.engines.recommendation import ScoringContext
from app.engines.transport import TransportEngine, TransportWeights
from app.providers.base import CityContext
from app.schemas.common import DataSource
from app.schemas.itinerary import DayPlan, DishSuggestion, Itinerary, ItemType, ItineraryItem
from app.schemas.place import Place
from app.schemas.trip import TripRequest
from app.nlp.interests import expand_interests, interest_phrase
from app.nlp.semantic import strength
from app.services import ai_service
from app.services.fx_service import FxService
from app.services.geocoding_service import GeocodingService
from app.services.places_service import PlacesService
from app.services.providers import ProviderBundle
from app.services.routes_service import RoutesService

log = logging.getLogger(__name__)

# Successive tightening steps used when fit_to_budget=True and the plan is over budget.
BUDGET_STEPS = [
    ("Prefer cheaper transport and restaurants", dict(cost_weight=0.45, meal_factor=1.2, fee_factor=None, drop=0)),
    ("Skip attractions with high entry fees", dict(cost_weight=0.5, meal_factor=1.0, fee_factor=1.0, drop=0)),
    ("Plan one activity fewer per day and favour free sights", dict(cost_weight=0.55, meal_factor=0.8, fee_factor=0.5, drop=1)),
]


def place_text(p: Place) -> str:
    cats = " ".join(c.replace("_", " ") for c in p.categories if not c.startswith("search:"))
    desc = p.description if p.description and not p.description.startswith("http") else ""
    return f"{p.name}. {desc}. {cats}".strip()


def semantic_interest_matches(semantic, interests: list[str], places: list[Place]) -> dict[str, dict[str, float]]:
    """{place_id: {interest: strength 0..1}} using sentence embeddings (only non-zero strengths kept)."""
    try:
        sims = semantic.similarity([interest_phrase(i) for i in interests], [place_text(p) for p in places])
    except Exception as exc:  # model failure -> lexical matching only
        log.warning("Semantic matching failed: %s", exc)
        return {}
    out: dict[str, dict[str, float]] = {}
    for qi, interest in enumerate(interests):
        for pi, p in enumerate(places):
            s = strength(float(sims[qi, pi]))
            if s > 0:
                out.setdefault(p.id, {})[interest] = round(s, 3)
    return out


class ItineraryService:
    def __init__(self, providers: ProviderBundle, settings: Settings, fx: FxService | None = None,
                 semantic=None):
        self.providers = providers
        self.settings = settings
        self.semantic = semantic   # SemanticMatcher or None (lexical matching only)
        self.places = PlacesService(providers.places)
        self.geo = GeocodingService(providers.geocoding)
        self.routes = RoutesService(providers.routes)
        self.fx = fx or FxService(settings.fx_url)
        self._cities: dict[str, CityContext] = {}

    @property
    def source(self) -> DataSource:
        return self.providers.source

    def city(self, name: str) -> CityContext:
        key = name.strip().lower()
        if key not in self._cities:
            self._cities[key] = self.geo.resolve_city(name)
        return self._cities[key]

    def costs_for(self, req: TripRequest, city: CityContext) -> CostModel:
        if self.providers.mode == DataMode.MOCK:
            return CostModel.build("IN", "INR")
        return CostModel.build(city.country_code, req.currency, self.fx)

    def transport_for(self, req: TripRequest, city: CityContext, weights: TransportWeights | None = None,
                      costs: CostModel | None = None) -> TransportEngine:
        return TransportEngine(self.routes, city, req, profile_for(req.pace), weights,
                               costs or self.costs_for(req, city))

    def _validate_mode(self, req: TripRequest) -> None:
        if self.providers.mode == DataMode.MOCK and req.currency != "INR":
            raise UnsupportedInMockModeError("The mock dataset is priced in INR; choose INR or switch DATA_MODE=open.")

    # ------------------------------------------------------------------ generate
    def generate(self, req: TripRequest) -> Itinerary:
        self._validate_mode(req)
        warnings: list[str] = []
        city = self.city(req.destination_city)
        city_data = self.providers.extras["cities"].get(city) if "cities" in self.providers.extras else None
        if city_data:
            warnings += city_data.warnings
        acc, acc_warn = self.geo.resolve_accommodation(req.accommodation, city)
        warnings += acc_warn
        home = accommodation_place(req.accommodation.name_or_address, acc.location, acc.formatted_address,
                                   acc.source, req.accommodation.type.value)
        start = req.effective_start_date
        weekdays = [(start + dt.timedelta(days=i)).weekday() for i in range(req.num_days)]
        costs = self.costs_for(req, city)
        warnings += costs.notes
        ctx = ScoringContext(req=req, origin=home.location, weekdays=weekdays, costs=costs)

        # NLP: typo-correct and expand interests ("musuems" -> museums, "temples" -> religious sites)
        expanded, corrections = expand_interests(req.interests)
        for raw, fixed in corrections.items():
            warnings.append(f"Interpreted interest '{raw.replace('_', ' ')}' as '{fixed.replace('_', ' ')}'.")
        ctx.interests = expanded
        search_req = req.model_copy(update={"interests": expanded})

        attractions = self.places.attraction_candidates(city, search_req)[: self.settings.max_candidate_places]
        food_places = self.places.food_candidates(city, req, self.settings.max_food_candidates)
        log.info("Planning %s: %d attraction and %d food candidates (%s)", city.name, len(attractions),
                 len(food_places), self.source.value)
        # DL: semantic similarity between each interest and each place's text
        semantic = self.semantic if (self.semantic is not None and self.semantic.available) else None
        if semantic and expanded and attractions:
            ctx.semantic = semantic_interest_matches(semantic, expanded, attractions)
        food = FoodEngine(ctx, food_places, semantic=semantic)
        if not food.candidates:
            warnings.append("No restaurants matched your dietary preferences; meal costs are generic estimates.")

        result = self._plan(ctx, home, city, food, attractions, PlanConstraints(), None)
        budget = budget_engine.summarize(result.days, req)
        applied: list[str] = []
        if req.fit_to_budget and budget.over_budget:
            for label, step in BUDGET_STEPS:
                c = PlanConstraints(
                    max_meal_cost_pp=ctx.meal_allowance * step["meal_factor"],
                    max_entry_fee_pp=(ctx.attraction_allowance * step["fee_factor"]) if step["fee_factor"] else None,
                    max_activities=max(1, ctx.pace.max_activities - step["drop"]),
                )
                w = TransportWeights(time=0.8 - step["cost_weight"], cost=step["cost_weight"], preference=0.2)
                result = self._plan(ctx, home, city, food, attractions, c, w)
                budget = budget_engine.summarize(result.days, req)
                applied.append(label)
                if not budget.over_budget:
                    break
            if budget.over_budget:
                warnings.append("Even after optimisation the plan exceeds your budget; see the suggestions below.")
        budget.applied_optimizations = applied
        budget.notes.append(f"Estimates use {costs.basis}.")

        if budget.over_budget or budget.remaining < 0.1 * req.budget:
            spare = [(c.place, c.score) for c in result.spare]
            budget.suggestions = budget_engine.suggest_savings(
                result.days, req, spare, cheaper_food=lambda item, day: self._cheaper_meal(food, item, day))

        attributions: list[str] = []
        enrich_note = self._enrich(result.days, food, city)
        if city_data:
            from app.providers.open.city_store import attributions_for

            attributions = attributions_for(city_data.sources)
        if enrich_note:
            warnings.append(enrich_note[0])
            if enrich_note[1]:
                attributions.append("Ratings and reviews marked 'Google' from Google Maps Platform")

        itinerary = Itinerary(
            data_source=self.source, generated_at=dt.datetime.now(dt.timezone.utc), request=req, accommodation=home,
            days=result.days, food_recommendations=food.recommendations(10),
            popular_dishes=self._dishes(food, city_data, req),
            budget=budget, unscheduled=result.unscheduled,
            warnings=warnings + result.warnings + [w for d in result.days for w in d.warnings],
            disclaimers=self._disclaimers(), attributions=attributions,
        )
        itinerary.ai_summary, itinerary.ai_status = ai_service.summarize(itinerary, self.settings)
        return itinerary

    # ------------------------------------------------------------------- helpers
    def _plan(self, ctx: ScoringContext, home: Place, city: CityContext, food: FoodEngine, attractions: list[Place],
              constraints: PlanConstraints, weights: TransportWeights | None) -> PlanResult:
        transport = self.transport_for(ctx.req, city, weights, ctx.costs)
        engine = ItineraryEngine(ctx, home, transport, food, self.source, constraints)
        return engine.build(attractions)

    def _enrich(self, days: list[DayPlan], food: FoodEngine, city: CityContext) -> tuple[str, bool] | None:
        factory = self.providers.extras.get("enricher_factory")
        if factory is None:
            return None
        enricher = factory()
        targets: dict[str, Place] = {}
        for d in days:
            for it in d.items:
                if it.type in (ItemType.ACTIVITY, ItemType.MEAL) and it.place is not None:
                    targets.setdefault(it.place.id, it.place)
        for c in sorted(food.candidates, key=lambda c: -c.base_score.score)[:10]:
            targets.setdefault(c.place.id, c.place)
        for p in targets.values():
            enricher.enrich(p, city)
        if enricher.errors:
            return (f"Google enrichment failed for {len(enricher.errors)} place(s): {enricher.errors[0]}",
                    enricher.matched > 0)
        return (f"Google ratings added for {enricher.matched} of {len(targets)} places "
                "(only exact name/location matches are used).", enricher.matched > 0)

    @staticmethod
    def _dishes(food: FoodEngine, city_data, req: TripRequest) -> list[DishSuggestion]:
        out = city_popular_dishes([c.place for c in food.candidates], req.food_preferences, food.semantic)
        have = {d.name.lower() for d in out}
        if city_data:
            for d in city_data.guide_dishes:
                if d.name.lower() not in have and _dish_allowed(d.name.lower(), req.food_preferences):
                    out.append(d)
                    have.add(d.name.lower())
        return out[:12]

    @staticmethod
    def _cheaper_meal(food: FoodEngine, item: ItineraryItem, day: DayPlan):
        if item.place is None or item.meal_type is None or item.cost is None:
            return None
        pp = item.cost.amount / max(1, food.ctx.req.travelers)
        pick = food.pick(item.meal_type, item.place.location, hm_to_min(item.start), day.date.weekday(),
                         exclude={item.place.id}, max_km=2.5, max_cost=pp * 0.8)
        if pick is None:
            return None
        cand, _ = pick
        return cand.place, budget_engine.meal_cost(cand.place, item.meal_type, food.ctx.req, food.ctx.costs).amount

    def _disclaimers(self) -> list[str]:
        out = ["Suitability scores are TripAura's own personalised score (0-5) and are kept separate from "
               "external ratings."]
        if self.source == DataSource.MOCK:
            out.insert(0, "DEMO MODE: places, 'demo ratings', reviews, fees, hours and travel times are illustrative "
                          "mock data for Jaipur - not real-world or Google data.")
        elif self.source == DataSource.OPEN:
            out.append("Places, opening hours, fees and diet tags come from community open data (OpenStreetMap, "
                       "Overture, Wikidata) and can be incomplete or out of date - check before you go.")
            out.append("Open data has no ratings; ratings appear only where Google enrichment found a match.")
            out.append("Travel times are estimates from distance and typical speeds (no live traffic) unless "
                       "a routing engine is configured.")
        else:
            out.append("Ratings labelled 'Google rating' and review counts come from the Google Places API.")
            out.append("Google does not publish entry fees or cab fares; those amounts are estimates.")
        out.append("Amounts marked 'estimate' are approximations; only 'verified' amounts came from a provider or you.")
        return out
