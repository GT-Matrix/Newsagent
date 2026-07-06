from __future__ import annotations

import json
import time

import requests

from modnews.core.config import LlmConfig
from modnews.core.progress import emit


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
            return self._request_content_without_stream(url, messages)
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
