from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.agents.llm_clients import (
    add_token_usage,
    build_openai_compatible_chat_llm,
    extract_token_usage,
    response_content_text,
)
from app.agents.tools.rag_tool import get_destination_guide_context
from app.config import (
    OLLAMA_FALLBACK_API_KEY,
    OLLAMA_FALLBACK_BASE_URL,
    OLLAMA_FALLBACK_ENABLED,
    OLLAMA_FALLBACK_MAX_RETRIES,
    OLLAMA_FALLBACK_MODEL,
    OLLAMA_FALLBACK_TIMEOUT_SECONDS,
    PLANNER_LLM_API_KEY,
    PLANNER_LLM_BASE_URL,
    PLANNER_LLM_MAX_RETRIES,
    PLANNER_LLM_MODEL,
    PLANNER_LLM_TIMEOUT_SECONDS,
)
from app.models.schemas import DayPlan, TripEditRequest, TripRequest


class PlannerDayDraft(BaseModel):
    """LLM 返回的单日最小行程草稿。"""

    day_index: int = Field(..., ge=1)
    theme: str = Field(..., description="当天的简短主题")
    spot_name: str = Field(..., description="当天主要景点名称")
    spot_description: str = Field(..., description="推荐该景点的简短理由")
    meal_name: str = Field(..., description="当天的餐饮或餐厅建议")
    meal_notes: str = Field(..., description="简短的用餐说明")
    daily_note: str = Field(..., description="当天的一条简短规划备注")


class PlannerDraft(BaseModel):
    """提供给 trip_service.py 使用的结构化行程草稿。"""

    summary: str = Field(..., description="整趟旅行的简短概述")
    tips: list[str] = Field(default_factory=list, description="旅行提示")
    days: list[PlannerDayDraft] = Field(default_factory=list)


class DayEditDraft(BaseModel):
    """LLM 返回的单日编辑草稿。"""

    theme: str = Field(..., description="编辑后的当天主题")
    spot_name: str = Field(..., description="编辑后的主要景点名称")
    spot_description: str = Field(..., description="编辑后的景点说明")
    meal_name: str = Field(..., description="编辑后的餐饮名称")
    meal_notes: str = Field(..., description="编辑后的餐饮说明")
    daily_note: str = Field(..., description="编辑后的当天备注")


def _normalize_day_edit_payload(payload: dict) -> dict:
    """兼容模型返回的两种单日编辑格式。"""
    if "spot_name" in payload and "meal_name" in payload and "daily_note" in payload:
        return payload

    normalized = dict(payload)

    spots = payload.get("spots")
    if isinstance(spots, list) and spots:
        first_spot = spots[0] or {}
        normalized.setdefault("spot_name", first_spot.get("name", ""))
        normalized.setdefault("spot_description", first_spot.get("description", ""))

    meals = payload.get("meals")
    if isinstance(meals, list) and meals:
        first_meal = meals[0] or {}
        normalized.setdefault("meal_name", first_meal.get("name", ""))
        normalized.setdefault("meal_notes", first_meal.get("notes", ""))

    notes = payload.get("notes")
    if isinstance(notes, list) and notes:
        normalized.setdefault("daily_note", notes[-1] or "")

    return normalized


def _extract_json_object(raw_text: str) -> str | None:
    """从模型原始文本中尽量提取 JSON 对象字符串。"""
    text = raw_text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    start_index = text.find("{")
    end_index = text.rfind("}")
    if start_index == -1 or end_index == -1 or end_index <= start_index:
        return None

    return text[start_index : end_index + 1]


def collect_trip_context(
    destination: str,
    preferences: list[str] | None = None,
    pace: str | None = None,
    special_notes: str | None = None,
    top_k: int = 5,
) -> tuple[list[str], dict[str, int], dict[str, int]]:
    """收集生成行程时需要参考的本地攻略片段。返回 (contexts, rewrite_token_usage, rerank_token_usage)。"""
    return get_destination_guide_context(
        destination=destination,
        preferences=preferences,
        pace=pace,
        special_notes=special_notes,
        top_k=top_k,
    )


def _build_chat_llm(temperature: float = 0.3):
    """创建通用 ChatOpenAI 实例。"""
    return build_openai_compatible_chat_llm(
        model=PLANNER_LLM_MODEL,
        api_key=PLANNER_LLM_API_KEY,
        base_url=PLANNER_LLM_BASE_URL,
        timeout=PLANNER_LLM_TIMEOUT_SECONDS,
        max_retries=PLANNER_LLM_MAX_RETRIES,
        temperature=temperature,
    )


def _build_ollama_fallback_llm(temperature: float = 0.3):
    """创建 Ollama OpenAI-compatible fallback 实例。"""
    if not OLLAMA_FALLBACK_ENABLED:
        return None
    return build_openai_compatible_chat_llm(
        model=OLLAMA_FALLBACK_MODEL,
        api_key=OLLAMA_FALLBACK_API_KEY,
        base_url=OLLAMA_FALLBACK_BASE_URL,
        timeout=OLLAMA_FALLBACK_TIMEOUT_SECONDS,
        max_retries=OLLAMA_FALLBACK_MAX_RETRIES,
        temperature=temperature,
    )


