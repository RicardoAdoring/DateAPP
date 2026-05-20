from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from app.models.schemas import TripRequest
from app.services.trip_service import generate_trip_itinerary


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="使用真实大模型测试 trip_service.py 的完整 itinerary 生成链路。"
    )
    parser.add_argument("--destination", default="大理", help="目的地")
    parser.add_argument("--start-date", default="2026-04-10", help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", default="2026-04-12", help="结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--travelers", type=int, default=2, help="出行人数")
    parser.add_argument("--budget", type=float, default=3200, help="总预算")
    parser.add_argument(
        "--preferences",
        nargs="*",
        default=["自然风景", "拍照", "美食"],
        help="旅行偏好，可传多个值",
    )
    parser.add_argument("--pace", default="轻松", help="旅行节奏")
    parser.add_argument(
        "--dietary-preferences",
        nargs="*",
        default=["少辣"],
        help="饮食偏好，可传多个值",
    )
    parser.add_argument("--hotel-level", default="舒适型", help="酒店档次")
    parser.add_argument(
        "--special-notes",
        default="不想太早起床，希望安排一个适合看日落的地点",
        help="额外备注",
    )
    return parser


def build_request(args: argparse.Namespace) -> TripRequest:
    """把命令行参数组装成 TripRequest。"""
    return TripRequest(
        destination=args.destination,
        start_date=args.start_date,
        end_date=args.end_date,
        travelers=args.travelers,
        budget=args.budget,
        preferences=args.preferences,
        pace=args.pace,
        dietary_preferences=args.dietary_preferences,
        hotel_level=args.hotel_level,
        special_notes=args.special_notes,
    )


def mask_api_key(value: str) -> str:
    """把 API Key 打码，避免完整打印到终端。"""
    if not value:
        return "<EMPTY>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    print("=== 当前模型配置 ===")
    print(f"LLM_MODEL: {LLM_MODEL}")
    print(f"LLM_BASE_URL: {LLM_BASE_URL or '<DEFAULT>'}")
    print(f"LLM_API_KEY: {mask_api_key(LLM_API_KEY)}")
    print()

    request = build_request(args)

    print("=== TripRequest ===")
    print(json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print()

    itinerary = generate_trip_itinerary(request)

    print("=== Itinerary ===")
    print(json.dumps(itinerary.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print()

    print("=== 快速观察点 ===")
    print(f"trip_id: {itinerary.trip_id}")
    print(f"destination: {itinerary.destination}")
    print(f"days: {len(itinerary.days)}")
    print(f"estimated_budget: {itinerary.estimated_budget}")
    print(f"tips_count: {len(itinerary.tips)}")
    print(f"source_notes_count: {len(itinerary.source_notes)}")

    if itinerary.days:
        print()
        print("=== 第一天摘要 ===")
        first_day = itinerary.days[0]
        print(f"theme: {first_day.theme}")
        if first_day.spots:
            print(f"spot: {first_day.spots[0].name}")
            print(f"spot_description: {first_day.spots[0].description}")
        if first_day.meals:
            print(f"meal: {first_day.meals[0].name}")
            print(f"meal_notes: {first_day.meals[0].notes}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
