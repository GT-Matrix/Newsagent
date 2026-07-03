from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def append_event(path: Path, event_type: str, **payload: Any) -> dict[str, Any]:
    event = {"ts": _now(), "type": event_type, **payload}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_events(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            rows.append(event)
    return rows[-limit:] if limit else rows


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
