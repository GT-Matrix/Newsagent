from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths


class QueueStateRepository:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.path = runtime_paths(project_root).process_dir / "event_queue.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"tasks": [], "results": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {"tasks": [], "results": {}}
        tasks = payload.get("tasks")
        results = payload.get("results")
        return {
            "tasks": tasks if isinstance(tasks, list) else [],
            "results": results if isinstance(results, dict) else {},
        }

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
