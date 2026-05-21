from __future__ import annotations

from typing import Any


def build_openai_compatible_chat_llm(
    *,
    model: str,
    api_key: str,
    base_url: str,
    timeout: int,
    max_retries: int,
    temperature: float,
):
    """Build a ChatOpenAI-compatible client, returning None when unavailable."""
    if not model or not api_key:
        return None

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url or None,
        timeout=timeout,
        max_retries=max_retries,
    )


def extract_token_usage(response: Any) -> dict[str, int]:
    """Extract token usage from a LangChain AIMessage-like response."""
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    metadata = getattr(response, "response_metadata", None) or {}
    token_usage = metadata.get("token_usage", {})
    if token_usage:
        usage["prompt_tokens"] = int(token_usage.get("prompt_tokens", 0) or 0)
        usage["completion_tokens"] = int(token_usage.get("completion_tokens", 0) or 0)
    return usage


def add_token_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    """Add two token usage dicts without requiring total_tokens."""
    return {
        "prompt_tokens": int(left.get("prompt_tokens", 0) or 0)
        + int(right.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(left.get("completion_tokens", 0) or 0)
        + int(right.get("completion_tokens", 0) or 0),
    }


def response_content_text(response: Any) -> str:
    """Normalize a LangChain AIMessage-like content field to text."""
    raw_text = getattr(response, "content", "")
    if isinstance(raw_text, list):
        raw_text = "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in raw_text
        )
    return str(raw_text)
