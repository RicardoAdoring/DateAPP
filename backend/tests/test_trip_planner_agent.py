from pathlib import Path
import json
import sys
from types import ModuleType


# 允许测试文件直接导入 backend/app 下的模块。
CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.agents.trip_planner_agent as trip_planner_agent  # noqa: E402
from app.models.schemas import (  # noqa: E402
    BudgetBreakdown,
    DayPlan,
    Itinerary,
    MealItem,
    SpotItem,
    TripEditRequest,
    TripRequest,
)


def build_trip_request() -> TripRequest:
    """构造一个合法的 TripRequest，供 agent 测试复用。"""
    return TripRequest(
        destination="大理",
        start_date="2026-04-10",
        end_date="2026-04-12",
        travelers=2,
        budget=3200,
        preferences=["自然风景", "拍照", "美食"],
        pace="轻松",
        dietary_preferences=["少辣"],
        hotel_level="舒适型",
        special_notes="不想太早起床，希望安排一个适合看日落的地点",
    )


def build_planner_draft(day_count: int) -> trip_planner_agent.PlannerDraft:
    """构造一个假的 PlannerDraft，模拟 LLM 正常返回。"""
    return trip_planner_agent.PlannerDraft(
        summary="这是一份适合轻松游玩的大理行程草稿。",
        tips=["早晚温差较大，建议带薄外套。"],
        days=[
            trip_planner_agent.PlannerDayDraft(
                day_index=index + 1,
                theme=f"第 {index + 1} 天主题",
                spot_name=f"景点 {index + 1}",
                spot_description=f"推荐景点 {index + 1} 的原因。",
                meal_name=f"餐厅 {index + 1}",
                meal_notes=f"餐饮说明 {index + 1}",
                daily_note=f"当天备注 {index + 1}",
            )
            for index in range(day_count)
        ],
    )


def install_fake_langchain_openai(monkeypatch, result: trip_planner_agent.PlannerDraft) -> tuple[type, type]:
    """往 sys.modules 注入假的 langchain_openai 模块，并返回两个假类。"""

    class FakeResponse:
        def __init__(self, content):
            self.content = content
            self.response_metadata = {
                "token_usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                }
            }

    class FakeChatOpenAI:
        last_init_kwargs = None
        last_messages = None

        def __init__(self, **kwargs):
            FakeChatOpenAI.last_init_kwargs = kwargs

        def invoke(self, messages):
            FakeChatOpenAI.last_messages = messages
            return FakeResponse(result.model_dump_json())

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

    return FakeChatOpenAI, FakeResponse


def test_collect_trip_context_calls_rag_tool_with_expected_arguments(monkeypatch) -> None:
    """测试 collect_trip_context 会把参数正确传给 rag_tool。"""
    captured = {}

    def fake_get_destination_guide_context(destination, preferences, pace, special_notes, top_k):
        captured["destination"] = destination
        captured["preferences"] = preferences
        captured["pace"] = pace
        captured["special_notes"] = special_notes
        captured["top_k"] = top_k
        return ["攻略片段 1", "攻略片段 2"], {"prompt_tokens": 0, "completion_tokens": 0}, {"prompt_tokens": 0, "completion_tokens": 0}

    monkeypatch.setattr(
        trip_planner_agent,
        "get_destination_guide_context",
        fake_get_destination_guide_context,
    )

    results, _, _ = trip_planner_agent.collect_trip_context(
        "大理",
        ["美食", "拍照"],
        pace="轻松",
        special_notes="想看日落，不想早起",
    )

    assert results == ["攻略片段 1", "攻略片段 2"]
    assert captured == {
        "destination": "大理",
        "preferences": ["美食", "拍照"],
        "pace": "轻松",
        "special_notes": "想看日落，不想早起",
        "top_k": 5,
    }


def test_generate_planner_draft_returns_none_when_api_key_is_missing(monkeypatch) -> None:
    """测试没有配置 PLANNER_LLM_API_KEY 时会直接返回 None。"""
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_API_KEY", "")

    result, usage = trip_planner_agent.generate_planner_draft(
        request=build_trip_request(),
        rag_contexts=["大理古城适合慢游。"],
        day_count=3,
    )

    assert result is None
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0}


