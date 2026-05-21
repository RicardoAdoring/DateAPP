import logging

from app.agents.llm_clients import (
    add_token_usage,
    build_openai_compatible_chat_llm,
    extract_token_usage,
    response_content_text,
)
from app.config import (
    OLLAMA_FALLBACK_API_KEY,
    OLLAMA_FALLBACK_BASE_URL,
    OLLAMA_FALLBACK_ENABLED,
    OLLAMA_FALLBACK_MAX_RETRIES,
    OLLAMA_FALLBACK_MODEL,
    OLLAMA_FALLBACK_TIMEOUT_SECONDS,
    QUERY_REWRITE_LLM_API_KEY,
    QUERY_REWRITE_LLM_BASE_URL,
    QUERY_REWRITE_LLM_MAX_RETRIES,
    QUERY_REWRITE_LLM_MODEL,
    QUERY_REWRITE_LLM_TIMEOUT_SECONDS,
)
from app.rag.retriever import retrieve_travel_guide


logger = logging.getLogger(__name__)


# rag_tool.py 自己不直接检索，
# 它只负责把"旅行规划语义"转成"检索查询"。
def _append_unique(parts: list[str], value: str) -> None:
    normalized = value.strip()
    if not normalized:
        return
    if normalized not in parts:
        parts.append(normalized)


def _extract_note_keywords(special_notes: str | None, destination: str | None = None) -> list[str]:
    """从用户备注里提炼更适合检索的关键词，而不是直接拼整句。"""
    if not special_notes:
        return []

    keywords: list[str] = []
    note = special_notes.strip()

    # 格式：(触发词, 目的地过滤, 输出关键词)
    # 目的地为 None 表示通用，不限目的地
    rule_keywords = [
        (("日落", "傍晚"), "大理", ["日落", "傍晚", "洱海", "双廊"]),
        (("日出", "清晨"), "大理", ["日出", "才村", "龙龛"]),
        (("拍照", "出片", "摄影"), None, ["拍照", "摄影", "出片"]),
        (("美食", "小吃", "吃"), None, ["美食", "小吃"]),
        (("轻松", "慢节奏", "休闲"), None, ["轻松", "慢节奏", "休闲"]),
        (("不想太早起床", "睡到自然醒"), None, ["轻松", "慢节奏"]),
        (("古镇",), "大理", ["古镇", "大理古城", "喜洲古镇"]),
        (("古镇",), "西安", ["古镇", "回民街"]),
        (("古镇",), "厦门", ["古镇", "鼓浪屿", "曾厝垵"]),
        (("骑行",), "大理", ["骑行", "洱海生态廊道"]),
        (("骑行",), "厦门", ["骑行", "环岛路"]),
        (("熊猫", "大熊猫"), "成都", ["大熊猫", "熊猫"]),
        (("潜水",), "三亚", ["潜水", "蜈支洲岛"]),
        (("海鲜",), "三亚", ["海鲜", "第一市场"]),
    ]

    for triggers, required_dest, values in rule_keywords:
        if required_dest and destination and required_dest not in destination:
            continue
        if any(trigger in note for trigger in triggers):
            for value in values:
                _append_unique(keywords, value)

    return keywords


def _build_chat_llm():
    """创建 ChatOpenAI 实例，用于 Query Rewrite。"""
    return build_openai_compatible_chat_llm(
        model=QUERY_REWRITE_LLM_MODEL,
        api_key=QUERY_REWRITE_LLM_API_KEY,
        base_url=QUERY_REWRITE_LLM_BASE_URL,
        timeout=QUERY_REWRITE_LLM_TIMEOUT_SECONDS,
        max_retries=QUERY_REWRITE_LLM_MAX_RETRIES,
        temperature=0.2,
    )


def _build_ollama_fallback_llm():
    """创建 Ollama OpenAI-compatible fallback 实例，用于 Query Rewrite。"""
    if not OLLAMA_FALLBACK_ENABLED:
        return None
    return build_openai_compatible_chat_llm(
        model=OLLAMA_FALLBACK_MODEL,
        api_key=OLLAMA_FALLBACK_API_KEY,
        base_url=OLLAMA_FALLBACK_BASE_URL,
        timeout=OLLAMA_FALLBACK_TIMEOUT_SECONDS,
        max_retries=OLLAMA_FALLBACK_MAX_RETRIES,
        temperature=0.2,
    )


