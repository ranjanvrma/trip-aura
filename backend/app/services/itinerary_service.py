"""Orchestrates a trip: geocode -> discover -> score -> schedule -> budget -> (optional) AI."""
from __future__ import annotations

import datetime as dt
import logging

from app.core.config import DataMode, Settings
from app.core.errors import UnsupportedInMockModeError
from app.core.timeutil import hm_to_min
from app.engines import budget as budget_engine
from app.engines.food import FoodEngine, city_popular_dishes
from app.engines.itinerary import ItineraryEngine, PlanConstraints, PlanResult, accommodation_place
from app.engines.recommendation import ScoringContext
from app.engines.transport import TransportEngine, TransportWeights
from app.providers.base import CityContext
from app.schemas.common import DataSource
from app.schemas.itinerary import DayPlan, Itinerary, ItineraryItem
from app.schemas.place import Place
from app.schemas.trip import TripRequest
from app.services import ai_service
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


class ItineraryService:
    def __init__(self, providers: ProviderBundle, settings: Settings):
        self.providers = providers
        self.settings = settings
        self.places = PlacesService(providers.places)
        self.geo = GeocodingService(providers.geocoding)
        self.routes = RoutesService(providers.routes)
        self._cities: dict[str, CityContext] = {}

    @property
    def source(self) -> DataSource:
        return self.providers.source

    def city(self, name: str) -> CityContext:
        key = name.strip().lower()
        if key not in self._cities:
            self._cities[key] = self.geo.resolve_city(name)
        return self._cities[key]

    def transport_for(self, req: TripRequest, city: CityContext, weights: TransportWeights | None = None) -> TransportEngine:
        from app.engines.pace import profile_for

        return TransportEngine(self.routes, city, req, profile_for(req.pace), weights)

    def _validate_mode(self, req: TripRequest) -> None:
        if self.providers.mode == DataMode.MOCK and req.currency != "INR":
            raise UnsupportedInMockModeError("The mock dataset is priced in INR; choose INR or enable live mode.")

    def generate(self, req: TripRequest) -> Itinerary:
        self._validate_mode(req)
        warnings: list[str] = []
        city = self.city(req.destination_city)
        acc, acc_warn = self.geo.resolve_accommodation(req.accommodation, city)
        warnings += acc_warn
        home = accommodation_place(req.accommodation.name_or_address, acc.location, acc.formatted_address,
                                   acc.source, req.accommodation.type.value)
        start = req.effective_start_date
        weekdays = [(start + dt.timedelta(days=i)).weekday() for i in range(req.num_days)]
        ctx = ScoringContext(req=req, origin=home.location, weekdays=weekdays)

        attractions = self.places.attraction_candidates(city, req)[: self.settings.max_candidate_places]
        food_places = self.places.food_candidates(city, req)[: self.settings.max_candidate_places]
        log.info("Planning %s: %d attraction and %d food candidates (%s)", city.name, len(attractions),
                 len(food_places), self.source.value)
        food = FoodEngine(ctx, food_places)
        if not food.candidates:
            warnings.append("No restaurants matched your dietary preferences; meal costs are generic estimates.")

        result, constraints = self._plan(ctx, home, city, food, attractions, PlanConstraints(), None)
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
                result, constraints = self._plan(ctx, home, city, food, attractions, c, w)
                budget = budget_engine.summarize(result.days, req)
                applied.append(label)
                if not budget.over_budget:
                    break
            if budget.over_budget:
                warnings.append("Even after optimisation the plan exceeds your budget; see the suggestions below.")
        budget.applied_optimizations = applied

        if budget.over_budget or budget.remaining < 0.1 * req.budget:
            spare = [(c.place, c.score) for c in result.spare]
            budget.suggestions = budget_engine.suggest_savings(
                result.days, req, spare, cheaper_food=lambda item, day: self._cheaper_meal(food, item, day))

        itinerary = Itinerary(
            data_source=self.source, generated_at=dt.datetime.now(dt.timezone.utc), request=req, accommodation=home,
            days=result.days, food_recommendations=food.recommendations(10),
            popular_dishes=city_popular_dishes([c.place for c in food.candidates], req.food_preferences),
            budget=budget, unscheduled=result.unscheduled, warnings=warnings + result.warnings
            + [w for d in result.days for w in d.warnings],
            disclaimers=self._disclaimers(),
        )
        itinerary.ai_summary, itinerary.ai_status = ai_service.summarize(itinerary, self.settings)
        return itinerary

    def _plan(self, ctx: ScoringContext, home: Place, city: CityContext, food: FoodEngine, attractions: list[Place],
              constraints: PlanConstraints, weights: TransportWeights | None) -> tuple[PlanResult, PlanConstraints]:
        transport = self.transport_for(ctx.req, city, weights)
        engine = ItineraryEngine(ctx, home, transport, food, self.source, constraints)
        return engine.build(attractions), constraints

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
        return cand.place, budget_engine.meal_cost(cand.place, item.meal_type, food.ctx.req).amount

    def _disclaimers(self) -> list[str]:
        out = ["Suitability scores are TripAura's own personalised score (0-5) and are kept separate from "
               "external ratings."]
        if self.source == DataSource.MOCK:
            out.insert(0, "DEMO MODE: places, 'demo ratings', reviews, fees, hours and travel times are illustrative "
                          "mock data for Jaipur - not real-world or Google data.")
        else:
            out.append("Ratings labelled 'Google rating' and review counts come from the Google Places API.")
            out.append("Google does not publish entry fees or cab fares; those amounts are estimates.")
        out.append("Amounts marked 'estimate' are approximations; only 'verified' amounts came from a provider or you.")
        return out