def test_generate_planner_draft_returns_structured_result_with_mock_llm(monkeypatch) -> None:
    """测试 agent 能调用结构化 LLM 并返回 PlannerDraft。"""
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_API_KEY", "test-key")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MODEL", "fake-model")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_BASE_URL", "https://example.test")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MAX_RETRIES", 1)

    expected_result = build_planner_draft(day_count=3)
    FakeChatOpenAI, _ = install_fake_langchain_openai(monkeypatch, expected_result)

    result, usage = trip_planner_agent.generate_planner_draft(
        request=build_trip_request(),
        rag_contexts=["大理古城适合傍晚散步。", "洱海生态廊道适合骑行。"],
        day_count=3,
    )

    assert result == expected_result
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 50
    assert FakeChatOpenAI.last_init_kwargs == {
        "model": "fake-model",
        "temperature": 0.3,
        "api_key": "test-key",
        "base_url": "https://example.test",
        "timeout": 60,
        "max_retries": 1,
    }


def test_generate_planner_draft_falls_back_to_ollama_when_primary_fails(monkeypatch) -> None:
    """测试 DeepSeek 调用异常时会自动尝试 Ollama fallback。"""

    class FakeResponse:
        def __init__(self, content):
            self.content = content
            self.response_metadata = {
                "token_usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 6,
                }
            }

    expected_result = build_planner_draft(day_count=3)
    init_kwargs: list[dict] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            init_kwargs.append(kwargs)

        def invoke(self, messages):
            if self.kwargs["model"] == "deepseek-test":
                raise RuntimeError("deepseek down")
            return FakeResponse(expected_result.model_dump_json())

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_API_KEY", "test-key")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MODEL", "deepseek-test")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_BASE_URL", "https://deepseek.test")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MAX_RETRIES", 1)
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_ENABLED", True)
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_API_KEY", "ollama")
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_TIMEOUT_SECONDS", 20)
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_MAX_RETRIES", 0)

    result, usage = trip_planner_agent.generate_planner_draft(
        request=build_trip_request(),
        rag_contexts=["大理古城适合傍晚散步。"],
        day_count=3,
    )

    assert result == expected_result
    assert usage == {"prompt_tokens": 12, "completion_tokens": 6}
    assert [item["model"] for item in init_kwargs] == ["deepseek-test", "qwen2.5:7b"]
    assert init_kwargs[1]["base_url"] == "http://127.0.0.1:11434/v1"


def test_generate_planner_draft_falls_back_to_ollama_when_primary_returns_bad_json(monkeypatch) -> None:
    """测试 DeepSeek 返回不可解析内容时会自动尝试 Ollama fallback。"""

    class FakeResponse:
        def __init__(self, content, prompt_tokens, completion_tokens):
            self.content = content
            self.response_metadata = {
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
            }

    expected_result = build_planner_draft(day_count=3)

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            if self.kwargs["model"] == "deepseek-test":
                return FakeResponse("模型返回了一段非 JSON 文本", 10, 2)
            return FakeResponse(expected_result.model_dump_json(), 8, 4)

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_API_KEY", "test-key")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MODEL", "deepseek-test")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_BASE_URL", "https://deepseek.test")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MAX_RETRIES", 1)
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_ENABLED", True)
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_API_KEY", "ollama")
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_TIMEOUT_SECONDS", 20)
    monkeypatch.setattr(trip_planner_agent, "OLLAMA_FALLBACK_MAX_RETRIES", 0)

    result, usage = trip_planner_agent.generate_planner_draft(
        request=build_trip_request(),
        rag_contexts=["大理古城适合傍晚散步。"],
        day_count=3,
    )

    assert result == expected_result
    assert usage == {"prompt_tokens": 18, "completion_tokens": 6}


