from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models.schemas import DatePlanRequest, Itinerary
from app.services.date_plan_service import generate_date_plan, generate_date_plan_with_progress
from app.services.providers.amap_mcp_provider import AmapMcpError


router = APIRouter(prefix="/date-plan", tags=["date-plan"])


@router.post("/generate", response_model=Itinerary)
async def generate_date_plan_route(request: DatePlanRequest) -> Itinerary:
    try:
        return await generate_date_plan(request)
    except AmapMcpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _json_line(event: dict[str, Any]) -> str:
    return json.dumps(event, ensure_ascii=False, default=str) + "\n"


async def _date_plan_event_stream(request: DatePlanRequest) -> AsyncIterator[str]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def progress(event: dict[str, Any]) -> None:
        await queue.put(event)

    task = asyncio.create_task(generate_date_plan_with_progress(request, progress))

    while not task.done() or not queue.empty():
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.2)
        except TimeoutError:
            continue
        yield _json_line(event)

    try:
        itinerary = await task
    except AmapMcpError as exc:
        yield _json_line(
            {
                "type": "error",
                "title": "地图工具不可用",
                "content": str(exc),
            }
        )
    except Exception as exc:  # pragma: no cover - defensive stream boundary
        yield _json_line(
            {
                "type": "error",
                "title": "生成失败",
                "content": str(exc),
            }
        )
    else:
        yield _json_line(
            {
                "type": "complete",
                "title": "约会路线已完成",
                "content": "完整 itinerary 已生成，可以进入结果页查看地图、预算和导出。",
                "itinerary": itinerary.model_dump(mode="json"),
            }
        )


@router.post("/generate/stream")
async def generate_date_plan_stream(request: DatePlanRequest) -> StreamingResponse:
    return StreamingResponse(
        _date_plan_event_stream(request),
        media_type="application/x-ndjson; charset=utf-8",
    )
