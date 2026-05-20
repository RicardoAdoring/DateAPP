from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib import request
from urllib.parse import quote


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="读取 generated_trip.json，并测试真实 /trip/save 和 /trip/{trip_id} 接口。"
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
        "--user-id",
        default="user_001",
        help="保存时使用的用户 ID",
    )
    return parser


def load_generated_trip(input_file: str) -> dict:
    """读取 generated_trip.json。"""
    file_path = Path(input_file)
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


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


def get_json(url: str) -> dict:
    """发送 GET 请求并返回 JSON 响应。"""
    req = request.Request(url=url, method="GET")
    with request.urlopen(req) as response:
        response_text = response.read().decode("utf-8")
        return json.loads(response_text)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    itinerary = load_generated_trip(args.input_file)
    trip_id = itinerary["trip_id"]

    save_payload = {
        "trip_id": trip_id,
        "itinerary": itinerary,
        "user_id": args.user_id,
    }

    print("=== 保存请求 ===")
    print(json.dumps(save_payload, ensure_ascii=False, indent=2))
    print()

    save_response = post_json(f"{args.base_url}/trip/save", save_payload)

    print("=== 保存响应 ===")
    print(json.dumps(save_response, ensure_ascii=False, indent=2))
    print()

    encoded_trip_id = quote(trip_id, safe="")
    get_response = get_json(f"{args.base_url}/trip/{encoded_trip_id}")

    print("=== 查询响应 ===")
    print(json.dumps(get_response, ensure_ascii=False, indent=2))
    print()

    print("=== 快速检查 ===")
    print(f"saved_trip_id: {save_response.get('trip_id')}")
    print(f"queried_trip_id: {get_response.get('trip_id')}")
    itinerary_data = get_response.get("itinerary", {})
    print(f"destination: {itinerary_data.get('destination')}")
    print(f"days_count: {len(itinerary_data.get('days', []))}")
    print(f"summary: {itinerary_data.get('summary')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
