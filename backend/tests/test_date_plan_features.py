from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
import sys

from fastapi.testclient import TestClient


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.main import app  # noqa: E402
import app.api.routes.date_plan as date_plan_route  # noqa: E402
import app.api.routes.location as location_route  # noqa: E402
from app.models.schemas import (  # noqa: E402
    BudgetBreakdown,
    DatePlanRequest,
    DayPlan,
    Itinerary,
    LocationCandidate,
    MealItem,
    PlanSource,
    SelectedLocation,
    SpotItem,
)
from app.services import date_plan_service  # noqa: E402
from app.services.providers.amap_mcp_provider import AmapMcpProvider  # noqa: E402
from app.services.providers.searchapi_provider import SearchApiProvider  # noqa: E402


client = TestClient(app)


def build_anchor() -> SelectedLocation:
    return SelectedLocation(
        name="The Bund",
        address="Shanghai Huangpu District",
        city="Shanghai",
        latitude=31.2397,
        longitude=121.4998,
        poi_id="anchor_001",
    )


def build_date_itinerary() -> Itinerary:
    return Itinerary(
        trip_id="date_demo_2026-05-20",
        destination="The Bund",
        summary="A relaxed one-day date route.",
        days=[
            DayPlan(
                day_index=1,
                date="2026-05-20",
                theme="Date route",
                spots=[
                    SpotItem(
                        name="Riverside Walk",
                        start_time="15:00",
                        end_time="16:30",
                        description="Walk and photos.",
                        latitude=31.24,
                        longitude=121.5,
                    )
                ],
                meals=[
                    MealItem(
                        name="Quiet Cafe",
                        meal_type="Cafe",
                        start_time="10:30",
                        end_time="11:20",
                        latitude=31.241,
                        longitude=121.501,
                    )
                ],
                transport=[],
                notes=["Keep it easy."],
            )
        ],
        estimated_budget=300,
        budget_breakdown=BudgetBreakdown(meals=120, tickets=80, other=30, total=230),
        tips=["Book dinner ahead."],
        source_notes=["Plan generated with AMap MCP provider."],
        source_links=[PlanSource(title="Search result", url="https://example.com")],
    )


def test_location_search_endpoint_returns_candidates(monkeypatch) -> None:
    async def fake_search_location_candidates(keyword: str, city: str | None = None, limit: int = 8):
        assert keyword == "外滩"
        assert city == "上海"
        assert limit == 3
        return [
            LocationCandidate(
                name="外滩",
                address="上海市黄浦区",
                city="上海",
                latitude=31.2397,
                longitude=121.4998,
                poi_id="poi_001",
            )
        ]

    monkeypatch.setattr(location_route, "search_location_candidates", fake_search_location_candidates)

    response = client.get("/location/search", params={"keyword": "外滩", "city": "上海", "limit": 3})

    assert response.status_code == 200
    assert response.json()[0]["name"] == "外滩"
    assert response.json()[0]["poi_id"] == "poi_001"


