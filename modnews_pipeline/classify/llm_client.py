from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from modnews_pipeline.config import LlmConfig
from modnews_pipeline.progress import compact_messages, describe_llm_request, emit, new_request_id, simulate_stream

_CACHE_LOCK = threading.Lock()


@dataclass(slots=True)
class LlmClient:
    config: LlmConfig
    session: requests.Session

    def complete_json(self, *, task: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        request_id = new_request_id(task)
        descriptor = describe_llm_request(task, messages)
        cached = self._read_cache(task, messages)
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
        last_error: Exception | None = None
        emit(
            "llm_request_start",
            request_id=request_id,
            task=task,
            model=self.config.model,
            temperature=self.config.temperature,
            messages=compact_messages(messages),
            **descriptor,
        )
        for attempt in range(1, max(1, self.config.max_retries) + 1):
            try:
                content = self._request_content(url, messages, request_id, attempt)
                parsed = _parse_json_content(content)
                self._write_cache(task, messages, parsed)
                emit(
                    "llm_request_done",
                    request_id=request_id,
                    task=task,
                    status="done",
                    response=parsed,
                )
                return parsed
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
                time.sleep(_retry_delay_seconds(exc, attempt))
        assert last_error is not None
        emit("llm_request_error", request_id=request_id, task=task, error=str(last_error))
        raise last_error

    def _request_content(self, url: str, messages: list[dict[str, str]], request_id: str, attempt: int) -> str:
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "response_format": {"type": "json_object"},
            "stream": True,
        }
        response = self.session.post(
            url,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            json=body,
            timeout=self.config.timeout_seconds,
            stream=True,
        )
        if response.status_code >= 400:
            if response.status_code in {400, 404, 415, 422}:
                return self._request_content_without_stream(url, messages)
            response.raise_for_status()
        chunks: list[str] = []
        non_stream_lines: list[str] = []
        saw_stream = False
        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                non_stream_lines.append(line)
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            saw_stream = True
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                return self._request_content_without_stream(url, messages)
            choices = payload.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta", {}).get("content")
            if delta:
                chunks.append(delta)
                emit("llm_stream_delta", request_id=request_id, attempt=attempt, delta=delta)
        if saw_stream:
            content = "".join(chunks)
            if not content.strip():
                raise ValueError("LLM stream returned no content")
            return content
        payload = json.loads("\n".join(non_stream_lines))
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError(f"LLM returned empty choices: {payload}")
        return choices[0]["message"]["content"]

    def _request_content_without_stream(self, url: str, messages: list[dict[str, str]]) -> str:
        response = self.session.post(
            url,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            json={
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError(f"LLM returned empty choices: {payload}")
        return choices[0]["message"]["content"]

    def _cache_key(self, task: str, messages: list[dict[str, str]]) -> str:
        payload = {
            "task": task,
            "model": self.config.model,
            "temperature": self.config.temperature,
            "messages": messages,
        }
        return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def _read_cache(self, task: str, messages: list[dict[str, str]]) -> dict[str, Any] | None:
        if not self.config.cache_path:
            return None
        key = self._cache_key(task, messages)
        with _CACHE_LOCK:
            self._ensure_cache()
            with sqlite3.connect(self.config.cache_path) as conn:
                row = conn.execute("SELECT response_json FROM llm_cache WHERE cache_key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def _write_cache(self, task: str, messages: list[dict[str, str]], response: dict[str, Any]) -> None:
        if not self.config.cache_path:
            return
        key = self._cache_key(task, messages)
        with _CACHE_LOCK:
            self._ensure_cache()
            with sqlite3.connect(self.config.cache_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO llm_cache (cache_key, task, response_json)
                    VALUES (?, ?, ?)
                    """,
                    (key, task, json.dumps(response, ensure_ascii=False, sort_keys=True)),
                )

    def _ensure_cache(self) -> None:
        assert self.config.cache_path is not None
        Path(self.config.cache_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.config.cache_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache (
                    cache_key TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )



def _retry_delay_seconds(exc: Exception, attempt: int) -> float:
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


def _parse_json_content(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise ValueError(f"Unexpected LLM content type: {type(content)!r}")
    text = content.strip()
    if not text:
        raise ValueError("LLM returned empty content")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError(f"LLM returned non-JSON content: {text[:500]}")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM returned non-object JSON: {text[:500]}")
    return parsed