def _extract_token_usage(response) -> dict[str, int]:
    """从 LangChain AIMessage 中提取 token 使用量。"""
    return extract_token_usage(response)


def llm_rewrite_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> tuple[str | None, dict[str, int]]:
    """用 LLM 把用户旅行需求改写成适合向量检索的 query。返回 (query, token_usage)。"""
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    llm = _build_chat_llm()
    if llm is None:
        return None, empty_usage

    system_prompt = (
        "你是一个 RAG 检索 query 改写专家。"
        "你的任务是把用户的旅行需求改写成适合向量检索的关键词组合。"
        "输出要求："
        "1. 只输出检索关键词，用空格分隔"
        "2. 不要输出解释、标点或任何多余文字"
        "3. 关键词要具体，优先包含景点名称、活动类型、场景特征"
        "4. 包含目的地城市名"
    )

    parts = [f"目的地：{destination}"]
    if preferences:
        parts.append(f"偏好：{'、'.join(preferences)}")
    if pace:
        parts.append(f"节奏：{pace}")
    if special_notes:
        parts.append(f"备注：{special_notes}")
    human_prompt = "\n".join(parts)

    messages = [
        ("system", system_prompt),
        ("human", human_prompt),
    ]
    total_usage = dict(empty_usage)
    fallback_tried = False
    attempts = [("DeepSeek", llm)]

    while attempts:
        provider_name, current_llm = attempts.pop(0)
        try:
            response = current_llm.invoke(messages)
        except Exception:
            logger.warning(
                "llm_rewrite_query failed with %s, trying fallback if available",
                provider_name,
                exc_info=True,
            )
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    logger.info("llm_rewrite_query: trying Ollama fallback")
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage

        token_usage = _extract_token_usage(response)
        total_usage = add_token_usage(total_usage, token_usage)
        raw_text = response_content_text(response)
        query = raw_text.strip()
        if query:
            logger.info(
                "llm_rewrite_query: provider=%s input=%s -> output=%s",
                provider_name,
                human_prompt,
                query,
            )
            return query, total_usage

        logger.warning("llm_rewrite_query returned empty output from %s", provider_name)
        if not fallback_tried:
            fallback_tried = True
            fallback_llm = _build_ollama_fallback_llm()
            if fallback_llm is not None:
                logger.info("llm_rewrite_query: trying Ollama fallback for empty output")
                attempts.append(("Ollama", fallback_llm))
                continue
        return None, total_usage

    return None, total_usage


def _rule_based_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> str:
    """规则级 Query Rewrite，作为 LLM Rewrite 的 fallback。"""
    parts: list[str] = [destination]

    if preferences:
        for preference in preferences:
            _append_unique(parts, preference)

    if pace:
        _append_unique(parts, pace)

    for keyword in _extract_note_keywords(special_notes, destination=destination):
        _append_unique(parts, keyword)

    for stable_term in ["景点", "行程", "攻略", "推荐"]:
        _append_unique(parts, stable_term)

    return " ".join(part for part in parts if part).strip()


def build_destination_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> tuple[str, dict[str, int]]:
    """把目的地、偏好、节奏和备注改写成更贴近检索场景的 query。返回 (query, token_usage)。"""
    llm_query, token_usage = llm_rewrite_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    )
    if llm_query:
        return llm_query, token_usage

    logger.info("build_destination_query: LLM rewrite unavailable, using rule-based")
    return _rule_based_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    ), {"prompt_tokens": 0, "completion_tokens": 0}


def _build_destination_query(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
) -> tuple[str, dict[str, int]]:
    """兼容旧调用，内部转到公开的 query 构造函数。"""
    return build_destination_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    )


def get_destination_guide_context(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
    top_k: int = 5,
) -> tuple[list[str], dict[str, int], dict[str, int]]:
    """根据目的地和偏好返回本地攻略里的相关片段。返回 (contexts, rewrite_token_usage, rerank_token_usage)。"""
    query, rewrite_usage = build_destination_query(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
    )
    contexts, rerank_usage = retrieve_travel_guide(query=query, top_k=top_k)
    return contexts, rewrite_usage, rerank_usage
