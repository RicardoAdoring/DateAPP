from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from app.agents.trip_planner_agent import (
    _build_ollama_fallback_llm,
    _build_chat_llm,
    _extract_json_object,
    _extract_response_text,
    _extract_token_usage,
)
from app.agents.llm_clients import add_token_usage
from app.models.schemas import (
    BudgetBreakdown,
    DatePlanRequest,
    DayPlan,
    Itinerary,
    MealItem,
    PlanSource,
    PoiCandidate,
    SelectedLocation,
    SpotItem,
    TokenUsage,
    TransportItem,
)
from app.services.providers.amap_mcp_provider import AmapMcpError, get_amap_provider
from app.services.providers.searchapi_provider import SearchApiError, get_search_provider


class DateStopDraft(BaseModel):
    kind: str = Field(..., description="activity/meal/cafe/night")
    name: str = Field(..., description="Stop name from candidates")
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    description: str = Field(..., description="Why this stop fits the date")
    estimated_cost: float = Field(default=0, ge=0)


class DatePlanDraft(BaseModel):
    summary: str
    tips: list[str] = Field(default_factory=list)
    stops: list[DateStopDraft] = Field(default_factory=list)


ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class CategoryQuery:
    category: str
    keyword: str


def _safe_slug(value: str) -> str:
    slug = re.sub(r"\s+", "_", value.strip())
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "", slug)
    return slug[:32] or "date_plan"


def _money(value: float | None) -> float:
    return round(max(value or 0.0, 0.0), 2)


def _category_queries(request: DatePlanRequest) -> list[CategoryQuery]:
    queries = [
        CategoryQuery("meal", "餐厅"),
        CategoryQuery("cafe", "咖啡 甜品"),
        CategoryQuery("activity", "景点"),
        CategoryQuery("activity", "公园"),
        CategoryQuery("activity", "博物馆 展览"),
        CategoryQuery("night", "商场 夜景"),
    ]
    preference_text = " ".join(request.preferences)
    if "电影" in preference_text:
        queries.append(CategoryQuery("activity", "电影院"))
    if "拍照" in preference_text:
        queries.append(CategoryQuery("activity", "拍照 打卡"))
    if "安静" in preference_text or "轻松" in preference_text:
        queries.append(CategoryQuery("cafe", "安静 咖啡"))
    return queries


def _candidate_key(candidate: PoiCandidate) -> str:
    if candidate.poi_id:
        return f"id:{candidate.poi_id}"
    return f"{candidate.name}:{candidate.address or ''}".lower()


def _to_poi(candidate: Any, category: str, source: str = "amap_mcp") -> PoiCandidate:
    if isinstance(candidate, PoiCandidate):
        data = candidate.model_dump()
        data["category"] = candidate.category or category
        data["source"] = candidate.source or source
        return PoiCandidate.model_validate(data)
    data = candidate.model_dump() if hasattr(candidate, "model_dump") else dict(candidate)
    data["category"] = category
    data.setdefault("source", source)
    return PoiCandidate.model_validate(data)


def _candidate_payload(candidate: PoiCandidate) -> dict[str, Any]:
    return {
        "name": candidate.name,
        "category": candidate.category,
        "address": candidate.address,
        "type": candidate.type,
        "rating": candidate.rating,
        "average_price": candidate.average_price,
        "latitude": candidate.latitude,
        "longitude": candidate.longitude,
        "poi_id": candidate.poi_id,
    }


def _match_candidate(name: str, candidates: list[PoiCandidate]) -> PoiCandidate | None:
    normalized = name.strip().lower()
    for candidate in candidates:
        if candidate.name.strip().lower() == normalized:
            return candidate
    for candidate in candidates:
        if normalized in candidate.name.strip().lower() or candidate.name.strip().lower() in normalized:
            return candidate
    return None


async def normalize_anchor(anchor: SelectedLocation) -> SelectedLocation:
    provider = get_amap_provider()
    if anchor.latitude is not None and anchor.longitude is not None:
        if anchor.address and anchor.city:
            return anchor
        try:
            resolved = await provider.reverse_geocode(anchor.longitude, anchor.latitude)
            return anchor.model_copy(
                update={
                    "address": anchor.address or resolved.address,
                    "province": anchor.province or resolved.province,
                    "city": anchor.city or resolved.city,
                    "district": anchor.district or resolved.district,
                    "name": anchor.name or resolved.name,
                }
            )
        except AmapMcpError:
            return anchor

    address = anchor.address or anchor.name
    if not address:
        raise AmapMcpError("Selected location must include coordinates or an address.")
    resolved = await provider.geocode(address=address, city=anchor.city)
    if resolved is None:
        raise AmapMcpError("Selected location cannot be geocoded.")
    return resolved


