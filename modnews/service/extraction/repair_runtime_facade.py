from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from modnews.service.pipeline.step import PipelineStepDescriptor
from modnews.service.task_entrypoints import run_planned_tasks
from modnews.service.extraction.repair_manager import RepairManager
from modnews.service.extraction.repair_queue import build_repair_task_event
from modnews.service.extraction.registry import registry_from_project


@dataclass(slots=True)
class RepairRuntimeFacade:
    project_root: Path
    queue: Any
    queue_show: Callable[[str], dict[str, Any]]
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None

    def list_tasks(self) -> list[dict[str, Any]]:
        return self._manager().list_tasks()

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._manager().get_task(task_id)

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = self._manager().create_task(
            str(payload["source_id"]),
            reason=str(payload.get("reason") or "manual repair request"),
        )
        queue_submission = None
        if bool(payload.get("auto_start", True)):
            queue_submission = self._submit_task(task.id, task.source_id)
        return {
            "ok": True,
            "item": task.to_dict(),
            "task": queue_submission["task"] if isinstance(queue_submission, dict) else None,
            "run_id": queue_submission.get("run_id") if isinstance(queue_submission, dict) else None,
            "run": queue_submission.get("run") if isinstance(queue_submission, dict) else None,
        }

    def retry_task(self, task_id: str) -> dict[str, Any]:
        task = self._manager().retry_task(task_id)
        queue_submission = self._submit_task(task.id, task.source_id)
        return {
            "ok": True,
            "item": task.to_dict(),
            "task": queue_submission["task"],
            "run_id": queue_submission.get("run_id"),
            "run": queue_submission.get("run"),
        }

    def promote_task(self, task_id: str) -> dict[str, Any]:
        task = self._manager().promote_task(task_id)
        return {"ok": True, "item": task.to_dict()}

    def delete_task(self, task_id: str) -> dict[str, Any]:
        self._manager().delete_task(task_id)
        return {"ok": True}

    def _manager(self) -> RepairManager:
        return RepairManager(self.project_root, registry_from_project(self.project_root))

    def _submit_task(self, repair_task_id: str, source_id: str) -> dict[str, Any]:
        run_id = f"repair-{repair_task_id}"
        task = build_repair_task_event(
            project_root=self.project_root,
            repair_task_id=repair_task_id,
            source_id=source_id,
            run_id=run_id,
            task_id=f"repair-{repair_task_id}",
        )
        result = run_planned_tasks(
            project_root=self.project_root,
            queue=self.queue,
            queue_show=self.queue_show,
            run_id=run_id,
            tasks=[task],
            create_payload={
                "source": "manual_repair_entrypoint",
                "repair_task_id": repair_task_id,
                "source_id": source_id,
            },
            pipeline_descriptors=self.pipeline_descriptors,
        )
        return {
            "run_id": result["run_id"],
            "run": result["run"],
            "task": result["tasks"][0] if result["tasks"] else {},
        }
