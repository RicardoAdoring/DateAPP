import json
from datetime import datetime
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.main import app  # noqa: E402
import app.api.routes.export as export_route  # noqa: E402
import app.api.routes.trip as trip_route  # noqa: E402
from app.models.schemas import (  # noqa: E402
    BudgetBreakdown,
    DayPlan,
    Itinerary,
    SpotItem,
    TokenStatsResponse,
    TokenUsage,
    TripDetailResponse,
    TripListResponse,
    TripSummaryItem,
    TripTokenStatsItem,
)


client = TestClient(app)


def build_generate_payload() -> dict:
    return {
        "destination": "Dali",
        "start_date": "2026-04-10",
        "end_date": "2026-04-12",
        "travelers": 2,
        "budget": 3200,
        "preferences": ["nature", "photos", "food"],
        "pace": "relaxed",
        "dietary_preferences": ["mild"],
        "hotel_level": "comfort",
        "special_notes": "Keep mornings easy.",
    }


def build_itinerary(trip_id: str = "trip_Dali_2026-04-10") -> Itinerary:
    return Itinerary(
        trip_id=trip_id,
        destination="Dali",
        summary="A relaxed Dali itinerary.",
        days=[
            DayPlan(
                day_index=1,
                date="2026-04-10",
                theme="Old town",
                spots=[
                    SpotItem(
                        name="Dali Old Town",
                        start_time="10:00",
                        end_time="12:00",
                        description="Slow walk and photos.",
                        estimated_cost=0,
                        location="Dali",
                    )
                ],
                meals=[],
                hotel=None,
                transport=[],
                notes=["Keep the pace easy."],
            )
        ],
        estimated_budget=300,
        budget_breakdown=BudgetBreakdown(
            transport=50,
            hotel=0,
            meals=120,
            tickets=0,
            other=30,
            total=200,
        ),
        tips=["Bring a light jacket."],
        source_notes=["RAG context: Dali guide"],
        token_usage=TokenUsage(
            rewrite_prompt_tokens=1,
            planner_prompt_tokens=2,
            rerank_prompt_tokens=3,
        ),
    )


@pytest.fixture(autouse=True)
def patch_route_dependencies(monkeypatch):
    store: dict[str, TripDetailResponse] = {}

    def fake_generate_trip_itinerary(request):
        return build_itinerary()

    def fake_edit_trip_itinerary(request):
        edited = request.current_itinerary.model_copy(deep=True)
        edited.summary = "Edited itinerary."
        return edited

    def fake_save_itinerary(itinerary: Itinerary) -> str:
        detail = TripDetailResponse(
            trip_id=itinerary.trip_id,
            itinerary=itinerary,
            created_at=datetime(2026, 4, 10, 8, 0, 0),
            updated_at=datetime(2026, 4, 10, 8, 0, 0),
        )
        store[itinerary.trip_id] = detail
        return itinerary.trip_id

    def fake_get_itinerary_by_trip_id(trip_id: str):
        return store.get(trip_id)

    def fake_list_saved_itineraries():
        items = [
            TripSummaryItem(
                trip_id=detail.trip_id,
                destination=detail.itinerary.destination,
                summary=detail.itinerary.summary,
                created_at=detail.created_at,
                updated_at=detail.updated_at,
            )
            for detail in store.values()
        ]
        return TripListResponse(total=len(items), items=items)

    def fake_delete_itinerary_by_trip_id(trip_id: str) -> bool:
        return store.pop(trip_id, None) is not None

    def fake_get_token_stats():
        items = [
            TripTokenStatsItem(
                trip_id=detail.trip_id,
                destination=detail.itinerary.destination,
                token_usage=detail.itinerary.token_usage or TokenUsage(),
            )
            for detail in store.values()
        ]
        total_prompt = sum(item.token_usage.total_prompt_tokens for item in items)
        total_completion = sum(item.token_usage.total_completion_tokens for item in items)
        return TokenStatsResponse(
            trip_count=len(items),
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_prompt + total_completion,
            items=items,
        )

    monkeypatch.setattr(trip_route, "generate_trip_itinerary", fake_generate_trip_itinerary)
    monkeypatch.setattr(trip_route, "edit_trip_itinerary", fake_edit_trip_itinerary)
    monkeypatch.setattr(trip_route, "save_itinerary", fake_save_itinerary)
    monkeypatch.setattr(trip_route, "get_itinerary_by_trip_id", fake_get_itinerary_by_trip_id)
    monkeypatch.setattr(trip_route, "list_saved_itineraries", fake_list_saved_itineraries)
    monkeypatch.setattr(trip_route, "delete_itinerary_by_trip_id", fake_delete_itinerary_by_trip_id)
    monkeypatch.setattr(trip_route, "get_token_stats", fake_get_token_stats)
    monkeypatch.setattr(export_route, "get_itinerary_by_trip_id", fake_get_itinerary_by_trip_id)

    return store


