from __future__ import annotations

import json
from typing import Any


def print_payload(payload: Any, output_format: str = "table") -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if output_format == "jsonl":
        rows = payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else [payload]
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
        return
    if isinstance(payload, list):
        _print_rows(payload)
    elif isinstance(payload, dict):
        _print_dict(payload)
    else:
        print(payload)


def _print_dict(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        print(f"{key}: {value}")


def _print_rows(rows: list[Any]) -> None:
    if not rows:
        return
    if not all(isinstance(row, dict) for row in rows):
        for row in rows:
            print(row)
        return
    keys = list(dict.fromkeys(key for row in rows for key in row.keys()))
    print("\t".join(keys))
    for row in rows:
        print("\t".join(_cell(row.get(key)) for key in keys))


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
