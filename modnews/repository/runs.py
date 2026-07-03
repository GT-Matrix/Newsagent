from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modnews_pipeline.paths import runtime_paths


class RunRepository:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.root = runtime_paths(project_root).process_dir / "runs"

    def create(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        record = {
            "run_id": run_id,
            "state": "queued",
            "created_at": now,
            "updated_at": now,
            "payload": payload,
        }
        self.save(run_id, record)
        return record

    def save(self, run_id: str, record: dict[str, Any]) -> dict[str, Any]:
        record["updated_at"] = _now()
        path = self.run_dir(run_id) / "run.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def update(self, run_id: str, **patch: Any) -> dict[str, Any]:
        record = self.get(run_id)
        record.update(patch)
        return self.save(run_id, record)

    def get(self, run_id: str) -> dict[str, Any]:
        path = self.run_dir(run_id) / "run.json"
        if not path.exists():
            raise KeyError(run_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"invalid run record: {path}")
        return data

    def list(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        rows = []
        for path in self.root.glob("*/run.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                data["path"] = str(path)
                rows.append(data)
        return sorted(rows, key=lambda row: str(row.get("updated_at", "")), reverse=True)

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