async def collect_date_candidates(request: DatePlanRequest) -> tuple[list[PoiCandidate], list[PlanSource]]:
    amap_provider = get_amap_provider()
    candidates: list[PoiCandidate] = []
    seen: set[str] = set()

    for query in _category_queries(request):
        raw_results = await amap_provider.search_around(
            longitude=request.anchor.longitude,
            latitude=request.anchor.latitude,
            radius_meters=request.radius_meters,
            keyword=query.keyword,
            limit=3,
        )
        for raw in raw_results:
            candidate = _to_poi(raw, category=query.category)
            key = _candidate_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)

    sources: list[PlanSource] = []
    try:
        search_provider = get_search_provider()
        city_text = request.anchor.city or request.anchor.address or request.anchor.name or ""
        search_query = f"{city_text} 约会 餐厅 景点 咖啡"
        for result in await search_provider.search_google_maps(search_query, city_text, limit=5):
            key = _candidate_key(result)
            if key not in seen:
                seen.add(key)
                candidates.append(result)
        sources.extend(await search_provider.search_web_sources(f"{city_text} 一日约会 攻略", limit=4))
    except SearchApiError:
        sources.append(
            PlanSource(
                title="SearchApi.io enrichment unavailable",
                snippet="SearchApi.io failed or is not configured; plan used AMap MCP candidates only.",
                source="searchapi",
            )
        )

    candidates = [candidate for candidate in candidates if candidate.latitude is not None and candidate.longitude is not None]
    if not candidates:
        raise AmapMcpError("No nearby POI candidates were found from AMap MCP.")
    return candidates, sources


def _choose(candidates: list[PoiCandidate], category: str, used: set[str]) -> PoiCandidate | None:
    for candidate in candidates:
        if candidate.category == category and _candidate_key(candidate) not in used:
            used.add(_candidate_key(candidate))
            return candidate
    for candidate in candidates:
        if _candidate_key(candidate) not in used:
            used.add(_candidate_key(candidate))
            return candidate
    return None


def _fallback_draft(request: DatePlanRequest, candidates: list[PoiCandidate]) -> DatePlanDraft:
    used: set[str] = set()
    schedule = [
        ("cafe", "cafe", "10:30", "11:20", "先用一杯咖啡进入轻松状态，适合聊天和确认当天节奏。"),
        ("activity", "activity", "11:40", "13:00", "安排一个不赶路的核心活动，兼顾散步、拍照和共同体验。"),
        ("meal", "meal", "13:10", "14:20", "午餐选择周边评价和位置都比较稳的餐厅，控制通勤时间。"),
        ("activity", "activity", "15:00", "17:10", "下午留给展览、公园或街区漫游，节奏更适合约会。"),
        ("meal", "meal", "18:00", "19:20", "晚餐作为当天的情绪收束，预算优先留给体验感。"),
        ("night", "night", "20:00", "21:20", "最后安排夜景或轻松散步，为一日约会留一个自然结尾。"),
    ]
    stops: list[DateStopDraft] = []
    for category, kind, start, end, reason in schedule:
        candidate = _choose(candidates, category, used)
        if candidate is None:
            continue
        base_cost = candidate.average_price if kind in {"meal", "cafe"} else None
        estimated_cost = base_cost or (120 if kind == "meal" else 60 if kind == "cafe" else 40)
        stops.append(
            DateStopDraft(
                kind=kind,
                name=candidate.name,
                start_time=start,
                end_time=end,
                description=reason,
                estimated_cost=_money(estimated_cost * request.travelers),
            )
        )
    preference_text = "、".join(request.preferences) if request.preferences else "轻松、好聊天、有记忆点"
    anchor_name = request.anchor.name or request.anchor.address or "选定地点"
    return DatePlanDraft(
        summary=f"围绕{anchor_name}安排的一日约会路线，重点是{preference_text}，尽量减少折返和长距离移动。",
        tips=[
            "热门餐厅建议提前确认排队和营业时间。",
            "每段活动之间预留 15-30 分钟缓冲，避免约会节奏太赶。",
            "如果当天降雨，可以优先保留咖啡、展览、商场和影院类室内点位。",
        ],
        stops=stops[:6],
    )


