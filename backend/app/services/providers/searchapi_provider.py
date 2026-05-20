from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import (
    SEARCHAPI_API_KEY,
    SEARCHAPI_BASE_URL,
    SEARCHAPI_TIMEOUT_SECONDS,
    SEARCHAPI_TTL_SECONDS,
)
from app.models.schemas import PlanSource, PoiCandidate
from app.services.cache_service import get_cached_json, set_cached_json


logger = logging.getLogger(__name__)


class SearchApiError(RuntimeError):
    """Raised when SearchApi.io cannot be reached or returns invalid data."""


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("$", "").replace("￥", "").strip())
    except (TypeError, ValueError):
        return None


def _first_image(item: dict[str, Any]) -> str | None:
    thumbnail = item.get("thumbnail") or item.get("image")
    if isinstance(thumbnail, str):
        return thumbnail
    images = item.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict):
            return first.get("thumbnail") or first.get("image") or first.get("url")
        if isinstance(first, str):
            return first
    return None


class SearchApiProvider:
    """SearchApi.io adapter used to enrich POI candidates."""

    async def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        if not SEARCHAPI_API_KEY:
            raise SearchApiError("SEARCHAPI_API_KEY is not configured.")

        cache_key = "searchapi:" + ":".join(
            f"{key}={_normalize(str(value))}" for key, value in sorted(params.items())
        )
        cached = get_cached_json(cache_key)
        if cached is not None:
            return cached

        request_params = {
            "api_key": SEARCHAPI_API_KEY,
            **params,
        }
        try:
            async with httpx.AsyncClient(timeout=SEARCHAPI_TIMEOUT_SECONDS) as client:
                response = await client.get(SEARCHAPI_BASE_URL, params=request_params)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("SearchApi request failed: params=%s error=%s", params, exc)
            raise SearchApiError("SearchApi.io request failed.") from exc

        if not isinstance(payload, dict):
            raise SearchApiError("SearchApi.io returned invalid JSON.")

        set_cached_json(cache_key, payload, SEARCHAPI_TTL_SECONDS)
        return payload

    async def search_google_maps(
        self,
        query: str,
        location_label: str | None = None,
        limit: int = 5,
    ) -> list[PoiCandidate]:
        params: dict[str, Any] = {
            "engine": "google_maps",
            "q": query,
        }
        if location_label:
            params["location"] = location_label

        payload = await self._request(params)
        raw_items = (
            payload.get("local_results")
            or payload.get("places")
            or payload.get("results")
            or []
        )
        results: list[PoiCandidate] = []
        for item in raw_items[:limit]:
            if not isinstance(item, dict):
                continue
            gps = item.get("gps_coordinates") or {}
            latitude = _parse_float(gps.get("latitude") or item.get("latitude"))
            longitude = _parse_float(gps.get("longitude") or item.get("longitude"))
            title = item.get("title") or item.get("name")
            if not title:
                continue
            results.append(
                PoiCandidate(
                    name=str(title),
                    address=item.get("address") or item.get("place"),
                    type=item.get("type"),
                    poi_id=item.get("place_id") or item.get("data_id"),
                    latitude=latitude,
                    longitude=longitude,
                    image_url=_first_image(item),
                    category="search",
                    rating=_parse_float(item.get("rating")),
                    average_price=_parse_float(item.get("price") or item.get("price_level")),
                    source="searchapi_google_maps",
                    source_url=item.get("link") or item.get("website"),
                )
            )
        return results

    async def search_web_sources(self, query: str, limit: int = 5) -> list[PlanSource]:
        payload = await self._request(
            {
                "engine": "google",
                "q": query,
            }
        )
        raw_items = payload.get("organic_results") or payload.get("results") or []
        sources: list[PlanSource] = []
        for item in raw_items[:limit]:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            if not title:
                continue
            sources.append(
                PlanSource(
                    title=str(title),
                    url=item.get("link"),
                    snippet=item.get("snippet"),
                    source="searchapi_google",
                )
            )
        return sources


_search_provider: SearchApiProvider | None = None


def get_search_provider() -> SearchApiProvider:
    global _search_provider
    if _search_provider is None:
        _search_provider = SearchApiProvider()
    return _search_provider