def test_generate_trip_returns_itinerary_successfully() -> None:
    response = client.post("/trip/generate", json=build_generate_payload())

    assert response.status_code == 200
    data = response.json()
    assert data["destination"] == "Dali"
    assert data["trip_id"] == "trip_Dali_2026-04-10"
    assert data["summary"] == "A relaxed Dali itinerary."
    assert len(data["days"]) == 1


def test_generate_trip_rejects_invalid_request() -> None:
    payload = build_generate_payload()
    payload["travelers"] = 0

    response = client.post("/trip/generate", json=payload)

    assert response.status_code == 422


def test_root_endpoint_returns_running_message() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Trip Planner Demo backend is running."}


def test_health_endpoint_returns_ok_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_edit_trip_returns_updated_itinerary_successfully() -> None:
    generated_itinerary = client.post("/trip/generate", json=build_generate_payload()).json()

    response = client.post(
        "/trip/edit",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "current_itinerary": generated_itinerary,
            "user_instruction": "Make it slower.",
            "edit_scope": "day_1",
            "preserve_constraints": ["Keep budget structure"],
        },
    )

    assert response.status_code == 200
    assert response.json()["summary"] == "Edited itinerary."


def test_edit_trip_stream_returns_ndjson_events() -> None:
    current_itinerary = build_itinerary().model_dump(mode="json")

    response = client.post(
        "/trip/edit/stream",
        json={
            "trip_id": current_itinerary["trip_id"],
            "current_itinerary": current_itinerary,
            "user_instruction": "Make it slower.",
            "edit_scope": "day_1",
            "preserve_constraints": ["Keep budget structure"],
        },
    )

    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.strip().splitlines()]
    assert events[0]["type"] == "stage"
    assert any(event["type"] == "plan_item" for event in events)
    assert events[-1]["type"] == "complete"
    assert events[-1]["itinerary"]["summary"] == "Edited itinerary."


def test_edit_trip_rejects_invalid_request() -> None:
    response = client.post(
        "/trip/edit",
        json={
            "trip_id": "trip_demo",
            "user_instruction": "Make it slower.",
        },
    )

    assert response.status_code == 422


def test_save_trip_returns_trip_id_successfully() -> None:
    generated_itinerary = client.post("/trip/generate", json=build_generate_payload()).json()

    response = client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Trip itinerary saved successfully.",
        "trip_id": generated_itinerary["trip_id"],
    }


def test_get_trip_detail_returns_saved_itinerary() -> None:
    generated_itinerary = client.post("/trip/generate", json=build_generate_payload()).json()
    client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    response = client.get(f"/trip/{generated_itinerary['trip_id']}")

    assert response.status_code == 200
    assert response.json()["itinerary"]["destination"] == "Dali"


def test_get_trip_detail_returns_404_for_missing_trip() -> None:
    response = client.get("/trip/trip_not_exists")

    assert response.status_code == 404


def test_list_trips_returns_saved_trip_summaries() -> None:
    generated_itinerary = client.post("/trip/generate", json=build_generate_payload()).json()
    client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    response = client.get("/trip")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["trip_id"] == generated_itinerary["trip_id"]


def test_delete_trip_removes_saved_itinerary() -> None:
    generated_itinerary = client.post("/trip/generate", json=build_generate_payload()).json()
    client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    response = client.delete(f"/trip/{generated_itinerary['trip_id']}")

    assert response.status_code == 200
    assert client.get(f"/trip/{generated_itinerary['trip_id']}").status_code == 404


def test_export_trip_markdown_returns_markdown_text() -> None:
    generated_itinerary = client.post("/trip/generate", json=build_generate_payload()).json()
    client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    response = client.get(f"/export/{generated_itinerary['trip_id']}/markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "Dali" in response.text
    assert "A relaxed Dali itinerary." in response.text


def test_export_trip_pdf_returns_pdf_bytes(monkeypatch) -> None:
    generated_itinerary = client.post("/trip/generate", json=build_generate_payload()).json()
    client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )
    monkeypatch.setattr(
        export_route,
        "itinerary_to_pdf_bytes",
        lambda trip_detail: b"%PDF-1.4\n%mock pdf\n",
    )

    response = client.get(f"/export/{generated_itinerary['trip_id']}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")


def test_trip_stats_returns_token_totals() -> None:
    generated_itinerary = client.post("/trip/generate", json=build_generate_payload()).json()
    client.post(
        "/trip/save",
        json={
            "trip_id": generated_itinerary["trip_id"],
            "itinerary": generated_itinerary,
            "user_id": "user_001",
        },
    )

    response = client.get("/trip/stats")

    assert response.status_code == 200
    assert response.json()["total_prompt_tokens"] == 6


def test_generate_trip_response_includes_rag_context() -> None:
    response = client.post("/trip/generate", json=build_generate_payload())

    assert response.status_code == 200
    assert "RAG context" in "\n".join(response.json()["source_notes"])
