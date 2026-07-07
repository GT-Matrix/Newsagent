from __future__ import annotations

import json
import re
from typing import Any


def parse_json_content(content: Any) -> dict[str, Any]:
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
