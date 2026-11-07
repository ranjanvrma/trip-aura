import datetime as dt

import pytest

from app.core.timeutil import hm_to_min
from app.engines.itinerary import open_window
from app.engines.pace import PACE_PROFILES
from app.providers.mock.providers import _all_places
from app.schemas.itinerary import ItemType
from app.schemas.trip import Pace, TripRequest


def _gen(svc, base, **kw):
    data = {**base, **kw}
    return svc.generate(TripRequest.model_validate(data))


def test_open_window_respects_hours():
    hawa = _all_places()["mock-hawa-mahal"]  # 09:00-16:30 daily (demo)
    assert open_window(hawa, 0, hm_to_min("08:00"), 45) == (540, 585)       # waits for opening
    assert open_window(hawa, 0, hm_to_min("16:00"), 45) is None             # would close mid-visit
    birla = _all_places()["mock-birla-mandir"]  # split hours 08-12, 16-20
    assert open_window(birla, 0, hm_to_min("11:30"), 45) == (960, 1005)     # jumps to the second window


def test_open_window_closed_day():
    johari = _all_places()["mock-johari-bazaar"]  # closed Sunday (6)
    assert open_window(johari, 6, hm_to_min("11:00"), 60) is None
    assert open_window(johari, 5, hm_to_min("11:00"), 60) is not None


def test_days_start_and_end_at_accommodation(mock_service, base_request):
    it = _gen(mock_service, base_request)
    assert len(it.days) == 2
    for day in it.days:
        assert day.items[0].type == ItemType.START
        assert day.items[-1].type == ItemType.END
        assert day.items[0].place.id == "accommodation"
        assert day.items[-1].place.id == "accommodation"
        travel_home = [i for i in day.items if i.type == ItemType.TRAVEL][-1]
        assert travel_home.travel.to_name == it.accommodation.name


def test_timeline_is_chronological_and_non_overlapping(mock_service, base_request):
    it = _gen(mock_service, base_request, num_days=3)
    for day in it.days:
        prev_end = 0
        for item in day.items:
            s, e = hm_to_min(item.start), hm_to_min(item.end)
            assert e >= s, item
            assert s >= prev_end - 1, f"{item.title} starts {item.start} before previous end"
            prev_end = e


def test_activities_within_opening_hours(mock_service, base_request):
    it = _gen(mock_service, base_request, num_days=3)
    for day in it.days:
        wd = day.date.weekday()
        for item in day.items:
            if item.type != ItemType.ACTIVITY:
                continue
            ranges = item.place.opening_hours.weekly.get(wd, [])
            s, e = hm_to_min(item.start), hm_to_min(item.end)
            assert any(hm_to_min(r.open) <= s and e <= hm_to_min(r.close) for r in ranges), item.title


def test_three_meals_per_day(mock_service, base_request):
    it = _gen(mock_service, base_request)
    for day in it.days:
        meals = [i.meal_type for i in day.items if i.type == ItemType.MEAL]
        assert meals == ["breakfast", "lunch", "dinner"]
        lunch = next(i for i in day.items if i.meal_type == "lunch")
        assert hm_to_min("12:00") <= hm_to_min(lunch.start) <= hm_to_min("15:30")


def test_no_attraction_repeats_across_days(mock_service, base_request):
    it = _gen(mock_service, base_request, num_days=4)
    ids = [i.place.id for d in it.days for i in d.items if i.type == ItemType.ACTIVITY]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("pace", list(Pace))
def test_activity_count_respects_pace(mock_service, base_request, pace):
    it = _gen(mock_service, base_request, pace=pace.value)
    for day in it.days:
        n = sum(1 for i in day.items if i.type == ItemType.ACTIVITY)
        assert 1 <= n <= PACE_PROFILES[pace].max_activities


def test_packed_has_more_activities_than_relaxed(mock_service, base_request):
    def count(p):
        it = _gen(mock_service, base_request, pace=p)
        return sum(1 for d in it.days for i in d.items if i.type == ItemType.ACTIVITY)
    assert count("packed") > count("relaxed")


def test_relaxed_pace_has_rest_periods(mock_service, base_request):
    it = _gen(mock_service, base_request, pace="relaxed")
    for day in it.days:
        assert any(i.type == ItemType.REST for i in day.items)


def test_closed_place_not_scheduled_on_closed_day(mock_service, base_request):
    # 2026-11-15 is a Sunday; Johari & Bapu Bazaar (demo) are closed on Sundays
    it = _gen(mock_service, base_request, start_date="2026-11-15", num_days=1, interests=["shopping", "markets"])
    assert dt.date(2026, 11, 15).weekday() == 6
    names = [i.title for i in it.days[0].items if i.type == ItemType.ACTIVITY]
    assert "Johari Bazaar" not in names and "Bapu Bazaar" not in names


def test_travel_legs_have_mode_time_and_cost(mock_service, base_request):
    it = _gen(mock_service, base_request)
    legs = [i.travel for d in it.days for i in d.items if i.type == ItemType.TRAVEL]
    assert legs
    for leg in legs:
        assert leg.chosen.duration_min > 0 and leg.chosen.distance_km > 0
        assert leg.chosen.cost.verified is False  # mock/estimate fares are never "verified"
        assert leg.recommendation_reason
        if leg.chosen.mode.value == "walking":
            assert leg.chosen.distance_km <= PACE_PROFILES[Pace.MODERATE].max_walk_km


def test_walking_only_user_gets_flagged_fallback(mock_service, base_request):
    it = _gen(mock_service, base_request, transport_modes=["walking"], num_days=1)
    legs = [i.travel for d in it.days for i in d.items if i.type == ItemType.TRAVEL]
    long_legs = [l for l in legs if l.chosen.mode.value != "walking"]
    for leg in long_legs:
        assert "None of your preferred modes is practical" in leg.recommendation_reason


def test_mock_itinerary_is_labelled(mock_service, base_request):
    it = _gen(mock_service, base_request)
    assert it.data_source.value == "mock"
    assert any("DEMO MODE" in d for d in it.disclaimers)
    for d in it.days:
        for i in d.items:
            if i.place and i.place.external_rating:
                assert i.place.external_rating.provider.value == "mock"
                assert i.place.external_rating.verified is False
                assert "not from Google" in i.place.external_rating.label
