from __future__ import annotations

import json
from typing import Any


def build_chat_completion_body(
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    stream: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    if stream:
        body["stream"] = True
    return body


def decode_stream_response_lines(lines: list[str]) -> tuple[bool, str | None]:
    chunks: list[str] = []
    non_stream_lines: list[str] = []
    saw_stream = False
    for line in lines:
        if not line:
            continue
        if not line.startswith("data:"):
            non_stream_lines.append(line)
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        saw_stream = True
        payload = json.loads(data)
        choices = payload.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta", {}).get("content")
        if delta:
            chunks.append(str(delta))
    if saw_stream:
        return True, "".join(chunks)
    return False, "\n".join(non_stream_lines) if non_stream_lines else None


def extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError(f"LLM returned empty choices: {payload}")
    return str(choices[0]["message"]["content"])
