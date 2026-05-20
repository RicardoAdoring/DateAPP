from __future__ import annotations

import json
import logging
import os
import shlex
from typing import Any

from app.config import (
    AMAP_API_KEY,
    AMAP_DEFAULT_CITY,
    MCP_AMAP_ARGS,
    MCP_AMAP_COMMAND,
    REDIS_MAP_TTL_SECONDS,
)
from app.models.schemas import LocationCandidate, SelectedLocation
from app.services.cache_service import get_cached_json, set_cached_json


logger = logging.getLogger(__name__)


class AmapMcpError(RuntimeError):
    """Raised when the AMap MCP server cannot satisfy a request."""


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, list):
        parts = [str(item).strip() for item in value if item not in (None, "")]
        return " ".join(part for part in parts if part) or None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _split_location(location: str | None) -> tuple[float | None, float | None]:
    if not location or "," not in location:
        return None, None
    longitude_text, latitude_text = location.split(",", 1)
    return _parse_float(latitude_text), _parse_float(longitude_text)


def _first_text_content(result: Any) -> str:
    content = getattr(result, "content", None) or []
    if not content:
        return ""
    first = content[0]
    if isinstance(first, dict):
        return str(first.get("text", ""))
    return str(getattr(first, "text", ""))


def _parse_tool_payload(result: Any) -> dict[str, Any]:
    if getattr(result, "isError", False):
        raise AmapMcpError(_first_text_content(result) or "AMap MCP tool returned an error.")

    raw_text = _first_text_content(result)
    if not raw_text:
        return {}
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AmapMcpError(f"AMap MCP returned non-JSON content: {raw_text[:160]}") from exc
    if not isinstance(payload, dict):
        return {}
    return payload


