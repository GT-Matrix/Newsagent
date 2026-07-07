from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TASKS_BY_ROOT: dict[str, dict[str, dict[str, Any]]] = {}
_ROOT_LOCK = threading.Lock()


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
        self._root_key = str(tasks_root.resolve())
        self._lock = threading.Lock()
        with _ROOT_LOCK:
            _TASKS_BY_ROOT.setdefault(self._root_key, {})

    def list_tasks(self) -> list[dict[str, Any]]:
        rows = [dict(row) for row in _TASKS_BY_ROOT.get(self._root_key, {}).values()]
        return sorted(rows, key=lambda row: str(row.get("updated_at", "")), reverse=True)

    def get_task(self, task_id: str) -> RepairTask:
        for raw in self.list_tasks():
            if raw.get("id") == task_id:
                return RepairTask.from_dict(raw)
        raise KeyError(task_id)

    def get_task_dict(
        self,
        task_id: str,
        *,
        include_log_tail: bool = True,
        max_log_chars: int = 40000,
    ) -> dict[str, Any]:
        task = self.get_task(task_id)
        payload = task.to_dict()
        if include_log_tail:
            payload["log_tail"] = self.read_log(task, max_chars=max_log_chars)
        return payload

    def save_task(self, task: RepairTask) -> None:
        with self._lock:
            _TASKS_BY_ROOT.setdefault(self._root_key, {})[task.id] = task.to_dict()

    def delete_task(self, task_id: str) -> None:
        task = self.get_task(task_id)
        if task.work_dir.exists():
            shutil.rmtree(task.work_dir)
        with self._lock:
            _TASKS_BY_ROOT.get(self._root_key, {}).pop(task_id, None)

    def read_log(self, task: RepairTask | str, *, max_chars: int = 40000) -> str:
        current = self.get_task(task) if isinstance(task, str) else task
        if current.log_path.exists():
            text = current.log_path.read_text(encoding="utf-8", errors="replace")
            return text[-max_chars:]
        return ""

    def codex_log_summary(
        self,
        task: RepairTask | str,
        *,
        max_chars: int = 12000,
    ) -> dict[str, Any]:
        current = self.get_task(task) if isinstance(task, str) else task
        log_path = current.log_path
        if not log_path.exists():
            return {
                "codex_log_path": str(log_path) if str(log_path) else None,
                "codex_log_tail": "",
                "codex_log_bytes": 0,
            }
        text = log_path.read_text(encoding="utf-8", errors="replace")
        return {
            "codex_log_path": str(log_path),
            "codex_log_tail": text[-max_chars:],
            "codex_log_bytes": len(text.encode("utf-8", errors="replace")),
        }


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
