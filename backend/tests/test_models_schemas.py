from pathlib import Path
import sys

import pytest
from pydantic import ValidationError


# Allow direct imports from backend/app when running tests from this file.
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import (  # noqa: E402
    BudgetBreakdown,
    DayPlan,
    HotelItem,
    Itinerary,
    MealItem,
    SpotItem,
    TransportItem,
    TripEditRequest,
    TripRequest,
    TripSaveRequest,
)


def build_trip_request() -> TripRequest:
    '''构建一个示例 TripRequest 对象，用于测试'''
    return TripRequest(
        destination="大理",
        start_date="2026-04-10",
        end_date="2026-04-12",
        travelers=2,
        budget=3200,
        preferences=["自然风景", "拍照", "美食"],
        pace="轻松",
        dietary_preferences=["少辣"],
        hotel_level="舒适型",
        special_notes="不想太早起床，希望能安排看日落。",
    )


def build_itinerary() -> Itinerary:
    '''构建一个示例 Itinerary 对象，用于测试'''
    day_one = DayPlan(
        day_index=1,
        date="2026-04-10",
        theme="古城慢游",
        spots=[
            SpotItem(
                name="大理古城",
                start_time="10:00",
                end_time="12:00",
                description="先在古城慢慢逛，适应旅行节奏。",
                estimated_cost=0,
                location="大理古城",
            )
        ],
        meals=[
            MealItem(
                name="古城米线店",
                meal_type="午餐",
                estimated_cost=60,
                notes="口味可选清淡。",
            )
        ],
        hotel=HotelItem(
            name="古城舒适型民宿",
            level="舒适型",
            estimated_cost=280,
            location="大理古城附近",
        ),
        transport=[
            TransportItem(
                mode="打车",
                from_place="大理站",
                to_place="大理古城",
                estimated_cost=35,
                duration="40 分钟",
            )
        ],
        notes=["第一天尽量轻松，不安排太赶。"],
    )

    return Itinerary(
        trip_id="trip_dali_demo_001",
        destination="大理",
        summary="适合两人轻松游玩的 3 日行程示例。",
        days=[day_one],
        estimated_budget=1550,
        budget_breakdown=BudgetBreakdown(
            transport=335,
            hotel=640,
            meals=180,
            tickets=120,
            other=275,
            total=1550,
        ),
        tips=["早晚温差较大，建议带薄外套。"],
        source_notes=["该结果目前是 Day 2 的手工演示数据。"],
    )


def test_trip_request_can_be_created_successfully() -> None:
    '''测试 TripRequest 模型能否成功创建'''
    request = build_trip_request()

    assert request.destination == "大理"
    assert request.travelers == 2
    assert request.budget == 3200
    assert request.preferences == ["自然风景", "拍照", "美食"]


def test_trip_request_rejects_invalid_travelers() -> None:
    '''测试 TripRequest 模型在 travelers 字段为 0 时会抛出 ValidationError'''
    with pytest.raises(ValidationError):
        TripRequest(
            destination="大理",
            start_date="2026-04-10",
            end_date="2026-04-12",
            travelers=0,
            budget=3200,
        )


def test_trip_request_rejects_negative_budget() -> None:
    '''测试 TripRequest 模型在 budget 字段为负数时会抛出 ValidationError'''
    with pytest.raises(ValidationError):
        TripRequest(
            destination="大理",
            start_date="2026-04-10",
            end_date="2026-04-12",
            travelers=2,
            budget=-1,
        )


def test_itinerary_can_be_created_successfully() -> None:
    '''测试 Itinerary 模型能否成功创建'''
    itinerary = build_itinerary()

    assert itinerary.trip_id == "trip_dali_demo_001"
    assert itinerary.destination == "大理"
    assert len(itinerary.days) == 1
    assert itinerary.days[0].theme == "古城慢游"
    assert itinerary.budget_breakdown.total == 1550


def test_day_plan_contains_nested_objects() -> None:
    '''测试 DayPlan 模型中的嵌套对象是否正确创建'''
    itinerary = build_itinerary()
    first_day = itinerary.days[0]

    assert isinstance(first_day.spots[0], SpotItem)
    assert isinstance(first_day.meals[0], MealItem)
    assert isinstance(first_day.hotel, HotelItem)
    assert isinstance(first_day.transport[0], TransportItem)


def test_trip_edit_request_can_wrap_existing_itinerary() -> None:
    '''测试 TripEditRequest 模型能否正确包装一个已存在的 Itinerary'''
    itinerary = build_itinerary()

    edit_request = TripEditRequest(
        trip_id=itinerary.trip_id,
        current_itinerary=itinerary,
        user_instruction="第二天改轻松一点",
        edit_scope="day_2",
        preserve_constraints=["保留轻松节奏"],
    )

    assert edit_request.trip_id == "trip_dali_demo_001"
    assert edit_request.current_itinerary.destination == "大理"
    assert edit_request.user_instruction == "第二天改轻松一点"


def test_trip_save_request_can_hold_full_itinerary() -> None:
    '''测试 TripSaveRequest 模型能否正确持有一个完整的 Itinerary'''
    itinerary = build_itinerary()

    save_request = TripSaveRequest(
        trip_id=itinerary.trip_id,
        itinerary=itinerary,
        user_id="user_001",
    )

    assert save_request.trip_id == "trip_dali_demo_001"
    assert save_request.itinerary.summary == "适合两人轻松游玩的 3 日行程示例。"
    assert save_request.user_id == "user_001"