async def _emit_progress(
    progress: ProgressCallback | None,
    event_type: str,
    title: str,
    content: str,
    data: dict[str, Any] | None = None,
) -> None:
    if progress is None:
        return
    event: dict[str, Any] = {
        "type": event_type,
        "title": title,
        "content": content,
    }
    if data is not None:
        event["data"] = data
    await progress(event)


def _generate_llm_draft(
    request: DatePlanRequest,
    candidates: list[PoiCandidate],
    sources: list[PlanSource],
) -> tuple[DatePlanDraft | None, dict[str, int]]:
    empty_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    llm = _build_chat_llm()
    if llm is None:
        return None, empty_usage

    candidate_json = json.dumps(
        [_candidate_payload(candidate) for candidate in candidates[:28]],
        ensure_ascii=False,
        indent=2,
    )
    source_json = json.dumps(
        [source.model_dump(mode="json") for source in sources[:6]],
        ensure_ascii=False,
        indent=2,
    )
    system_prompt = (
        "你是一个中文约会路线规划 Agent。"
        "你只能使用候选 POI 里的地点名称来生成路线，不要编造不存在的地点。"
        "输出必须是严格 JSON 对象，不要 Markdown，不要代码块，不要额外解释。"
        "路线需要像一日约会：有聊天空间、活动变化、用餐、休息和自然收尾。"
    )
    human_prompt = f"""
中心点：{request.anchor.model_dump(mode="json")}
日期：{request.date.isoformat()}
时间：{request.start_time}-{request.end_time}
人数：{request.travelers}
预算：{request.budget}
交通：{request.transport_mode}
偏好：{"、".join(request.preferences) if request.preferences else "轻松、有氛围"}
饮食：{"、".join(request.dietary_preferences) if request.dietary_preferences else "无特别限制"}
备注：{request.special_notes or "无"}

候选 POI：
{candidate_json}

可参考来源：
{source_json}

要求：
1. 生成 4-6 个 stops，按时间排序。
2. kind 只能是 activity、meal、cafe、night。
3. name 必须完全来自候选 POI 的 name。
4. 覆盖至少一次正餐；如果时间覆盖晚上，尽量安排晚餐或夜间轻活动。
5. estimated_cost 是该 stop 对所有人的估算费用。
6. 返回 JSON：
{{
  "summary": "一句话概述",
  "tips": ["提示1", "提示2"],
  "stops": [
    {{
      "kind": "activity",
      "name": "候选 POI 名称",
      "start_time": "10:30",
      "end_time": "11:30",
      "description": "安排理由",
      "estimated_cost": 80
    }}
  ]
}}
"""
    messages = [("system", system_prompt), ("human", human_prompt)]
    total_usage = dict(empty_usage)
    fallback_tried = False
    attempts = [("DeepSeek", llm)]

    while attempts:
        provider_name, current_llm = attempts.pop(0)
        try:
            response = current_llm.invoke(messages)
        except Exception:
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage

        usage = _extract_token_usage(response)
        total_usage = add_token_usage(total_usage, usage)
        raw_text = _extract_response_text(response)
        json_text = _extract_json_object(raw_text)
        if json_text is None:
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage
        try:
            draft = DatePlanDraft.model_validate(json.loads(json_text))
        except Exception:
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage
        if not draft.stops:
            if not fallback_tried:
                fallback_tried = True
                fallback_llm = _build_ollama_fallback_llm()
                if fallback_llm is not None:
                    attempts.append(("Ollama", fallback_llm))
                    continue
            return None, total_usage
        return draft, total_usage

    return None, total_usage


def _spot_cost(candidate: PoiCandidate, draft: DateStopDraft) -> float:
    if draft.estimated_cost:
        return _money(draft.estimated_cost)
    if candidate.average_price:
        return _money(candidate.average_price)
    if candidate.category == "night":
        return 30
    return 50