def _photo_url(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("url") or value.get("photo_url")
    if isinstance(value, list) and value:
        return _photo_url(value[0])
    return None


class AmapMcpProvider:
    """Thin async adapter over the official AMap MCP stdio server."""

    def __init__(self, command: str | None = None, args: str | None = None) -> None:
        self.command = command or MCP_AMAP_COMMAND
        self.args = args if args is not None else MCP_AMAP_ARGS

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not AMAP_API_KEY:
            raise AmapMcpError("AMAP_API_KEY is not configured.")

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:  # pragma: no cover - depends on deployment env
            raise AmapMcpError("Python package 'mcp' is not installed.") from exc

        env = os.environ.copy()
        env["AMAP_MAPS_API_KEY"] = AMAP_API_KEY
        server_params = StdioServerParameters(
            command=self.command,
            args=shlex.split(self.args) if self.args else [],
            env=env,
        )

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)
        except Exception as exc:  # pragma: no cover - exercised through integration tests
            logger.warning("AMap MCP tool call failed: tool=%s error=%s", tool_name, exc)
            raise AmapMcpError(f"AMap MCP tool call failed: {tool_name}") from exc

        return _parse_tool_payload(result)

    async def geocode(self, address: str, city: str | None = None) -> SelectedLocation | None:
        cache_key = f"amap_mcp:geo:{_normalize(address)}:{_normalize(city or AMAP_DEFAULT_CITY)}"
        cached = get_cached_json(cache_key)
        if cached is not None:
            return SelectedLocation.model_validate(cached)

        payload = await self._call_tool(
            "maps_geo",
            {
                "address": address,
                "city": city or AMAP_DEFAULT_CITY or "",
            },
        )
        results = payload.get("return") or []
        if not isinstance(results, list) or not results:
            return None

        first = results[0] or {}
        latitude, longitude = _split_location(first.get("location"))
        if latitude is None or longitude is None:
            return None

        city_value = first.get("city")
        if isinstance(city_value, list):
            city_value = city_value[0] if city_value else city
        location = SelectedLocation(
            name=address,
            address=address,
            province=_string_or_none(first.get("province")),
            city=_string_or_none(city_value or city),
            district=_string_or_none(first.get("district")),
            latitude=latitude,
            longitude=longitude,
        )
        set_cached_json(cache_key, location.model_dump(mode="json"), REDIS_MAP_TTL_SECONDS)
        return location

    async def reverse_geocode(self, longitude: float, latitude: float) -> SelectedLocation:
        cache_key = f"amap_mcp:regeo:{longitude:.6f},{latitude:.6f}"
        cached = get_cached_json(cache_key)
        if cached is not None:
            return SelectedLocation.model_validate(cached)

        payload = await self._call_tool(
            "maps_regeocode",
            {"location": f"{longitude},{latitude}"},
        )
        province = _string_or_none(payload.get("province") or payload.get("provice"))
        city = _string_or_none(payload.get("city"))
        district = _string_or_none(payload.get("district"))
        address = "".join(str(part) for part in (province, city, district) if part)
        location = SelectedLocation(
            name=address or "Selected location",
            address=address or None,
            province=province,
            city=city,
            district=district,
            latitude=latitude,
            longitude=longitude,
        )
        set_cached_json(cache_key, location.model_dump(mode="json"), REDIS_MAP_TTL_SECONDS)
        return location

    async def search_text(
        self,
        keyword: str,
        city: str | None = None,
        limit: int = 8,
    ) -> list[LocationCandidate]:
        cache_key = f"amap_mcp:text:{_normalize(keyword)}:{_normalize(city or AMAP_DEFAULT_CITY)}:{limit}"
        cached = get_cached_json(cache_key)
        if cached is not None:
            return [LocationCandidate.model_validate(item) for item in cached]

        payload = await self._call_tool(
            "maps_text_search",
            {
                "keywords": keyword,
                "city": city or AMAP_DEFAULT_CITY or "",
            },
        )
        pois = payload.get("pois") or []
        results = await self._hydrate_candidates(pois[:limit], city=city, limit=limit)
        set_cached_json(
            cache_key,
            [item.model_dump(mode="json") for item in results],
            REDIS_MAP_TTL_SECONDS,
        )
        return results

    async def search_around(
        self,
        longitude: float,
        latitude: float,
        radius_meters: int,
        keyword: str = "",
        limit: int = 8,
    ) -> list[LocationCandidate]:
        cache_key = (
            "amap_mcp:around:"
            f"{longitude:.6f},{latitude:.6f}:{radius_meters}:{_normalize(keyword)}:{limit}"
        )
        cached = get_cached_json(cache_key)
        if cached is not None:
            return [LocationCandidate.model_validate(item) for item in cached]

        payload = await self._call_tool(
            "maps_around_search",
            {
                "location": f"{longitude},{latitude}",
                "radius": str(radius_meters),
                "keywords": keyword,
            },
        )
        pois = payload.get("pois") or []
        results = await self._hydrate_candidates(pois[:limit], limit=limit)
        set_cached_json(
            cache_key,
            [item.model_dump(mode="json") for item in results],
            REDIS_MAP_TTL_SECONDS,
        )
        return results

    async def search_detail(self, poi_id: str) -> LocationCandidate | None:
        cache_key = f"amap_mcp:detail:{poi_id}"
        cached = get_cached_json(cache_key)
        if cached is not None:
            return LocationCandidate.model_validate(cached)

        payload = await self._call_tool("maps_search_detail", {"id": poi_id})
        latitude, longitude = _split_location(payload.get("location"))
        result = LocationCandidate(
            name=str(payload.get("name") or ""),
            address=_string_or_none(payload.get("address")),
            city=_string_or_none(payload.get("city")),
            type=_string_or_none(payload.get("type")),
            poi_id=payload.get("id") or poi_id,
            latitude=latitude,
            longitude=longitude,
            image_url=_photo_url(payload.get("photos")),
        )
        set_cached_json(cache_key, result.model_dump(mode="json"), REDIS_MAP_TTL_SECONDS)
        return result

    async def estimate_route(
        self,
        origin_longitude: float,
        origin_latitude: float,
        destination_longitude: float,
        destination_latitude: float,
        mode: str = "driving",
    ) -> dict[str, Any] | None:
        route_mode = "walking" if "walk" in mode or "步" in mode else "driving"
        cache_key = (
            "amap_mcp:route:"
            f"{route_mode}:{origin_longitude:.6f},{origin_latitude:.6f}:"
            f"{destination_longitude:.6f},{destination_latitude:.6f}"
        )
        cached = get_cached_json(cache_key)
        if cached is not None:
            return cached

        tool_name = "maps_direction_walking" if route_mode == "walking" else "maps_direction_driving"
        payload = await self._call_tool(
            tool_name,
            {
                "origin": f"{origin_longitude},{origin_latitude}",
                "destination": f"{destination_longitude},{destination_latitude}",
            },
        )
        route = payload.get("route") or {}
        paths = route.get("paths") or []
        if not paths:
            return None
        first_path = paths[0]
        distance_meters = _parse_float(first_path.get("distance"))
        duration_seconds = _parse_float(first_path.get("duration"))
        result = {
            "distance_meters": distance_meters,
            "distance_km": round(distance_meters / 1000, 2) if distance_meters is not None else None,
            "duration_seconds": duration_seconds,
            "estimated_minutes": round(duration_seconds / 60) if duration_seconds is not None else None,
            "mode": "步行" if route_mode == "walking" else "打车",
        }
        set_cached_json(cache_key, result, REDIS_MAP_TTL_SECONDS)
        return result

    async def _hydrate_candidates(
        self,
        raw_pois: list[dict[str, Any]],
        city: str | None = None,
        limit: int = 8,
    ) -> list[LocationCandidate]:
        results: list[LocationCandidate] = []
        for poi in raw_pois:
            poi_id = poi.get("id")
            detailed = None
            if poi_id:
                try:
                    detailed = await self.search_detail(str(poi_id))
                except AmapMcpError:
                    detailed = None

            if detailed is not None:
                if not detailed.city:
                    detailed.city = city
                results.append(detailed)
            else:
                latitude, longitude = _split_location(poi.get("location"))
                results.append(
                    LocationCandidate(
                        name=str(poi.get("name") or ""),
                        address=_string_or_none(poi.get("address")),
                        city=_string_or_none(city),
                        type=_string_or_none(poi.get("type") or poi.get("typecode")),
                        poi_id=poi_id,
                        latitude=latitude,
                        longitude=longitude,
                        image_url=_photo_url(poi.get("photos")),
                    )
                )

            if len(results) >= limit:
                break
        return [item for item in results if item.name]


_amap_provider: AmapMcpProvider | None = None


def get_amap_provider() -> AmapMcpProvider:
    global _amap_provider
    if _amap_provider is None:
        _amap_provider = AmapMcpProvider()
    return _amap_provider
