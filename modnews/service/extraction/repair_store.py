from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RepairTask:
    id: str
    source_id: str
    status: str
    work_dir: Path
    created_at: str
    updated_at: str
    log_path: Path
    result_path: Path
    command: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "status": self.status,
            "work_dir": str(self.work_dir),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "log_path": str(self.log_path),
            "result_path": str(self.result_path),
            "command": self.command,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RepairTask":
        return cls(
            id=str(raw["id"]),
            source_id=str(raw["source_id"]),
            status=str(raw["status"]),
            work_dir=Path(str(raw["work_dir"])),
            created_at=str(raw["created_at"]),
            updated_at=str(raw["updated_at"]),
            log_path=Path(str(raw["log_path"])),
            result_path=Path(str(raw["result_path"])),
            command=[str(item) for item in raw.get("command", [])],
            error=raw.get("error"),
        )


class RepairTaskStore:
    def __init__(self, tasks_root: Path) -> None:
        self.tasks_root = tasks_root
        self._lock = threading.Lock()

    def list_tasks(self) -> list[dict[str, Any]]:
        if not self.tasks_root.exists():
            return []
        rows = []
        for meta_path in sorted(self.tasks_root.glob("*/*/task.json"), reverse=True):
            rows.append(read_json(meta_path, {}))
        return rows

    def get_task(self, task_id: str) -> RepairTask:
        for raw in self.list_tasks():
            if raw.get("id") == task_id:
                return RepairTask.from_dict(raw)
        raise KeyError(task_id)

    def save_task(self, task: RepairTask) -> None:
        with self._lock:
            write_json(task.work_dir / "task.json", task.to_dict())

    def delete_task(self, task_id: str) -> None:
        task = self.get_task(task_id)
        if task.work_dir.exists():
            shutil.rmtree(task.work_dir)


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