def _extract_token_usage(response) -> dict[str, int]:
    """从 LangChain AIMessage 中提取 token 使用量。"""
    return extract_token_usage(response)


def _extract_response_text(response) -> str:
    """把模型返回内容规范化为字符串。"""
    return response_content_text(response)


def _fallback_message(reason: str) -> None:
    print(
        "[trip_planner_agent] DeepSeek 链路不可用，"
        f"尝试调用 Ollama 本地模型。原因：{reason}"
    )


def generate_planner_draft(
    request: TripRequest,
    rag_contexts: list[str],
    day_count: int,
) -> tuple[PlannerDraft | None, dict[str, int]]:
    """
    使用 LangChain 生成结构化行程草稿。返回 (draft, token_usage)。

    如果当前环境还没有准备好模型调用条件，就返回 None，
    这样 service 层还能回退到规则版实现。
    """
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    llm = _build_chat_llm()
    if llm is None:
        return None, empty_usage

    guide_context = "\n\n".join(rag_contexts) if rag_contexts else "暂无本地攻略上下文。"

    system_prompt = (
        "你是一名旅行规划助手。"
        "请用中文生成简洁的结构化旅行草稿。"
        "需要遵守用户给出的目的地、预算、节奏和本地攻略上下文。"
        "你必须只输出一个 JSON 对象，不要输出 Markdown，不要输出解释文字，不要输出代码块。"
        "输出内容必须严格符合给定的结构化字段要求。"
        "如果用户在额外备注里提出了明确诉求，例如看日落、不想早起、少辣、拍照等，你要优先把这些诉求落实到具体某一天的主要景点或当天安排里，而不是只写成泛泛的提示。"
        "如果用户明确提到想看日落，请优先把适合看日落的地点安排为某一天的主要景点，或至少让当天主景点与日落安排保持强关联。"
    )

    human_prompt = f"""
目的地：{request.destination}
出发日期：{request.start_date.isoformat()}
结束日期：{request.end_date.isoformat()}
天数：{day_count}
人数：{request.travelers}
预算：{request.budget}
偏好：{'、'.join(request.preferences) if request.preferences else '无特别偏好'}
节奏：{request.pace or '适中'}
饮食偏好：{'、'.join(request.dietary_preferences) if request.dietary_preferences else '无'}
酒店档次：{request.hotel_level or '舒适型'}
额外备注：{request.special_notes or '无'}

本地攻略上下文：
{guide_context}

要求：
1. 输出一个整体 summary。
2. 输出 {day_count} 天的 daily draft。
3. 每天只给一个主要景点、一个餐饮建议和一条当天备注。
4. tips 保持简洁。
5. day_index 必须从 1 到 {day_count}。
6. 如果额外备注里有“想看日落”“不想早起”这类明确要求，必须在 days 中体现，不要只放到 tips。
7. 如果安排了看日落，当天的 spot_name 应尽量就是适合看日落的地点，或与 daily_note 中的日落安排保持一致，避免“主景点”和“日落地点”完全割裂。
8. 每天的安排要符合“轻松”节奏，避免过满、避免太早出发。
9. 餐饮建议尽量优先使用本地攻略上下文里已经出现的特色餐饮。
10. 只返回 JSON 对象，不要返回任何额外说明，不要使用 ```json 代码块。

JSON 结构示例：
{{
  "summary": "整体概述",
  "tips": ["提示1", "提示2"],
  "days": [
    {{
      "day_index": 1,
      "theme": "当天主题",
      "spot_name": "主要景点",
      "spot_description": "景点推荐理由",
      "meal_name": "餐饮名称",
      "meal_notes": "餐饮说明",
      "daily_note": "当天备注"
    }}
  ]
}}
"""

    print("[trip_planner_agent] 准备调用大模型...")
    print(f"[trip_planner_agent] model = {PLANNER_LLM_MODEL}")
    print(f"[trip_planner_agent] base_url = {PLANNER_LLM_BASE_URL or '<DEFAULT>'}")
    print(f"[trip_planner_agent] timeout = {PLANNER_LLM_TIMEOUT_SECONDS}s")
    print(f"[trip_planner_agent] max_retries = {PLANNER_LLM_MAX_RETRIES}")

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
        except Exception as exc:
            print(f"[trip_planner_agent] {provider_name} 调用失败: {type(exc).__name__}: {exc}")
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    _fallback_message(f"{provider_name} 调用异常")
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage

        token_usage = _extract_token_usage(response)
        total_usage = add_token_usage(total_usage, token_usage)
        print(
            f"[trip_planner_agent] {provider_name} 调用完成。"
            f"token: prompt={token_usage['prompt_tokens']}, completion={token_usage['completion_tokens']}"
        )

        raw_text = _extract_response_text(response)
        json_text = _extract_json_object(raw_text)
        if json_text is None:
            print(f"[trip_planner_agent] 未能从 {provider_name} 返回中提取 JSON。")
            print(f"[trip_planner_agent] 原始返回预览: {raw_text[:300]}")
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    _fallback_message(f"{provider_name} 返回非 JSON 内容")
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage

        try:
            result = PlannerDraft.model_validate(json.loads(json_text))
        except Exception as exc:
            print(f"[trip_planner_agent] {provider_name} JSON 解析失败: {type(exc).__name__}: {exc}")
            print(f"[trip_planner_agent] 原始返回预览: {raw_text[:300]}")
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    _fallback_message(f"{provider_name} JSON 解析失败")
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage

        if len(result.days) != day_count:
            print(
                f"[trip_planner_agent] {provider_name} 结构化结果天数不匹配，"
                f"expected={day_count}, actual={len(result.days)}"
            )
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    _fallback_message(f"{provider_name} 返回天数不匹配")
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage

        return result, total_usage

    return None, total_usage


