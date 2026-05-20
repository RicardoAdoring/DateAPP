from pathlib import Path
import sys
from types import SimpleNamespace


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import TripEditRequest, TripRequest  # noqa: E402
from app.services.trip_service import edit_trip_itinerary, generate_trip_itinerary  # noqa: E402
import app.services.trip_service as trip_service  # noqa: E402


def build_trip_request() -> TripRequest:
    return TripRequest(
        destination="Dali",
        start_date="2026-04-10",
        end_date="2026-04-12",
        travelers=2,
        budget=3200,
        preferences=["nature", "photos", "food"],
        pace="relaxed",
        dietary_preferences=["mild"],
        hotel_level="comfort",
        special_notes="Keep mornings easy and include a sunset option.",
    )


def patch_generation_dependencies(monkeypatch) -> None:
    monkeypatch.setattr(trip_service, "ENABLE_AMAP_ENRICHMENT", False)
    monkeypatch.setattr(
        trip_service,
        "collect_trip_context",
        lambda **kwargs: (
            ["[source: dali_guide.md] Dali Old Town and Erhai are useful context."],
            {"prompt_tokens": 11, "completion_tokens": 3},
            {"prompt_tokens": 17, "completion_tokens": 0},
        ),
    )
    monkeypatch.setattr(
        trip_service,
        "generate_planner_draft",
        lambda request, rag_contexts, day_count: (
            None,
            {"prompt_tokens": 23, "completion_tokens": 9},
        ),
    )


def test_generate_trip_itinerary_returns_itinerary_object(monkeypatch) -> None:
    patch_generation_dependencies(monkeypatch)

    itinerary = generate_trip_itinerary(build_trip_request())

    assert itinerary.destination == "Dali"
    assert itinerary.trip_id == "trip_Dali_2026-04-10"
    assert len(itinerary.days) == 3
    assert itinerary.budget_breakdown.total >= 0
    assert itinerary.token_usage is not None
    assert itinerary.token_usage.rewrite_prompt_tokens == 11
    assert itinerary.token_usage.rerank_prompt_tokens == 17
    assert itinerary.token_usage.planner_prompt_tokens == 23


def test_generate_trip_itinerary_builds_day_plans_by_date_range(monkeypatch) -> None:
    patch_generation_dependencies(monkeypatch)

    itinerary = generate_trip_itinerary(build_trip_request())

    assert [day.day_index for day in itinerary.days] == [1, 2, 3]
    assert [day.date.isoformat() for day in itinerary.days] == [
        "2026-04-10",
        "2026-04-11",
        "2026-04-12",
    ]


def test_generate_trip_itinerary_includes_retrieved_context(monkeypatch) -> None:
    patch_generation_dependencies(monkeypatch)

    itinerary = generate_trip_itinerary(build_trip_request())

    joined_notes = "\n".join(itinerary.source_notes)
    assert "Dali Old Town and Erhai" in joined_notes


def test_edit_trip_itinerary_applies_llm_day_edit(monkeypatch) -> None:
    patch_generation_dependencies(monkeypatch)
    original_itinerary = generate_trip_itinerary(build_trip_request())

    fake_draft = SimpleNamespace(
        theme="A slower Erhai afternoon",
        spot_name="Erhai lakeside walk",
        spot_description="A low-pressure lakeside plan with photo time.",
        meal_name="Lakeside tea",
        meal_notes="Light food and a long rest.",
        daily_note="Start late and keep the afternoon flexible.",
    )
    monkeypatch.setattr(
        trip_service,
        "generate_day_edit_draft",
        lambda request, target_day: (
            fake_draft,
            {"prompt_tokens": 80, "completion_tokens": 30},
        ),
    )

    edit_request = TripEditRequest(
        trip_id=original_itinerary.trip_id,
        current_itinerary=original_itinerary,
        user_instruction="Make day 2 slower.",
        edit_scope="day_2",
        preserve_constraints=["Keep budget structure"],
    )

    updated_itinerary = edit_trip_itinerary(edit_request)

    assert updated_itinerary.days[1].theme == "A slower Erhai afternoon"
    assert updated_itinerary.days[1].spots[0].name == "Erhai lakeside walk"
    assert updated_itinerary.days[1].meals[0].name == "Lakeside tea"
    assert updated_itinerary.days[1].notes[-1] == "Start late and keep the afternoon flexible."
    assert updated_itinerary.token_usage is not None
    assert updated_itinerary.token_usage.planner_prompt_tokens == 80
    assert updated_itinerary.token_usage.planner_completion_tokens == 30
