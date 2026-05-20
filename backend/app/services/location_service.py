from __future__ import annotations

from app.models.schemas import LocationCandidate, SelectedLocation
from app.services.providers.amap_mcp_provider import get_amap_provider


async def search_location_candidates(
    keyword: str,
    city: str | None = None,
    limit: int = 8,
) -> list[LocationCandidate]:
    provider = get_amap_provider()
    return await provider.search_text(keyword=keyword, city=city, limit=limit)


async def reverse_geocode_location(longitude: float, latitude: float) -> SelectedLocation:
    provider = get_amap_provider()
    return await provider.reverse_geocode(longitude=longitude, latitude=latitude)

