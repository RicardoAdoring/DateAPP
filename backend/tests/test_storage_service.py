from pathlib import Path
import sys
import uuid


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import TripRequest  # noqa: E402
from app.services.storage_service import get_itinerary_by_trip_id, save_itinerary  # noqa: E402
from app.services.trip_service import generate_trip_itinerary  # noqa: E402


def build_trip_request() -> TripRequest:
    """构造一个合法的 TripRequest，供存储层测试复用。"""
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
        special_notes="不想太早起床，希望安排一个适合看日落的地点",
    )


def test_save_itinerary_returns_trip_id() -> None:
    """测试保存 itinerary 后会返回 trip_id。"""
    itinerary = generate_trip_itinerary(build_trip_request())
    itinerary.trip_id = f"{itinerary.trip_id}_{uuid.uuid4().hex[:8]}"

    saved_trip_id = save_itinerary(itinerary)

    assert saved_trip_id == itinerary.trip_id


def test_get_itinerary_by_trip_id_returns_saved_result() -> None:
    """测试可以根据 trip_id 读回已保存的 itinerary。"""
    itinerary = generate_trip_itinerary(build_trip_request())
    itinerary.trip_id = f"{itinerary.trip_id}_{uuid.uuid4().hex[:8]}"

    save_itinerary(itinerary)
    trip_detail = get_itinerary_by_trip_id(itinerary.trip_id)

    assert trip_detail is not None
    assert trip_detail.trip_id == itinerary.trip_id
    assert trip_detail.itinerary.destination == "大理"
    assert len(trip_detail.itinerary.days) == 3


def test_get_itinerary_by_trip_id_returns_none_for_missing_trip() -> None:
    """测试查询不存在的 trip_id 时会返回 None。"""
    trip_detail = get_itinerary_by_trip_id("trip_not_exists")
    assert trip_detail is None
