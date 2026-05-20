from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.map_service import estimate_route, geocode_address, search_places  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="手工测试高德地图 service。")
    parser.add_argument("--keyword", default="大理古城", help="POI 搜索关键词")
    parser.add_argument("--city", default="大理", help="搜索城市")
    parser.add_argument("--address", default="云南省大理白族自治州大理古城", help="待地理编码的地址")
    args = parser.parse_args()

    print("=== POI 搜索 ===")
    places = search_places(keyword=args.keyword, city=args.city)
    print(json.dumps(places, ensure_ascii=False, indent=2))

    print("\n=== 地理编码 ===")
    geocode = geocode_address(address=args.address, city=args.city)
    print(json.dumps(geocode, ensure_ascii=False, indent=2))

    if geocode and geocode.get("latitude") is not None and geocode.get("longitude") is not None:
        print("\n=== 路线估算（同点位示例）===")
        route = estimate_route(
            origin_longitude=geocode["longitude"],
            origin_latitude=geocode["latitude"],
            destination_longitude=geocode["longitude"],
            destination_latitude=geocode["latitude"],
        )
        print(json.dumps(route, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
