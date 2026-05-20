from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.trip_planner_agent import collect_trip_context, generate_planner_draft
from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from app.models.schemas import TripRequest


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="使用真实大模型测试 trip_planner_agent.py 的最小链路。"
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
    parser.add_argument("--top-k", type=int, default=5, help="打印多少条 RAG 上下文")
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

    if not LLM_API_KEY:
        print("未检测到 LLM_API_KEY，无法测试真实大模型链路。")
        print("请先在 backend/.env 中配置真实 API Key。")
        return 1

    request = build_request(args)
    day_count = (request.end_date - request.start_date).days + 1
    day_count = max(day_count, 1)

    print("=== TripRequest ===")
    print(json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2))
    print()

    rag_contexts, rewrite_usage, rerank_usage = collect_trip_context(
        destination=request.destination,
        preferences=request.preferences,
        pace=request.pace,
        special_notes=request.special_notes,
        top_k=args.top_k,
    )

    print("=== Token 消耗 ===")
    print(f"Query Rewrite: prompt={rewrite_usage.get('prompt_tokens', 0)}, completion={rewrite_usage.get('completion_tokens', 0)}")
    print(f"Rerank: prompt={rerank_usage.get('prompt_tokens', 0)}, completion={rerank_usage.get('completion_tokens', 0)}")
    print()

    print("=== RAG 上下文 ===")
    if rag_contexts:
        for index, context in enumerate(rag_contexts[: args.top_k], start=1):
            print(f"[{index}] {context}")
            print()
    else:
        print("未检索到本地攻略上下文。")
        print()

    draft, planner_usage = generate_planner_draft(
        request=request,
        rag_contexts=rag_contexts,
        day_count=day_count,
    )

    print("=== Planner Token 消耗 ===")
    print(f"Planner: prompt={planner_usage.get('prompt_tokens', 0)}, completion={planner_usage.get('completion_tokens', 0)}")
    print()

    print("=== PlannerDraft ===")
    if draft is None:
        print("generate_planner_draft 返回了 None。")
        print("这通常表示：")
        print("1. API Key 未配置")
        print("2. langchain_openai 未安装")
        print("3. 模型返回的 days 数量与 day_count 不一致")
        print("4. 模型接口连接失败（例如 base_url / 模型名 / 平台兼容性问题）")
        print("5. 平台限流或配额不足（例如 429 / 403）")
        return 1

    print(json.dumps(draft.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
