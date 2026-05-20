from pathlib import Path
import sys


CURRENT_FILE = Path(__file__).resolve()
BACKEND_DIR = CURRENT_FILE.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app.rag.retriever as retriever  # noqa: E402


def disable_cache_and_external_rerank(monkeypatch) -> None:
    monkeypatch.setattr(retriever, "get_cached_json", lambda key: None)
    monkeypatch.setattr(retriever, "set_cached_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        retriever,
        "_rerank_with_dashscope",
        lambda query, chunks, top_k: (None, {"prompt_tokens": 0, "completion_tokens": 0}),
    )


def test_retrieve_travel_guide_formats_chunks_as_text(monkeypatch) -> None:
    disable_cache_and_external_rerank(monkeypatch)

    def fake_search_guide_chunks(query: str, top_k: int = 3) -> list[dict[str, str]]:
        assert query == "Dali old town food"
        assert top_k == 6
        return [
            {
                "source": "dali_guide.md",
                "title": "Dali Old Town",
                "text": "Dali Old Town is good for slow walks and photos.",
            }
        ]

    monkeypatch.setattr(retriever, "search_guide_chunks", fake_search_guide_chunks)

    results, usage = retriever.retrieve_travel_guide("Dali old town food", top_k=2)

    assert results == [
        "[来源: dali_guide.md | 标题: Dali Old Town]\n"
        "Dali Old Town is good for slow walks and photos."
    ]
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0}


def test_retrieve_travel_guide_returns_empty_when_no_chunks(monkeypatch) -> None:
    disable_cache_and_external_rerank(monkeypatch)

    def fake_search_guide_chunks(query: str, top_k: int = 3) -> list[dict[str, str]]:
        assert query == "Mars desert expedition"
        assert top_k == 6
        return []

    monkeypatch.setattr(retriever, "search_guide_chunks", fake_search_guide_chunks)

    results, usage = retriever.retrieve_travel_guide("Mars desert expedition", top_k=2)

    assert results == []
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0}
