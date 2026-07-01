from __future__ import annotations

import json
from pathlib import Path

from src.models import EnrichedEvent


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def write_enriched_events(path: Path, events: list[EnrichedEvent]) -> None:
    write_json(path, [event.to_dict() for event in events])


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
