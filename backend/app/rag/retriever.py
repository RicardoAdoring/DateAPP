import hashlib
import json
import logging
import re

import httpx

from app.config import (
    RERANK_API_KEY,
    RERANK_BASE_URL,
    RERANK_MODEL,
    RERANK_TIMEOUT_SECONDS,
    REDIS_RAG_TTL_SECONDS,
    REDIS_RERANK_TTL_SECONDS,
)
from app.rag.vector_db import search_guide_chunks
from app.services.cache_service import get_cached_json, set_cached_json


DASHSCOPE_RERANK_URL = f"{RERANK_BASE_URL}/reranks"


logger = logging.getLogger(__name__)


def _normalize_cache_text(value: str) -> str:
    """把检索 query 做简单标准化，避免大小写和空格造成重复 key。"""
    return " ".join(value.strip().lower().split())


def _extract_query_keywords(query: str) -> list[str]:
    """从 query 中切出用于轻量重排序的关键词。"""
    raw_parts = re.split(r"[\s,，。；;、]+", query)
    return [part.strip() for part in raw_parts if part.strip()]


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _score_chunk_for_rerank(
    query: str,
    chunk: dict[str, str],
    destination: str | None = None,
) -> int:
    """根据 query 关键词对召回片段做轻量打分。"""
    title = chunk.get("title", "")
    text = chunk.get("text", "")
    source = chunk.get("source", "")
    combined_text = f"{title}\n{text}"
    reasons: list[str] = []

    score = 0
    for keyword in _extract_query_keywords(query):
        if keyword in title:
            score += 3
            reasons.append(f"title+3:{keyword}")
        if keyword in text:
            score += 1
            reasons.append(f"text+1:{keyword}")

    # 文档开头通常是低信息量噪声片段。
    if title == "文档开头":
        score -= 8
        reasons.append("noise-8:文档开头")

    # 行程类片段更适合承接"景点 / 行程 / 推荐"类请求。
    if "行程" in title and "行程参考" not in title:
        score += 4
        reasons.append("domain+4:行程标题")

    # "经典行程参考"类片段内容过于全面，会霸占 Top1，对非行程查询做降权。
    if "行程参考" in title:
        score -= 4
        reasons.append("domain-4:行程参考降权")

    # "目的地简介"内容过于泛化，对具体查询（美食、亲子等）不是最优候选。
    if "目的地简介" in title:
        score -= 2
        reasons.append("domain-2:目的地简介降权")

    # 餐饮/预算类片段在"日落/拍照/轻松"这类主目标下通常不是最优候选。
    if _contains_any(title, ["餐饮", "预算"]) and not _contains_any(
        combined_text,
        ["日落", "傍晚", "拍照", "摄影", "出片", "洱海", "双廊", "慢节奏"],
    ):
        score -= 3
        reasons.append("domain-3:餐饮预算弱相关")

    # 目的地不匹配降权：片段来源与查询目的地不一致时降权。
    if destination:
        chunk_lower = f"{source} {title} {text}".lower()
        if destination.lower() not in chunk_lower:
            score -= 5
            reasons.append(f"dest-5:非{destination}片段")

    chunk["rerank_reasons"] = reasons
    return score


_NOISE_TITLES = {"文档开头"}


def _extract_rerank_token_usage(response_data: dict) -> tuple[dict[str, int], bool]:
    """只读取接口返回的官方 usage；没有 usage 时不做本地估算。"""
    usage = response_data.get("usage") or response_data.get("output", {}).get("usage") or {}
    prompt_tokens = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("input_token_count")
        or 0
    )
    completion_tokens = (
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("output_token_count")
        or 0
    )
    total_tokens = usage.get("total_tokens") or usage.get("total_token_count") or 0

    if not prompt_tokens and not completion_tokens and total_tokens:
        prompt_tokens = total_tokens

    if prompt_tokens or completion_tokens:
        return {
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
        }, True

    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }, False


