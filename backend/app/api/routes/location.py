from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import LocationCandidate, SelectedLocation
from app.services.location_service import (
    reverse_geocode_location,
    search_location_candidates,
)
from app.services.providers.amap_mcp_provider import AmapMcpError


router = APIRouter(prefix="/location", tags=["location"])


@router.get("/search", response_model=list[LocationCandidate])
async def search_location(
    keyword: str = Query(..., min_length=1),
    city: str | None = Query(default=None),
    limit: int = Query(default=8, ge=1, le=20),
) -> list[LocationCandidate]:
    try:
        return await search_location_candidates(keyword=keyword, city=city, limit=limit)
    except AmapMcpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/reverse-geocode", response_model=SelectedLocation)
async def reverse_geocode(
    longitude: float = Query(..., ge=-180, le=180),
    latitude: float = Query(..., ge=-90, le=90),
) -> SelectedLocation:
    try:
        return await reverse_geocode_location(longitude=longitude, latitude=latitude)
    except AmapMcpError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