async def _build_transports(
    anchor: SelectedLocation,
    ordered_candidates: list[PoiCandidate],
    transport_mode: str,
) -> list[TransportItem]:
    provider = get_amap_provider()
    transports: list[TransportItem] = []
    previous_name = anchor.name or anchor.address or "起点"
    previous_longitude = anchor.longitude
    previous_latitude = anchor.latitude

    route_mode = "walking" if transport_mode in {"walking", "walking_transit"} else "driving"
    for candidate in ordered_candidates:
        if candidate.longitude is None or candidate.latitude is None:
            continue
        try:
            route = await provider.estimate_route(
                origin_longitude=previous_longitude,
                origin_latitude=previous_latitude,
                destination_longitude=candidate.longitude,
                destination_latitude=candidate.latitude,
                mode=route_mode,
            )
        except AmapMcpError:
            route = None
        distance_km = route.get("distance_km") if route else None
        estimated_minutes = route.get("estimated_minutes") if route else None
        mode_text = "步行" if route_mode == "walking" else "打车"
        if route_mode == "walking":
            cost = 0.0
        elif distance_km is not None:
            cost = 10 + distance_km * 2.4
        else:
            cost = 20.0
        transports.append(
            TransportItem(
                mode=mode_text,
                from_place=previous_name,
                to_place=candidate.name,
                estimated_cost=_money(cost),
                duration=f"{estimated_minutes} 分钟" if estimated_minutes is not None else None,
                distance_km=distance_km,
                estimated_minutes=estimated_minutes,
            )
        )
        previous_name = candidate.name
        previous_longitude = candidate.longitude
        previous_latitude = candidate.latitude
    return transports


def _budget_breakdown(day: DayPlan) -> BudgetBreakdown:
    transport = _money(sum(item.estimated_cost for item in day.transport))
    meals = _money(sum(item.estimated_cost for item in day.meals))
    tickets = _money(sum(item.estimated_cost for item in day.spots))
    other = _money(max(20.0, (transport + meals + tickets) * 0.08))
    total = _money(transport + meals + tickets + other)
    return BudgetBreakdown(
        transport=transport,
        hotel=0.0,
        meals=meals,
        tickets=tickets,
        other=other,
        total=total,
    )