def test_generate_planner_draft_builds_prompt_with_request_and_rag_context(monkeypatch) -> None:
    """测试 prompt 中包含用户请求信息和本地攻略上下文。"""
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_API_KEY", "test-key")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MODEL", "fake-model")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_BASE_URL", "")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MAX_RETRIES", 1)

    expected_result = build_planner_draft(day_count=3)
    FakeChatOpenAI, _ = install_fake_langchain_openai(monkeypatch, expected_result)

    trip_planner_agent.generate_planner_draft(
        request=build_trip_request(),
        rag_contexts=["大理古城适合傍晚散步。", "洱海生态廊道适合骑行。"],
        day_count=3,
    )

    messages = FakeChatOpenAI.last_messages
    assert messages is not None
    assert messages[0][0] == "system"
    assert "旅行规划助手" in messages[0][1]
    assert messages[1][0] == "human"
    assert "目的地：大理" in messages[1][1]
    assert "偏好：自然风景、拍照、美食" in messages[1][1]
    assert "本地攻略上下文：" in messages[1][1]
    assert "大理古城适合傍晚散步。" in messages[1][1]
    assert "洱海生态廊道适合骑行。" in messages[1][1]


def test_generate_planner_draft_returns_none_when_day_count_mismatches(monkeypatch) -> None:
    """测试当 LLM 返回的天数不符合预期时，会回退为 None。"""
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_API_KEY", "test-key")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MODEL", "fake-model")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_BASE_URL", "")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MAX_RETRIES", 1)

    wrong_result = build_planner_draft(day_count=2)
    install_fake_langchain_openai(monkeypatch, wrong_result)

    result, usage = trip_planner_agent.generate_planner_draft(
        request=build_trip_request(),
        rag_contexts=["大理古城适合傍晚散步。"],
        day_count=3,
    )

    assert result is None


def test_generate_day_edit_draft_accepts_nested_day_shape(monkeypatch) -> None:
    """测试单日编辑结果即使返回 DayPlan 风格结构，也能被兼容解析。"""

    class FakeResponse:
        def __init__(self, content):
            self.content = content
            self.response_metadata = {
                "token_usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 30,
                    "total_tokens": 110,
                }
            }

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def invoke(self, messages):
            return FakeResponse(
                json.dumps(
                    {
                        "theme": "更轻松的喜洲慢游",
                        "spots": [
                            {
                                "name": "双廊古镇",
                                "description": "更适合看海、发呆和看日落。",
                            }
                        ],
                        "meals": [
                            {
                                "name": "海景下午茶",
                                "notes": "保留轻松节奏，少辣。",
                            }
                        ],
                        "notes": ["上午慢慢出发，下午去双廊看日落。"],
                    },
                    ensure_ascii=False,
                )
            )

    fake_module = ModuleType("langchain_openai")
    fake_module.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_module)

    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_API_KEY", "test-key")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MODEL", "fake-model")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_BASE_URL", "")
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_TIMEOUT_SECONDS", 60)
    monkeypatch.setattr(trip_planner_agent, "PLANNER_LLM_MAX_RETRIES", 1)

    itinerary = build_planner_draft(day_count=3)
    target_day = DayPlan(
        day_index=2,
        date="2026-04-11",
        theme="原始主题",
        spots=[
            SpotItem(
                name="喜洲古镇",
                start_time="10:00",
                end_time="12:00",
                description="原始景点说明",
                estimated_cost=50.0,
                location="大理",
            )
        ],
        meals=[
            MealItem(
                name="喜洲粑粑",
                meal_type="午餐",
                estimated_cost=30.0,
                notes="原始餐饮说明",
            )
        ],
        notes=["原始备注"],
    )
    request = TripEditRequest(
        trip_id="trip_demo",
        current_itinerary=Itinerary(
            trip_id="trip_demo",
            destination="大理",
            summary=itinerary.summary,
            days=[],
            estimated_budget=1000,
            budget_breakdown=BudgetBreakdown(
                transport=100,
                hotel=300,
                meals=200,
                tickets=100,
                other=100,
                total=800,
            ),
            tips=[],
            source_notes=[],
        ),
        user_instruction="第二天改得更轻松一点，不要安排太满",
        edit_scope="day_2",
        preserve_constraints=["保留预算结构"],
    )

    result, usage = trip_planner_agent.generate_day_edit_draft(request, target_day)

    assert result is not None
    assert result.theme == "更轻松的喜洲慢游"
    assert usage["prompt_tokens"] == 80
    assert usage["completion_tokens"] == 30
    assert result.spot_name == "双廊古镇"
    assert result.spot_description == "更适合看海、发呆和看日落。"
    assert result.meal_name == "海景下午茶"
    assert result.meal_notes == "保留轻松节奏，少辣。"
    assert result.daily_note == "上午慢慢出发，下午去双廊看日落。"
