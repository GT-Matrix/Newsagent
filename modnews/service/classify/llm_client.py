from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests

from modnews.core.config import LlmConfig
from modnews.core.progress import emit
from modnews.repository.llm_cache import LlmCacheRepository
from .llm_request_ops import build_llm_request_context, emit_cached_llm_response, ensure_llm_request_config
from .llm_response import parse_json_content
from .llm_transport import LlmTransport


@dataclass(slots=True)
class LlmClient:
    config: LlmConfig
    session: requests.Session

    def complete_json(self, *, task: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        request = build_llm_request_context(task, messages)
        request_id = str(request["request_id"])
        descriptor = dict(request["descriptor"])
        cache = LlmCacheRepository(self.config)
        cached = cache.read(task, messages)
        if cached is not None:
            emit_cached_llm_response(
                config=self.config,
                task=task,
                request_id=request_id,
                descriptor=descriptor,
                compacted_messages=list(request["compact_messages"]),
                cached=cached,
            )
            return cached

        url = ensure_llm_request_config(self.config)
        emit(
            "llm_request_start",
            request_id=request_id,
            task=task,
            model=self.config.model,
            temperature=self.config.temperature,
            messages=request["compact_messages"],
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
