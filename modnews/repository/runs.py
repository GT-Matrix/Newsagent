from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths


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
        _write_json_atomic(path, record)
        return record

    def update(self, run_id: str, **patch: Any) -> dict[str, Any]:
        record = self._read(run_id)
        record.update(patch)
        return self.save(run_id, record)

    def append_checkpoint(self, run_id: str, checkpoint_path: Path | str, *, create_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            record = self._read(run_id)
        except KeyError:
            record = self.create(run_id, create_payload or {})
        checkpoints = list(record.get("checkpoints", []))
        checkpoints.append(str(Path(checkpoint_path)))
        return self.update(run_id, checkpoints=checkpoints)

    def get(self, run_id: str) -> dict[str, Any]:
        data = self._read(run_id)
        try:
            from modnews.service.pipeline.runtime_store import overlay_run_record
        except Exception:
            return data
        return overlay_run_record(self.project_root, data)

    def _read(self, run_id: str) -> dict[str, Any]:
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


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    tmp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)
