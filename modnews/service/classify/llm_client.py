from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from modnews.core.config import LlmConfig
from modnews.core.progress import compact_messages, describe_llm_request, emit, new_request_id, simulate_stream
from modnews.repository.llm_cache import LlmCacheRepository
from .llm_response import parse_json_content
from .llm_transport import LlmTransport


@dataclass(slots=True)
class LlmClient:
    config: LlmConfig
    session: requests.Session

    def complete_json(self, *, task: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        request_id = new_request_id(task)
        descriptor = describe_llm_request(task, messages)
        cache = LlmCacheRepository(self.config)
        cached = cache.read(task, messages)
        if cached is not None:
            response_text = json.dumps(cached, ensure_ascii=False, sort_keys=True)
            emit(
                "llm_cache_hit",
                request_id=request_id,
                task=task,
                status="cached",
                response=cached,
                **descriptor,
            )
            if self.config.simulate_cache_stream:
                emit(
                    "llm_request_start",
                    request_id=request_id,
                    task=task,
                    model=self.config.model,
                    temperature=self.config.temperature,
                    cached=True,
                    simulated=True,
                    messages=compact_messages(messages),
                    **descriptor,
                )
                simulate_stream(
                    request_id=request_id,
                    text=response_text,
                    first_token_delay_seconds=self.config.cache_first_token_delay_seconds,
                    tokens_per_second=self.config.cache_tokens_per_second,
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
            return cached

        if not self.config.base_url:
            raise ValueError("LLM_BASE_URL is required for LLM classification")
        if not self.config.api_key:
            raise ValueError("LLM_API_KEY is required for LLM classification")

        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        emit(
            "llm_request_start",
            request_id=request_id,
            task=task,
            model=self.config.model,
            temperature=self.config.temperature,
            messages=compact_messages(messages),
            **descriptor,
        )
        transport = LlmTransport(self.config, self.session)
        try:
            content = transport.request_json_content(url=url, messages=messages, request_id=request_id, task=task)
            parsed = parse_json_content(content)
            cache.write(task, messages, parsed)
            emit(
                "llm_request_done",
                request_id=request_id,
                task=task,
                status="done",
                response=parsed,
            )
            return parsed
        except (requests.RequestException, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
            emit("llm_request_error", request_id=request_id, task=task, error=str(exc))
            raise