def _rerank_with_dashscope(
    query: str,
    chunks: list[dict[str, str]],
    top_k: int,
) -> tuple[list[tuple[float, int]] | None, dict[str, int]]:
    """调用 DashScope qwen3-rerank 模型做语义重排序。返回 (scored, token_usage)。"""
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    if not RERANK_API_KEY or not chunks:
        print("[rerank] skip qwen3-rerank: missing RERANK_API_KEY or empty chunks")
        return None, empty_usage

    # 过滤已知噪声片段，避免浪费 rerank 名额
    filtered = [
        (i, chunk) for i, chunk in enumerate(chunks)
        if chunk.get("title", "") not in _NOISE_TITLES
    ]
    if not filtered:
        print("[rerank] skip qwen3-rerank: all chunks are noise")
        return None, empty_usage

    original_indices = [i for i, _ in filtered]
    clean_chunks = [chunk for _, chunk in filtered]

    documents = [
        f"{chunk.get('title', '')}\n{chunk.get('text', '')}"
        for chunk in clean_chunks
    ]
    instruct = (
        "你是一个旅行攻略检索专家。"
        "给定一个旅行规划查询，从候选文档中检索出最具体、最详细、最能直接回答用户问题的片段。"
        "优先选择包含具体景点名称、活动推荐、实用信息的片段，"
        "避免选择泛化的目的地简介、文档开头等信息量低的片段。"
    )
    payload = {
        "model": RERANK_MODEL,
        "documents": documents,
        "query": query,
        "top_n": min(top_k, len(documents)),
        "instruct": instruct,
    }

    try:
        print(
            f"[rerank] calling qwen3-rerank: query={query}, "
            f"candidate_count={len(clean_chunks)}, top_k={top_k}"
        )
        with httpx.Client(timeout=RERANK_TIMEOUT_SECONDS) as client:
            response = client.post(
                DASHSCOPE_RERANK_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {RERANK_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            print(f"[rerank] qwen3-rerank status_code={response.status_code}")
            if response.status_code != 200:
                print(f"[rerank] qwen3-rerank response preview={response.text[:500]}")
                logger.warning(
                    "dashscope rerank HTTP %d: %s",
                    response.status_code,
                    response.text[:500],
                )
                return None, empty_usage
            data = response.json()

        # 只提取接口返回的官方 token usage；没有 usage 时保持 0，不做估算。
        token_usage, has_official_usage = _extract_rerank_token_usage(data)
        usage_source = "api" if has_official_usage else "none"
        print(
            "[rerank] qwen3-rerank token: "
            f"prompt={token_usage['prompt_tokens']}, "
            f"completion={token_usage['completion_tokens']}, "
            f"source={usage_source}"
        )
        if not has_official_usage:
            print(
                "[rerank] qwen3-rerank response has no official usage field; "
                "precise token count is unavailable from this response."
            )
        if token_usage["prompt_tokens"] or token_usage["completion_tokens"]:
            logger.info(
                "dashscope rerank token: prompt=%d, completion=%d",
                token_usage["prompt_tokens"],
                token_usage["completion_tokens"],
            )

        # 兼容两种响应格式
        results = data.get("output", {}).get("results", []) or data.get("results", [])
        if not results:
            print(
                "[rerank] qwen3-rerank empty results, "
                f"response preview={json.dumps(data, ensure_ascii=False)[:500]}"
            )
            logger.warning("dashscope rerank empty results, response: %s", json.dumps(data, ensure_ascii=False)[:500])
            return None, token_usage

        scored = [
            (float(item.get("relevance_score", 0)), original_indices[int(item.get("index", 0))])
            for item in results
            if int(item.get("index", 0)) < len(original_indices)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        print(f"[rerank] qwen3-rerank success: results={len(scored)}")
        logger.info("dashscope rerank: query=%s, results=%d", query, len(scored))
        return scored, token_usage

    except Exception as exc:
        print(f"[rerank] qwen3-rerank failed: {type(exc).__name__}: {exc}")
        logger.warning("dashscope rerank failed: %s, falling back to rule-based", exc)
        return None, empty_usage


def _build_rerank_cache_key(query: str, chunks: list[dict[str, str]]) -> str:
    """根据 query 和 chunk 内容生成 rerank 缓存 key。"""
    """
query = " 大理 自然风景 "，_normalize_cache_text 处理后得到 "大理 自然风景"。

chunks = [{"source": "大理攻略.md", "title": "苍山"}, {"source": "大理攻略.md", "title": "洱海"}]

content_fingerprint = "大理攻略.md:苍山|大理攻略.md:洱海"

chunks_hash = hashlib.md5("大理攻略.md:苍山|大理攻略.md:洱海".encode()).hexdigest()[:12] → 假设得到 "a1b2c3d4e5f6"

最终缓存键："rerank:大理 自然风景:a1b2c3d4e5f6"
    """
    normalized_query = _normalize_cache_text(query)
    content_fingerprint = "|".join(
        f"{c.get('source', '')}:{c.get('title', '')}" for c in chunks
    )
    chunks_hash = hashlib.md5(content_fingerprint.encode()).hexdigest()[:12]
    return f"rerank:{normalized_query}:{chunks_hash}"


def rerank_guide_chunks(
    query: str,
    matched_chunks: list[dict[str, str]],
    top_k: int,
    destination: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """对召回候选做重排序，优先 Cross-encoder，fallback 规则级。返回 (chunks, rerank_token_usage)。"""
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}

    # 尝试从缓存读取 rerank 结果
    cache_key = _build_rerank_cache_key(query, matched_chunks)
    cached = get_cached_json(cache_key)
    if cached is not None:
        logger.info("rerank cache hit: query=%s", query)
        reranked: list[dict[str, str]] = []
        for item in cached:
            idx = item["i"]
            if 0 <= idx < len(matched_chunks):
                enriched = dict(matched_chunks[idx])
                enriched["rerank_score"] = item["s"]
                enriched["rerank_reasons"] = [f"cross-encoder:{item['s']:.4f}"]
                reranked.append(enriched)
        return reranked[:top_k], empty_usage
    logger.info("rerank cache miss: query=%s", query)

    # 优先尝试 DashScope Cross-encoder Rerank
    dashscope_results, rerank_token_usage = _rerank_with_dashscope(query, matched_chunks, top_k)
    if dashscope_results:
        print("[rerank] using qwen3-rerank results")
        # 写入缓存：只存索引和分数，不重复存文本
        cache_value = [
            {"i": idx, "s": round(score, 4)}
            for score, idx in dashscope_results
        ]
        set_cached_json(cache_key, cache_value, expire_seconds=REDIS_RERANK_TTL_SECONDS)

        reranked = []
        for score, original_index in dashscope_results:
            if 0 <= original_index < len(matched_chunks):
                enriched_chunk = dict(matched_chunks[original_index])
                enriched_chunk["rerank_score"] = round(score, 4)
                enriched_chunk["rerank_reasons"] = [f"cross-encoder:{score:.4f}"]
                reranked.append(enriched_chunk)
        return reranked[:top_k], rerank_token_usage

    # fallback 到规则级 Rerank
    print("[rerank] qwen3-rerank unavailable, using rule-based rerank")
    logger.info("rerank_guide_chunks: using rule-based rerank")
    scored_chunks: list[tuple[int, int, dict[str, str]]] = []
    for index, chunk in enumerate(matched_chunks):
        enriched_chunk = dict(chunk)
        score = _score_chunk_for_rerank(query, enriched_chunk, destination=destination)
        enriched_chunk["rerank_score"] = score
        scored_chunks.append((score, -index, enriched_chunk))

    scored_chunks.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [chunk for _, _, chunk in scored_chunks[:top_k]], empty_usage


def retrieve_travel_guide_chunks(
    query: str, top_k: int = 3, destination: str | None = None
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """返回带轻量 rerank 的原始攻略片段。返回 (chunks, rerank_token_usage)。"""
    candidate_k = max(top_k * 2, 6)
    matched_chunks = search_guide_chunks(query=query, top_k=candidate_k)
    return rerank_guide_chunks(
        query=query, matched_chunks=matched_chunks, top_k=top_k, destination=destination
    )


def retrieve_travel_guide(query: str, top_k: int = 3) -> tuple[list[str], dict[str, int]]:
    """返回最相关的攻略片段。返回 (texts, rerank_token_usage)。"""
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    cache_key = f"rag:guide:{_normalize_cache_text(query)}:{top_k}"
    cached_value = get_cached_json(cache_key)
    if cached_value is not None:
        logger.info("rag cache hit: query=%s top_k=%s", query, top_k)
        return [str(item) for item in cached_value], empty_usage
    logger.info("rag cache miss: query=%s top_k=%s", query, top_k)

    matched_chunks, rerank_usage = retrieve_travel_guide_chunks(query=query, top_k=top_k)

    results: list[str] = []
    for chunk in matched_chunks:
        results.append(
            f"[来源: {chunk['source']} | 标题: {chunk['title']}]\n{chunk['text']}"
        )

    set_cached_json(cache_key, results, expire_seconds=REDIS_RAG_TTL_SECONDS)
    return results, rerank_usage
