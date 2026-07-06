from __future__ import annotations

import json
import time

import requests

from modnews.core.config import LlmConfig
from modnews.core.progress import emit
from .llm_transport_codec import (
    build_chat_completion_body,
    decode_stream_response_lines,
    extract_message_content,
)


class LlmTransport:
    def __init__(self, config: LlmConfig, session: requests.Session) -> None:
        self.config = config
        self.session = session

    def request_json_content(
        self,
        *,
        url: str,
        messages: list[dict[str, str]],
        request_id: str,
        task: str,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(1, max(1, self.config.max_retries) + 1):
            try:
                return self._request_content(url, messages, request_id, attempt)
            except (requests.RequestException, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc
                emit(
                    "llm_request_retry",
                    request_id=request_id,
                    task=task,
                    attempt=attempt,
                    max_retries=max(1, self.config.max_retries),
                    error=str(exc),
                )
                if attempt >= max(1, self.config.max_retries):
                    break
                time.sleep(retry_delay_seconds(exc, attempt))
        assert last_error is not None
        raise last_error

    def _request_content(self, url: str, messages: list[dict[str, str]], request_id: str, attempt: int) -> str:
        body = build_chat_completion_body(
            model=self.config.model,
            messages=messages,
            temperature=self.config.temperature,
            stream=True,
        )
        response = self.session.post(
            url,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            json=body,
            timeout=self.config.timeout_seconds,
            stream=True,
        )
        if response.status_code >= 400:
            return self._request_content_without_stream(url, messages)
        raw_lines: list[str] = []
        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace").strip()
            raw_lines.append(line)
        try:
            saw_stream, payload = decode_stream_response_lines(raw_lines)
        except json.JSONDecodeError:
            return self._request_content_without_stream(url, messages)
        if saw_stream:
            content = payload or ""
            if payload:
                for chunk in _iter_stream_chunks(raw_lines):
                    emit("llm_stream_delta", request_id=request_id, attempt=attempt, delta=chunk)
            if not content.strip():
                raise ValueError("LLM stream returned no content")
            return content
        if not payload:
            raise ValueError("LLM returned empty response body")
        return extract_message_content(json.loads(payload))

    def _request_content_without_stream(self, url: str, messages: list[dict[str, str]]) -> str:
        response = self.session.post(
            url,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            json=build_chat_completion_body(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                stream=False,
            ),
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return extract_message_content(payload)


def _iter_stream_chunks(lines: list[str]) -> list[str]:
    chunks: list[str] = []
    for line in lines:
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return []
        choices = payload.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta", {}).get("content")
        if delta:
            chunks.append(str(delta))
    return chunks


def retry_delay_seconds(exc: Exception, attempt: int) -> float:
    response = getattr(exc, "response", None)
    retry_after = None
    if response is not None:
        retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), 90.0)
        except ValueError:
            pass
    status_code = getattr(response, "status_code", None)
    base = 8.0 if status_code in {429, 500, 502, 503, 504} else 2.0
    return min(base * (2 ** max(attempt - 1, 0)), 90.0)
