from __future__ import annotations

import json
from typing import Any

from modnews.core.config import LlmConfig
from modnews.core.progress import compact_messages, describe_llm_request, emit, new_request_id, simulate_stream


def build_llm_request_context(task: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    request_id = new_request_id(task)
    descriptor = describe_llm_request(task, messages)
    return {
        "request_id": request_id,
        "descriptor": descriptor,
        "compact_messages": compact_messages(messages),
    }


def emit_cached_llm_response(
    *,
    config: LlmConfig,
    task: str,
    request_id: str,
    descriptor: dict[str, Any],
    compacted_messages: list[dict[str, str]],
    cached: dict[str, Any],
) -> None:
    response_text = json.dumps(cached, ensure_ascii=False, sort_keys=True)
    emit(
        "llm_cache_hit",
        request_id=request_id,
        task=task,
        status="cached",
        response=cached,
        **descriptor,
    )
    if not config.simulate_cache_stream:
        return
    emit(
        "llm_request_start",
        request_id=request_id,
        task=task,
        model=config.model,
        temperature=config.temperature,
        cached=True,
        simulated=True,
        messages=compacted_messages,
        **descriptor,
    )
    simulate_stream(
        request_id=request_id,
        text=response_text,
        first_token_delay_seconds=config.cache_first_token_delay_seconds,
        tokens_per_second=config.cache_tokens_per_second,
    )
    emit(
        "llm_request_done",
        request_id=request_id,
        task=task,
        status="cached",
        cached=True,
        simulated=True,
        response=cached,
    )


def ensure_llm_request_config(config: LlmConfig) -> str:
    if not config.base_url:
        raise ValueError("LLM_BASE_URL is required for LLM classification")
    if not config.api_key:
        raise ValueError("LLM_API_KEY is required for LLM classification")
    return f"{config.base_url.rstrip('/')}/chat/completions"
