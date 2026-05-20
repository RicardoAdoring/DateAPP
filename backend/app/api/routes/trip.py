import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import (
    Itinerary,
    TokenStatsResponse,
    TripDetailResponse,
    TripEditRequest,
    TripListResponse,
    TripRequest,
    TripSaveRequest,
)
from app.services.storage_service import (
    delete_itinerary_by_trip_id,
    get_itinerary_by_trip_id,
    get_token_stats,
    list_saved_itineraries,
    save_itinerary,
)
from app.services.trip_service import edit_trip_itinerary, generate_trip_itinerary


router = APIRouter(prefix="/trip", tags=["trip"])


@router.get("", response_model=TripListResponse)
def list_trips() -> TripListResponse:
    """返回已保存行程的摘要列表。"""
    return list_saved_itineraries()


@router.post("/generate", response_model=Itinerary)
def generate_trip(request: TripRequest) -> Itinerary:
    """生成结构化 itinerary。"""
    return generate_trip_itinerary(request)


@router.get("/stats", response_model=TokenStatsResponse)
def get_trip_token_stats() -> TokenStatsResponse:
    """返回所有已保存行程的 token 消耗统计。"""
    return get_token_stats()


@router.post("/edit", response_model=Itinerary)
def edit_trip(request: TripEditRequest) -> Itinerary:
    """根据用户编辑指令返回更新后的 itinerary。"""
    return edit_trip_itinerary(request)


def _json_line(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, default=str) + "\n"


async def _trip_edit_event_stream(request: TripEditRequest) -> AsyncIterator[str]:
    yield _json_line(
        {
            "type": "stage",
            "title": "理解调整要求",
            "content": f"正在读取修改指令：{request.user_instruction}",
            "data": {
                "trip_id": request.trip_id,
                "edit_scope": request.edit_scope,
                "preserve_constraints": request.preserve_constraints,
            },
        }
    )
    yield _json_line(
        {
            "type": "thought",
            "title": "约束已锁定",
            "content": "会尽量保留中心点、预算结构和既有路线骨架，只调整用户指定的部分。",
        }
    )
    yield _json_line(
        {
            "type": "stage",
            "title": "调用模型调整",
            "content": "正在生成新的安排，并重新刷新预算与可用地图信息。",
        }
    )

    task = asyncio.create_task(asyncio.to_thread(edit_trip_itinerary, request))
    elapsed_seconds = 0
    while not task.done():
        await asyncio.sleep(5)
        elapsed_seconds += 5
        yield _json_line(
            {
                "type": "thought",
                "title": "仍在调整",
                "content": "模型和地图补全仍在工作，正在等待最终结构化 itinerary。",
                "data": {"elapsed_seconds": elapsed_seconds},
            }
        )

    try:
        itinerary = await task
    except Exception as exc:  # pragma: no cover - defensive stream boundary
        yield _json_line(
            {
                "type": "error",
                "title": "调整失败",
                "content": str(exc),
            }
        )
        return

    yield _json_line(
        {
            "type": "stage",
            "title": "输出调整结果",
            "content": "新的路线结构已生成，正在逐步展开调整后的停靠点。",
        }
    )

    for day in itinerary.days:
        timeline_items = [
            {
                "kind": "activity",
                "name": spot.name,
                "start_time": spot.start_time,
                "end_time": spot.end_time,
                "address": spot.address or spot.location,
                "estimated_cost": spot.estimated_cost,
                "content": spot.description or "活动安排已更新。",
            }
            for spot in day.spots
        ] + [
            {
                "kind": "meal",
                "name": meal.name,
                "start_time": meal.start_time,
                "end_time": meal.end_time,
                "address": meal.address or meal.location,
                "estimated_cost": meal.estimated_cost,
                "content": meal.notes or "餐饮安排已更新。",
            }
            for meal in day.meals
        ]
        timeline_items.sort(key=lambda item: item.get("start_time") or "99:99")
        for item in timeline_items:
            yield _json_line(
                {
                    "type": "plan_item",
                    "title": str(item["name"]),
                    "content": str(item["content"]),
                    "data": item,
                }
            )

        for transport in day.transport:
            distance_text = (
                f"{transport.distance_km} km"
                if transport.distance_km is not None
                else "距离待估"
            )
            yield _json_line(
                {
                    "type": "route",
                    "title": f"{transport.from_place or '上一站'} → {transport.to_place or '下一站'}",
                    "content": (
                        f"{transport.mode} · "
                        f"{distance_text} · "
                        f"{transport.duration or '耗时待估'}"
                    ),
                    "data": transport.model_dump(mode="json"),
                }
            )

    yield _json_line(
        {
            "type": "complete",
            "title": "路线已调整完成",
            "content": "完整 itinerary 已更新，可以进入结果页继续查看、保存或导出。",
            "itinerary": itinerary.model_dump(mode="json"),
        }
    )


@router.post("/edit/stream")
async def edit_trip_stream(request: TripEditRequest) -> StreamingResponse:
    """根据用户编辑指令流式返回调整过程和最终 itinerary。"""
    return StreamingResponse(
        _trip_edit_event_stream(request),
        media_type="application/x-ndjson; charset=utf-8",
    )


@router.post("/save")
def save_trip(request: TripSaveRequest) -> dict[str, str]:
    """保存 itinerary，并返回 trip_id。"""
    saved_trip_id = save_itinerary(request.itinerary)
    return {
        "message": "Trip itinerary saved successfully.",
        "trip_id": saved_trip_id,
    }


@router.get("/{trip_id}", response_model=TripDetailResponse)
def get_trip_detail(trip_id: str) -> TripDetailResponse:
    """根据 trip_id 查询已保存 itinerary。"""
    trip_detail = get_itinerary_by_trip_id(trip_id)
    if trip_detail is None:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return trip_detail


@router.delete("/{trip_id}")
def delete_trip(trip_id: str) -> dict[str, str]:
    """根据 trip_id 删除已保存 itinerary。"""
    deleted = delete_itinerary_by_trip_id(trip_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Trip not found.")
    return {
        "message": "Trip itinerary deleted successfully.",
        "trip_id": trip_id,
    }