def generate_day_edit_draft(
    request: TripEditRequest,
    target_day: DayPlan,
) -> tuple[DayEditDraft | None, dict[str, int]]:
    """
    使用 LLM 生成单日编辑草稿。返回 (draft, token_usage)。

    这个函数只负责产出目标那一天的编辑结果，
    最终如何合并回完整 itinerary 由 service 层处理。
    """
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    llm = _build_chat_llm()
    if llm is None:
        return None, empty_usage

    current_day_payload = {
        "day_index": target_day.day_index,
        "date": target_day.date.isoformat() if target_day.date else None,
        "theme": target_day.theme,
        "spots": [spot.model_dump(mode="json") for spot in target_day.spots],
        "meals": [meal.model_dump(mode="json") for meal in target_day.meals],
        "notes": list(target_day.notes),
    }

    current_itinerary_payload = request.current_itinerary.model_dump(mode="json")

    system_prompt = (
        "你是一名旅行行程编辑助手。"
        "请根据用户编辑指令，只重写目标那一天的核心安排。"
        "你必须只输出一个 JSON 对象，不要输出 Markdown，不要输出解释文字，不要输出代码块。"
        "编辑结果要尽量保留原 itinerary 的整体风格、预算结构和轻松程度。"
    )

    human_prompt = f"""
当前完整 itinerary：
{json.dumps(current_itinerary_payload, ensure_ascii=False, indent=2)}

需要重点编辑的目标 day：
{json.dumps(current_day_payload, ensure_ascii=False, indent=2)}

用户编辑指令：{request.user_instruction}
编辑范围：{request.edit_scope or '未指定'}
需要尽量保留的约束：{', '.join(request.preserve_constraints) if request.preserve_constraints else '无'}

要求：
1. 只输出目标那一天编辑后的结果。
2. 如果用户要求“更轻松”“不要安排太满”，请减少固定景点压力，让备注更自然。
3. 尽量延续原 itinerary 的城市、风格、餐饮语气和预算结构。
4. 不要输出额外字段。
5. 只返回 JSON 对象。

JSON 结构示例：
{{
  "theme": "编辑后的当天主题",
  "spot_name": "编辑后的主要景点",
  "spot_description": "编辑后的景点说明",
  "meal_name": "编辑后的餐饮名称",
  "meal_notes": "编辑后的餐饮说明",
  "daily_note": "编辑后的当天备注"
}}
"""

    print("[trip_planner_agent] 准备调用大模型进行单日编辑...")
    print(f"[trip_planner_agent] model = {PLANNER_LLM_MODEL}")
    print(f"[trip_planner_agent] base_url = {PLANNER_LLM_BASE_URL or '<DEFAULT>'}")

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
        except Exception as exc:
            print(f"[trip_planner_agent] {provider_name} 单日编辑调用失败: {type(exc).__name__}: {exc}")
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    _fallback_message(f"{provider_name} 单日编辑调用异常")
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage

        token_usage = _extract_token_usage(response)
        total_usage = add_token_usage(total_usage, token_usage)
        print(
            f"[trip_planner_agent] {provider_name} 单日编辑调用完成。"
            f"token: prompt={token_usage['prompt_tokens']}, completion={token_usage['completion_tokens']}"
        )

        raw_text = _extract_response_text(response)
        json_text = _extract_json_object(raw_text)
        if json_text is None:
            print(f"[trip_planner_agent] 未能从 {provider_name} 单日编辑结果中提取 JSON。")
            print(f"[trip_planner_agent] 原始返回预览: {raw_text[:300]}")
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    _fallback_message(f"{provider_name} 单日编辑返回非 JSON 内容")
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage

        try:
            payload = json.loads(json_text)
            if not isinstance(payload, dict):
                raise ValueError("单日编辑结果不是 JSON 对象。")
            normalized_payload = _normalize_day_edit_payload(payload)
            return DayEditDraft.model_validate(normalized_payload), total_usage
        except Exception as exc:
            print(f"[trip_planner_agent] {provider_name} 单日编辑 JSON 解析失败: {type(exc).__name__}: {exc}")
            print(f"[trip_planner_agent] 原始返回预览: {raw_text[:300]}")
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    _fallback_message(f"{provider_name} 单日编辑 JSON 解析失败")
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage

    return None, total_usage
