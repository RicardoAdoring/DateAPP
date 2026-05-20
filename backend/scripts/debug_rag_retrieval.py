from __future__ import annotations

import argparse
from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.tools.rag_tool import build_destination_query
from app.rag.retriever import retrieve_travel_guide_chunks


def _parse_preferences(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    parts = [item.strip() for item in raw_value.replace("，", ",").split(",")]
    return [item for item in parts if item]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="调试智旅云图 RAG 在线检索结果。"
    )
    parser.add_argument("--destination", required=True, help="目的地，例如：大理")
    parser.add_argument(
        "--preferences",
        default="",
        help="偏好，使用逗号分隔，例如：自然风景,拍照,美食",
    )
    parser.add_argument("--pace", default="", help="节奏偏好，例如：轻松")
    parser.add_argument(
        "--special-notes",
        default="",
        help="补充备注，例如：不想太早起床，希望安排一个适合看日落的地点。",
    )
    parser.add_argument("--top-k", type=int, default=5, help="召回数量")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    preferences = _parse_preferences(args.preferences)
    query, _ = build_destination_query(
        destination=args.destination,
        preferences=preferences,
        pace=args.pace or None,
        special_notes=args.special_notes or None,
    )
    matched_chunks, _ = retrieve_travel_guide_chunks(query=query, top_k=args.top_k)

    print("=== RAG 检索调试 ===")
    print(f"destination: {args.destination}")
    print(f"preferences: {preferences}")
    print(f"pace: {args.pace or '<空>'}")
    print(f"special_notes: {args.special_notes or '<空>'}")
    print(f"top_k: {args.top_k}")
    print()
    print("=== 检索 Query ===")
    print(query)
    print()

    if not matched_chunks:
        print("=== 检索结果 ===")
        print("未召回到任何攻略片段。")
        return 0

    print("=== Top-K 召回片段 ===")
    for index, chunk in enumerate(matched_chunks, start=1):
        print(f"[Top {index}]")
        print(f"source: {chunk.get('source', '未知来源')}")
        print(f"title: {chunk.get('title', '未命名片段')}")
        print(f"rerank_score: {chunk.get('rerank_score', '<none>')}")
        print(f"rerank_reasons: {chunk.get('rerank_reasons', [])}")
        print("content:")
        print(chunk.get("text", "").strip())
        print("-" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
