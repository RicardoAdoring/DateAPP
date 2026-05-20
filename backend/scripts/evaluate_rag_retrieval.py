from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys
from typing import Any


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.tools.rag_tool import build_destination_query
from app.rag.retriever import retrieve_travel_guide_chunks


DEFAULT_CASES_PATH = BACKEND_DIR / "eval" / "rag_eval_cases.json"

ALL_DESTINATIONS = ["大理", "成都", "西安", "厦门", "三亚"]


def _load_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("RAG eval cases file must contain a JSON list.")
    return data


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    top_k = int(case.get("top_k", 5))
    destination = str(case["destination"])
    query, _ = build_destination_query(
        destination=destination,
        preferences=list(case.get("preferences", [])),
        pace=case.get("pace"),
        special_notes=case.get("special_notes"),
    )

    start_time = time.perf_counter()
    chunks, _ = retrieve_travel_guide_chunks(query=query, top_k=top_k, destination=destination)
    latency_ms = round((time.perf_counter() - start_time) * 1000, 1)

    expected_title_keywords = list(case.get("expected_title_keywords", []))
    required_content_keywords = list(case.get("required_content_keywords", []))
    noise_title_keywords = list(case.get("noise_title_keywords", []))

    titles = [str(chunk.get("title", "")) for chunk in chunks]
    combined_text = "\n".join(
        f"{chunk.get('title', '')}\n{chunk.get('text', '')}" for chunk in chunks
    )

    top1_title = titles[0] if titles else ""
    top1_title_hit = _contains_any(top1_title, expected_title_keywords)
    topk_title_hit = any(_contains_any(title, expected_title_keywords) for title in titles)
    required_keyword_hits = _count_keyword_hits(combined_text, required_content_keywords)
    noise_count = sum(
        1 for title in titles if _contains_any(title, noise_title_keywords)
    )

    # MRR: 第一个命中期望关键词的结果排名的倒数
    reciprocal_rank = 0.0
    for rank, title in enumerate(titles, start=1):
        if _contains_any(title, expected_title_keywords):
            reciprocal_rank = 1.0 / rank
            break

    # 跨目的地污染：片段来源包含非当前目的地的城市名
    other_destinations = [d for d in ALL_DESTINATIONS if d not in destination]
    pollution_count = 0
    for chunk in chunks:
        source = str(chunk.get("source", ""))
        title = str(chunk.get("title", ""))
        chunk_text = f"{source} {title}"
        if any(other in chunk_text for other in other_destinations):
            pollution_count += 1

    return {
        "id": case.get("id", "<unknown>"),
        "destination": destination,
        "query": query,
        "top1_title": top1_title,
        "top1_title_hit": top1_title_hit,
        "topk_title_hit": topk_title_hit,
        "required_keyword_hits": required_keyword_hits,
        "required_keyword_total": len(required_content_keywords),
        "noise_count": noise_count,
        "reciprocal_rank": reciprocal_rank,
        "pollution_count": pollution_count,
        "latency_ms": latency_ms,
        "titles": titles,
    }


def _print_case_result(result: dict[str, Any]) -> None:
    print(f"case: {result['id']}")
    print(f"destination: {result['destination']}")
    print(f"query: {result['query']}")
    print(f"top1_title: {result['top1_title']}")
    print(f"top1_title_hit: {result['top1_title_hit']}")
    print(f"topk_title_hit: {result['topk_title_hit']}")
    print(
        "required_keyword_hits: "
        f"{result['required_keyword_hits']}/{result['required_keyword_total']}"
    )
    print(f"noise_count: {result['noise_count']}")
    print(f"reciprocal_rank: {result['reciprocal_rank']:.3f}")
    print(f"pollution_count: {result['pollution_count']}")
    print(f"latency_ms: {result['latency_ms']}")
    print("titles:")
    for index, title in enumerate(result["titles"], start=1):
        print(f"  {index}. {title}")
    print("-" * 60)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate RAG retrieval quality with a small scenario case set."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to the RAG eval cases JSON file.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    cases = _load_cases(args.cases)
    results = [_evaluate_case(case) for case in cases]

    for result in results:
        _print_case_result(result)

    total = len(results)
    top1_hits = sum(1 for result in results if result["top1_title_hit"])
    topk_hits = sum(1 for result in results if result["topk_title_hit"])
    total_noise = sum(int(result["noise_count"]) for result in results)
    total_required_hits = sum(int(result["required_keyword_hits"]) for result in results)
    total_required_keywords = sum(
        int(result["required_keyword_total"]) for result in results
    )
    mrr = sum(result["reciprocal_rank"] for result in results) / total
    noise_rate = total_noise / (total * int(cases[0].get("top_k", 5))) * 100
    total_pollution = sum(int(result["pollution_count"]) for result in results)
    avg_latency = sum(result["latency_ms"] for result in results) / total

    print("=== Summary ===")
    print(f"cases: {total}")
    print(f"top1_title_hit_rate: {top1_hits}/{total} ({top1_hits/total*100:.1f}%)")
    print(f"topk_title_hit_rate: {topk_hits}/{total} ({topk_hits/total*100:.1f}%)")
    print(f"required_keyword_coverage: {total_required_hits}/{total_required_keywords}")
    print(f"MRR: {mrr:.3f}")
    print(f"noise_count_total: {total_noise}")
    print(f"noise_rate: {noise_rate:.1f}%")
    print(f"cross_destination_pollution: {total_pollution}")
    print(f"avg_latency_ms: {avg_latency:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
