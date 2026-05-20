from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib import request


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="读取 generated_trip.json，并调用真实 /trip/edit 接口。"
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="FastAPI 服务地址",
    )
    parser.add_argument(
        "--input-file",
        default="generated_trip.json",
        help="先前通过 /trip/generate 保存的 itinerary 文件",
    )
    parser.add_argument(
        "--instruction",
        default="第二天改得更轻松一点，不要安排太满",
        help="用户编辑指令",
    )
    parser.add_argument(
        "--edit-scope",
        default="day_2",
        help="编辑范围，例如 day_2",
    )
    return parser


def load_generated_trip(input_file: str) -> dict:
    """读取 generated_trip.json。"""
    file_path = Path(input_file)
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_edit_payload(
    itinerary: dict,
    instruction: str,
    edit_scope: str,
) -> dict:
    """组装 /trip/edit 的请求体。"""
    return {
        "trip_id": itinerary["trip_id"],
        "current_itinerary": itinerary,
        "user_instruction": instruction,
        "edit_scope": edit_scope,
        "preserve_constraints": ["保留预算结构"],
    }


def post_json(url: str, payload: dict) -> dict:
    """发送 JSON POST 请求并返回 JSON 响应。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req) as response:
        response_text = response.read().decode("utf-8")
        return json.loads(response_text)


def print_day_summary(title: str, itinerary: dict, day_index: int) -> None:
    """打印某一天的简要信息。"""
    print(title)
    matched_day = next(
        (day for day in itinerary.get("days", []) if day.get("day_index") == day_index),
        None,
    )
    if matched_day is None:
        print(f"未找到 day_{day_index}")
        print()
        return

    print(f"theme: {matched_day.get('theme')}")
    if matched_day.get("spots"):
        print(f"spot: {matched_day['spots'][0].get('name')}")
        print(f"spot_description: {matched_day['spots'][0].get('description')}")
    if matched_day.get("notes"):
        print(f"notes: {matched_day['notes']}")
    print()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    original_itinerary = load_generated_trip(args.input_file)
    payload = build_edit_payload(
        itinerary=original_itinerary,
        instruction=args.instruction,
        edit_scope=args.edit_scope,
    )

    print("=== 编辑请求 ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()

    response = post_json(f"{args.base_url}/trip/edit", payload)

    print("=== 编辑后的 Itinerary ===")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    print()

    target_day = 2
    print_day_summary("=== 编辑前 day_2 ===", original_itinerary, target_day)
    print_day_summary("=== 编辑后 day_2 ===", response, target_day)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
