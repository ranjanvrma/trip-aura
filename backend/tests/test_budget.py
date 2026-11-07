from app.engines import budget as be
from app.engines.fares import estimate_fare
from app.providers.mock.providers import _all_places
from app.schemas.common import DataSource, LatLng, Money
from app.schemas.itinerary import ItemType
from app.schemas.place import Place, PlaceKind
from app.schemas.trip import TransportMode, TripRequest


def req(**kw) -> TripRequest:
    data = {"accommodation": {"name_or_address": "MI Road"}, "destination_city": "Jaipur", "num_days": 2,
            "budget": 10000, "travelers": 1}
    data.update(kw)
    return TripRequest.model_validate(data)


def test_fare_per_person_vs_per_vehicle():
    bus1 = estimate_fare(TransportMode.BUS, 5, "INR", 1).amount
    bus3 = estimate_fare(TransportMode.BUS, 5, "INR", 3).amount
    assert bus3 == 3 * bus1
    auto1 = estimate_fare(TransportMode.AUTO, 5, "INR", 1).amount
    auto3 = estimate_fare(TransportMode.AUTO, 5, "INR", 3).amount   # 3 fit in one auto
    auto4 = estimate_fare(TransportMode.AUTO, 5, "INR", 4).amount   # needs two autos
    assert auto1 == auto3 and auto4 == 2 * auto1


def test_fare_minimum_and_cap():
    assert estimate_fare(TransportMode.CAB, 0.2, "INR").amount == 100          # minimum fare
    assert estimate_fare(TransportMode.METRO, 100, "INR").amount == 35         # capped
    assert estimate_fare(TransportMode.WALKING, 3, "INR").amount == 0
    assert estimate_fare(TransportMode.CAB, 5, "INR").verified is False


def test_entry_cost_multiplies_travelers_and_estimates_unknown():
    albert = _all_places()["mock-albert-hall"]
    assert be.entry_cost(albert, req(travelers=3)).amount == albert.entry_fee.amount * 3
    unknown = Place(id="x", name="X", kind=PlaceKind.ATTRACTION, location=LatLng(lat=0, lng=0), source=DataSource.GOOGLE)
    m = be.entry_cost(unknown, req(travelers=2))
    assert m.amount == be.UNKNOWN_ENTRY_FEE["INR"] * 2 and m.verified is False and "not available" in m.note
    park = unknown.model_copy(update={"kind": PlaceKind.PARK})
    assert be.entry_cost(park, req()).amount == 0


def test_meal_cost_breakfast_factor_and_price_level():
    thali = _all_places()["mock-food-thali-house"]
    lunch = be.meal_cost(thali, "lunch", req(travelers=2)).amount
    breakfast = be.meal_cost(thali, "breakfast", req(travelers=2)).amount
    assert lunch == thali.avg_cost_per_person.amount * 2
    assert breakfast == round(lunch * be.BREAKFAST_FACTOR, 2)
    generic = Place(id="g", name="G", kind=PlaceKind.RESTAURANT, location=LatLng(lat=0, lng=0),
                    price_level=3, source=DataSource.GOOGLE)
    assert be.meal_cost(generic, "dinner", req()).amount == be.PRICE_LEVEL_MEAL["INR"][3]


def test_summary_totals_add_up(mock_service):
    r = req(num_days=3, budget=20000, accommodation_cost_total=6000)
    it = mock_service.generate(r)
    b = it.budget
    cat = b.by_category
    assert abs(cat.food + cat.transport + cat.attractions + cat.accommodation - b.planned_total) < 0.01
    assert abs(sum(d.total for d in b.per_day) + cat.accommodation - b.planned_total) < 0.01
    assert abs(b.verified_total + b.estimated_total - b.planned_total) < 0.01
    assert abs(b.remaining - (b.total_budget - b.planned_total)) < 0.01
    assert cat.accommodation == 6000 and b.verified_total >= 6000  # user-entered amount counts as confirmed
    # per-day totals match item costs
    for d in it.days:
        items_sum = sum((i.travel.chosen.cost.amount if i.type == ItemType.TRAVEL else (i.cost.amount if i.cost else 0))
                        for i in d.items if i.type in (ItemType.TRAVEL, ItemType.MEAL, ItemType.ACTIVITY))
        assert abs(items_sum - d.budget.total) < 0.01


def test_over_budget_produces_suggestions(mock_service):
    it = mock_service.generate(req(num_days=2, budget=1200, transport_modes=["cab"]))
    assert it.budget.over_budget
    assert it.budget.suggestions
    kinds = {s.kind for s in it.budget.suggestions}
    assert kinds & {"cheaper_transport", "free_attraction", "cheaper_food"}
    assert all(s.estimated_saving > 0 for s in it.budget.suggestions)
    savings = [s.estimated_saving for s in it.budget.suggestions]
    assert savings == sorted(savings, reverse=True)


def test_fit_to_budget_reduces_cost(mock_service):
    base = dict(num_days=2, budget=2500, transport_modes=["cab", "auto", "bus", "walking"],
                interests=["wildlife", "adventure", "museums"])
    plain = mock_service.generate(req(**base))
    fitted = mock_service.generate(req(**base, fit_to_budget=True))
    if plain.budget.over_budget:
        assert fitted.budget.planned_total < plain.budget.planned_total
        assert fitted.budget.applied_optimizations
    else:
        assert fitted.budget.applied_optimizations == []


def test_verified_money_counted_separately():
    from app.schemas.itinerary import ItineraryItem
    items = [
        ItineraryItem(id="a", type=ItemType.ACTIVITY, period="morning", start="10:00", end="11:00", duration_min=60,
                      title="A", cost=Money(amount=100, currency="INR", verified=True, source=DataSource.GOOGLE)),
        ItineraryItem(id="b", type=ItemType.MEAL, period="afternoon", start="13:00", end="14:00", duration_min=60,
                      title="B", cost=Money.estimate(250, "INR")),
    ]
    db = be.day_budget(1, items)
    assert db.verified_amount == 100 and db.estimated_amount == 250 and db.total == 350
    assert db.totals.attractions == 100 and db.totals.food == 250