def test_reverse_geocode_endpoint_returns_selected_location(monkeypatch) -> None:
    async def fake_reverse_geocode_location(longitude: float, latitude: float):
        assert longitude == 121.4998
        assert latitude == 31.2397
        return build_anchor()

    monkeypatch.setattr(location_route, "reverse_geocode_location", fake_reverse_geocode_location)

    response = client.get(
        "/location/reverse-geocode",
        params={"longitude": 121.4998, "latitude": 31.2397},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "The Bund"


def test_date_plan_endpoint_returns_itinerary(monkeypatch) -> None:
    async def fake_generate_date_plan(request: DatePlanRequest):
        assert request.anchor.name == "The Bund"
        return build_date_itinerary()

    monkeypatch.setattr(date_plan_route, "generate_date_plan", fake_generate_date_plan)

    response = client.post(
        "/date-plan/generate",
        json={
            "anchor": build_anchor().model_dump(mode="json"),
            "date": "2026-05-20",
            "start_time": "10:00",
            "end_time": "22:00",
            "travelers": 2,
            "budget": 900,
            "preferences": ["轻松聊天"],
            "dietary_preferences": ["少辣"],
            "transport_mode": "walking_transit",
            "radius_meters": 3000,
            "special_notes": "不要太赶",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["trip_id"] == "date_demo_2026-05-20"
    assert data["days"][0]["meals"][0]["latitude"] == 31.241


def test_date_plan_stream_endpoint_returns_ndjson_events(monkeypatch) -> None:
    async def fake_generate_date_plan_with_progress(request: DatePlanRequest, progress=None):
        assert request.anchor.name == "The Bund"
        if progress is not None:
            await progress(
                {
                    "type": "stage",
                    "title": "Mock stage",
                    "content": "Collecting candidates.",
                }
            )
        return build_date_itinerary()

    monkeypatch.setattr(
        date_plan_route,
        "generate_date_plan_with_progress",
        fake_generate_date_plan_with_progress,
    )

    response = client.post(
        "/date-plan/generate/stream",
        json={
            "anchor": build_anchor().model_dump(mode="json"),
            "date": "2026-05-20",
            "start_time": "10:00",
            "end_time": "22:00",
            "travelers": 2,
            "budget": 900,
            "preferences": ["轻松聊天"],
            "dietary_preferences": ["少辣"],
            "transport_mode": "walking_transit",
            "radius_meters": 3000,
            "special_notes": "不要太赶",
        },
    )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.strip().splitlines()]
    assert events[0]["type"] == "stage"
    assert events[-1]["type"] == "complete"
    assert events[-1]["itinerary"]["trip_id"] == "date_demo_2026-05-20"


def test_amap_mcp_provider_parses_geo_and_search(monkeypatch) -> None:
    provider = AmapMcpProvider(command="fake")

    async def fake_call_tool(tool_name: str, arguments: dict):
        if tool_name == "maps_geo":
            return {
                "return": [
                    {
                        "province": "Shanghai",
                        "city": "Shanghai",
                        "district": "Huangpu",
                        "location": "121.4998,31.2397",
                    }
                ]
            }
        if tool_name == "maps_text_search":
            return {"pois": [{"id": "poi_001", "name": "外滩", "address": "黄浦区"}]}
        if tool_name == "maps_search_detail":
            return {
                "id": "poi_001",
                "name": "外滩",
                "address": ["黄浦区", "中山东一路"],
                "city": "上海",
                "location": "121.4998,31.2397",
                "photos": {"url": "https://example.com/photo.jpg"},
            }
        raise AssertionError(tool_name)

    monkeypatch.setattr(provider, "_call_tool", fake_call_tool)

    geocode = asyncio.run(provider.geocode("外滩", city="上海"))
    results = asyncio.run(provider.search_text("外滩", city="上海", limit=1))

    assert geocode is not None
    assert geocode.longitude == 121.4998
    assert results[0].latitude == 31.2397
    assert results[0].address == "黄浦区 中山东一路"
    assert results[0].image_url == "https://example.com/photo.jpg"


def test_searchapi_provider_parses_maps_and_web(monkeypatch) -> None:
    provider = SearchApiProvider()

    async def fake_request(params: dict):
        if params["engine"] == "google_maps":
            return {
                "local_results": [
                    {
                        "title": "Quiet Cafe",
                        "address": "Somewhere",
                        "rating": 4.6,
                        "gps_coordinates": {"latitude": 31.24, "longitude": 121.5},
                        "link": "https://example.com/cafe",
                    }
                ]
            }
        return {
            "organic_results": [
                {
                    "title": "Date ideas",
                    "link": "https://example.com/date",
                    "snippet": "A short guide.",
                }
            ]
        }

    monkeypatch.setattr(provider, "_request", fake_request)

    pois = asyncio.run(provider.search_google_maps("date cafe", "Shanghai"))
    sources = asyncio.run(provider.search_web_sources("date guide"))

    assert pois[0].name == "Quiet Cafe"
    assert pois[0].rating == 4.6
    assert sources[0].title == "Date ideas"


def test_date_plan_service_falls_back_when_searchapi_fails(monkeypatch) -> None:
    class FakeAmapProvider:
        async def reverse_geocode(self, longitude: float, latitude: float):
            return build_anchor()

        async def search_around(self, **kwargs):
            return [
                LocationCandidate(
                    name=f"{kwargs['keyword']} Place",
                    address="Nearby",
                    latitude=31.24 + len(kwargs["keyword"]) / 1000,
                    longitude=121.5,
                    poi_id=f"poi_{kwargs['keyword']}",
                )
            ]

        async def estimate_route(self, **kwargs):
            return {"distance_km": 1.2, "estimated_minutes": 15}

    class FakeSearchProvider:
        async def search_google_maps(self, *args, **kwargs):
            raise date_plan_service.SearchApiError("down")

        async def search_web_sources(self, *args, **kwargs):
            return []

    monkeypatch.setattr(date_plan_service, "get_amap_provider", lambda: FakeAmapProvider())
    monkeypatch.setattr(date_plan_service, "get_search_provider", lambda: FakeSearchProvider())
    monkeypatch.setattr(date_plan_service, "_generate_llm_draft", lambda *args, **kwargs: (None, {}))

    request = DatePlanRequest(
        anchor=build_anchor(),
        date=date(2026, 5, 20),
        preferences=["轻松聊天"],
        dietary_preferences=[],
    )

    itinerary = asyncio.run(date_plan_service.generate_date_plan(request))

    assert itinerary.trip_id.startswith("date_")
    assert itinerary.days[0].transport
    assert any("SearchApi.io enrichment unavailable" in note for note in itinerary.source_notes)
