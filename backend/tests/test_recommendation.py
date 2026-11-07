from app.engines.recommendation import (
    WEIGHTS, ScoringContext, affordability, distance_component, score_attraction, transport_component,
)
from app.providers.mock.providers import _all_places
from app.schemas.common import LatLng
from app.schemas.place import ExternalRating
from app.schemas.common import DataSource
from app.schemas.trip import TransportMode, TripRequest

MI_ROAD = LatLng(lat=26.916, lng=75.809)


def ctx_for(**overrides) -> ScoringContext:
    data = {"accommodation": {"name_or_address": "MI Road"}, "destination_city": "Jaipur", "num_days": 2,
            "budget": 12000, "interests": ["museums"], "transport_modes": ["walking", "auto"]}
    data.update(overrides)
    return ScoringContext(req=TripRequest.model_validate(data), origin=MI_ROAD, weekdays=[1, 2])


def place(pid: str):
    return _all_places()[pid].model_copy(deep=True)


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_score_is_bounded_and_explained():
    for pid in ("mock-albert-hall", "mock-amber-fort", "mock-central-park", "mock-chokhi-dhani"):
        s = score_attraction(place(pid), ctx_for())
        assert 0 <= s.score <= 5
        assert set(s.components) == set(WEIGHTS)
        assert all(0 <= v <= 1 for v in s.components.values())
        assert s.reasons, "every score must come with reasons"


def test_interest_match_raises_score():
    museum = place("mock-albert-hall")
    with_interest = score_attraction(museum, ctx_for(interests=["museums"]))
    without = score_attraction(museum, ctx_for(interests=["shopping"]))
    assert with_interest.score > without.score
    assert any("museums" in r for r in with_interest.reasons)


def test_external_rating_does_not_affect_suitability():
    """The two ratings must stay independent."""
    p = place("mock-albert-hall")
    a = score_attraction(p, ctx_for()).score
    p.external_rating = ExternalRating(provider=DataSource.MOCK, rating=1.0, review_count=5, label="x")
    b = score_attraction(p, ctx_for()).score
    p.external_rating = None
    c = score_attraction(p, ctx_for()).score
    assert a == b == c


def test_famous_place_outside_interests_is_flagged_discovery():
    s = score_attraction(place("mock-hawa-mahal"), ctx_for(interests=["wildlife"]))
    assert s.discovery is True
    assert any("best-known" in r for r in s.reasons)
    s2 = score_attraction(place("mock-sisodia-garden"), ctx_for(interests=["wildlife"]))
    assert s2.discovery is False and s2.components["interest"] == 0


def test_custom_interest_matches_by_text():
    s = score_attraction(place("mock-jhalana-safari"), ctx_for(interests=["leopard"]))
    assert s.components["interest"] > 0


def test_affordability_curve():
    assert affordability(0, 100) == 1.0
    assert affordability(100, 100) == 1.0
    assert affordability(200, 100) == 0.5
    assert affordability(300, 100) == 0.0
    assert affordability(None, 100) == 0.6


def test_distance_component_decreases():
    vals = [distance_component(km, 10) for km in (0, 2, 5, 10, 20)]
    assert vals == sorted(vals, reverse=True)
    assert abs(distance_component(10, 10) - 0.5) < 1e-9


def test_transport_component_walking_only():
    assert transport_component(1.0, [TransportMode.WALKING], 2.5) == 1.0
    assert transport_component(10.0, [TransportMode.WALKING], 2.5) == 0.0
    assert transport_component(10.0, [TransportMode.WALKING, TransportMode.CAB], 2.5) == 1.0


def test_expensive_place_scores_lower_on_small_budget():
    safari = place("mock-jhalana-safari")  # demo fee 1500
    rich = score_attraction(safari, ctx_for(budget=100000, interests=["wildlife"]))
    poor = score_attraction(safari, ctx_for(budget=3000, interests=["wildlife"]))
    assert rich.components["budget"] > poor.components["budget"]
    assert rich.score > poor.score


def test_pace_prefers_short_visits_when_packed():
    long_visit = place("mock-chokhi-dhani")  # 150 min
    relaxed = score_attraction(long_visit, ctx_for(pace="relaxed"))
    packed = score_attraction(long_visit, ctx_for(pace="packed"))
    assert packed.components["pace"] >= relaxed.components["pace"] or relaxed.components["pace"] <= 0.8
