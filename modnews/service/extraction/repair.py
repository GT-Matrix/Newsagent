from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths
from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_creation import create_repair_task
from modnews.service.extraction.repair_lifecycle import run_and_promote_repair_task
from modnews.service.extraction.repair_store import RepairTask, RepairTaskStore


class RepairManager:
    def __init__(self, project_root: Path, registry: ExtractorRegistry) -> None:
        self.project_root = project_root
        self.registry = registry
        self.tasks_root = runtime_paths(project_root).agent_work_dir / "extractors"
        self.store = RepairTaskStore(self.tasks_root)

    def list_tasks(self) -> list[dict[str, Any]]:
        return self.store.list_tasks()

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self.store.get_task_dict(task_id)

    def delete_task(self, task_id: str) -> None:
        self.store.delete_task(task_id)

    def promote_task(self, task_id: str) -> RepairTask:
        from modnews.service.extraction.repair_promote import promote_repair_task

        task = promote_repair_task(self.project_root, self.registry, self._load_task(task_id))
        self._save_task(task)
        return task

    def retry_task(self, task_id: str) -> RepairTask:
        from modnews.service.extraction.repair_support import now

        task = self._load_task(task_id)
        task.status = "queued"
        task.error = None
        task.updated_at = now()
        self._save_task(task)
        return task

    def create_task(
        self,
        source_id: str,
        reason: str,
        source_metadata: dict[str, Any] | None = None,
    ) -> RepairTask:
        task = create_repair_task(
            tasks_root=self.tasks_root,
            registry=self.registry,
            source_id=source_id,
            reason=reason,
            source_metadata=source_metadata,
        )
        self._save_task(task)
        return task

    def run_task(self, task_id: str) -> None:
        task = run_and_promote_repair_task(
            project_root=self.project_root,
            registry=self.registry,
            task=self._load_task(task_id),
        )
        self._save_task(task)

    def _load_task(self, task_id: str) -> RepairTask:
        return self.store.get_task(task_id)

    def _save_task(self, task: RepairTask) -> None:
        self.store.save_task(task)