async def generate_date_plan_with_progress(
    request: DatePlanRequest,
    progress: ProgressCallback | None = None,
) -> Itinerary:
    await _emit_progress(
        progress,
        "stage",
        "确认中心点",
        "正在标准化用户选择的位置，补齐地址、城市和坐标信息。",
        {
            "anchor": request.anchor.model_dump(mode="json"),
        },
    )
    anchor = await normalize_anchor(request.anchor)
    request = request.model_copy(update={"anchor": anchor})

    await _emit_progress(
        progress,
        "thought",
        "中心点已确认",
        f"将围绕「{anchor.name or anchor.address or '已选位置'}」在 {request.radius_meters} 米内筛选适合约会的一日路线。",
        {
            "anchor": anchor.model_dump(mode="json"),
        },
    )

    await _emit_progress(
        progress,
        "stage",
        "收集附近候选",
        "正在通过高德 MCP 搜索餐厅、咖啡、景点、公园、展馆和夜间活动。",
    )
    candidates, sources = await collect_date_candidates(request)

    category_counts: dict[str, int] = {}
    for candidate in candidates:
        category_counts[candidate.category] = category_counts.get(candidate.category, 0) + 1
    await _emit_progress(
        progress,
        "thought",
        "候选池完成",
        f"已找到 {len(candidates)} 个可用地点，接下来会按时间、偏好和移动成本组合路线。",
        {
            "category_counts": category_counts,
            "source_count": len(sources),
        },
    )

    await _emit_progress(
        progress,
        "stage",
        "生成路线草案",
        "正在让 LLM 只基于候选 POI 输出严格 JSON，避免编造地点。",
    )
    llm_draft, usage = _generate_llm_draft(request, candidates, sources)
    draft = llm_draft or _fallback_draft(request, candidates)

    await _emit_progress(
        progress,
        "thought",
        "草案已生成",
        "LLM 草案可用。" if llm_draft is not None else "LLM 草案不可用，已切换为高德候选驱动的规则草案。",
        {
            "stop_count": len(draft.stops),
            "used_fallback": llm_draft is None,
        },
    )

    ordered_candidates: list[PoiCandidate] = []
    spots: list[SpotItem] = []
    meals: list[MealItem] = []
    used: set[str] = set()
    await _emit_progress(
        progress,
        "stage",
        "编排停靠点",
        "正在逐个匹配地点详情，生成餐饮、活动、夜间散步等时间节点。",
    )
    for stop in draft.stops[:6]:
        candidate = _match_candidate(stop.name, candidates)
        if candidate is None:
            continue
        key = _candidate_key(candidate)
        if key in used:
            continue
        used.add(key)
        ordered_candidates.append(candidate)
        if stop.kind in {"meal", "cafe"}:
            meal = MealItem(
                name=candidate.name,
                meal_type="咖啡休息" if stop.kind == "cafe" else "正餐",
                estimated_cost=_money(stop.estimated_cost or candidate.average_price or 100),
                notes=stop.description,
                start_time=stop.start_time,
                end_time=stop.end_time,
                location=candidate.type,
                image_url=candidate.image_url,
                address=candidate.address,
                latitude=candidate.latitude,
                longitude=candidate.longitude,
                poi_id=candidate.poi_id,
            )
            meals.append(meal)
            await _emit_progress(
                progress,
                "plan_item",
                meal.name,
                meal.notes or "餐饮节点已加入路线。",
                {
                    "kind": "meal",
                    "name": meal.name,
                    "start_time": meal.start_time,
                    "end_time": meal.end_time,
                    "address": meal.address,
                    "estimated_cost": meal.estimated_cost,
                    "latitude": meal.latitude,
                    "longitude": meal.longitude,
                },
            )
        else:
            spot = SpotItem(
                name=candidate.name,
                start_time=stop.start_time,
                end_time=stop.end_time,
                description=stop.description,
                estimated_cost=_spot_cost(candidate, stop),
                location=candidate.type,
                image_url=candidate.image_url,
                address=candidate.address,
                latitude=candidate.latitude,
                longitude=candidate.longitude,
                poi_id=candidate.poi_id,
            )
            spots.append(spot)
            await _emit_progress(
                progress,
                "plan_item",
                spot.name,
                spot.description or "活动节点已加入路线。",
                {
                    "kind": "activity",
                    "name": spot.name,
                    "start_time": spot.start_time,
                    "end_time": spot.end_time,
                    "address": spot.address,
                    "estimated_cost": spot.estimated_cost,
                    "latitude": spot.latitude,
                    "longitude": spot.longitude,
                },
            )

    if not ordered_candidates:
        raise AmapMcpError("Planner could not match any usable POI candidates.")

    await _emit_progress(
        progress,
        "stage",
        "计算相邻路线",
        "正在用高德 MCP 估算每两个停靠点之间的距离、耗时和交通方式。",
    )
    transports = await _build_transports(anchor, ordered_candidates, request.transport_mode)
    for transport in transports:
        distance_text = (
            f"{transport.distance_km} km"
            if transport.distance_km is not None
            else "距离待估"
        )
        await _emit_progress(
            progress,
            "route",
            f"{transport.from_place or '上一站'} → {transport.to_place or '下一站'}",
            f"{transport.mode} · {distance_text} · {transport.duration or '耗时待估'}",
            transport.model_dump(mode="json"),
        )

    await _emit_progress(
        progress,
        "stage",
        "汇总预算与来源",
        "正在整理预算拆分、提示和外部数据来源，准备输出完整 itinerary。",
    )
    day = DayPlan(
        day_index=1,
        date=request.date,
        theme="一日约会路线",
        spots=spots,
        meals=meals,
        hotel=None,
        transport=transports,
        notes=[
            f"中心点：{anchor.name or anchor.address or '已选位置'}",
            f"搜索半径：{request.radius_meters} 米",
            request.special_notes or "建议根据当天营业状态和排队情况微调停留时间。",
        ],
    )
    budget = _budget_breakdown(day)
    anchor_label = anchor.name or anchor.address or "选定地点"
    source_notes = [
        "Plan generated with AMap MCP provider.",
        "SearchApi.io enrichment was used when available.",
    ]
    if any(source.title == "SearchApi.io enrichment unavailable" for source in sources):
        source_notes.append("SearchApi.io enrichment unavailable; generated with AMap MCP only.")

    itinerary = Itinerary(
        trip_id=f"date_{_safe_slug(anchor_label)}_{request.date.isoformat()}",
        destination=anchor_label,
        summary=draft.summary,
        days=[day],
        estimated_budget=budget.total,
        budget_breakdown=budget,
        tips=draft.tips,
        source_notes=source_notes,
        source_links=sources,
        token_usage=TokenUsage(
            planner_prompt_tokens=usage.get("prompt_tokens", 0),
            planner_completion_tokens=usage.get("completion_tokens", 0),
        ),
    )
    return itinerary


async def generate_date_plan(request: DatePlanRequest) -> Itinerary:
    return await generate_date_plan_with_progress(request)
