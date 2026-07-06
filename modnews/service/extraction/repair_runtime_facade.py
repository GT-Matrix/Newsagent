from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from modnews.service.extraction.repair_manager import RepairManager
from modnews.service.extraction.repair_queue_runtime import submit_repair_queue_task_detail
from modnews.service.extraction.registry import registry_from_project


@dataclass(slots=True)
class RepairRuntimeFacade:
    project_root: Path
    queue: Any
    queue_show: Callable[[str], dict[str, Any]]

    def list_tasks(self) -> list[dict[str, Any]]:
        return self._manager().list_tasks()

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._manager().get_task(task_id)

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = self._manager().create_task(
            str(payload["source_id"]),
            reason=str(payload.get("reason") or "manual repair request"),
        )
        queue_task = None
        if bool(payload.get("auto_start", True)):
            queue_task = self._submit_task(task.id, task.source_id)
        return {"ok": True, "item": task.to_dict(), "task": queue_task}

    def retry_task(self, task_id: str) -> dict[str, Any]:
        task = self._manager().retry_task(task_id)
        queue_task = self._submit_task(task.id, task.source_id)
        return {"ok": True, "item": task.to_dict(), "task": queue_task}

    def promote_task(self, task_id: str) -> dict[str, Any]:
        task = self._manager().promote_task(task_id)
        return {"ok": True, "item": task.to_dict()}

    def delete_task(self, task_id: str) -> dict[str, Any]:
        self._manager().delete_task(task_id)
        return {"ok": True}

    def _manager(self) -> RepairManager:
        return RepairManager(self.project_root, registry_from_project(self.project_root))

    def _submit_task(self, repair_task_id: str, source_id: str) -> dict[str, Any]:
        submission = submit_repair_queue_task_detail(
            self.queue,
            queue_show=self.queue_show,
            project_root=self.project_root,
            repair_task_id=repair_task_id,
            source_id=source_id,
        )
        return submission["task"]
