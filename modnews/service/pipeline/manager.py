from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.core.task import TERMINAL_STATES, TaskEvent
from modnews.repository.runs import RunRepository


@dataclass(slots=True)
class PipelineManager:
    steps: list[Any] = field(default_factory=list)
    event_queue: EventQueue | None = None
    event_router: EventRouter | None = None
    ingest_registry: Any | None = None

    def bind(self, event_queue: EventQueue, event_router: EventRouter) -> None:
        self.event_queue = event_queue
        self.event_router = event_router

    def register_step(self, step: Any) -> None:
        self.steps.append(step)

    def start_run(self, request: dict[str, Any], *, submit: bool = False) -> dict[str, Any]:
        run_id = str(request.get("run_id") or "local")
        tasks: list[TaskEvent] = []
        for step in self.steps:
            tasks.extend(step.plan({"run_id": run_id, "request": request}))
        if self.event_queue:
            for task in tasks:
                if submit:
                    self.event_queue.submit(task)
                else:
                    self.event_queue.register(task)
        return {"run_id": run_id, "registered_tasks": [task.to_dict() for task in tasks]}

    def on_task_completed(self, event: dict[str, Any]) -> None:
        self._patch_completed_outputs(event)
        self._update_run_state(event)
        self._dispatch_next(event, failed=False)

    def on_task_failed(self, event: dict[str, Any]) -> None:
        self._update_run_state(event, failed=True)
        self._dispatch_next(event, failed=True)

    def _dispatch_next(self, event: dict[str, Any], *, failed: bool) -> None:
        if failed:
            return
        if not self.event_queue:
            return
        for step in self.steps:
            for task in step.plan({}, completed_event=event):
                self.event_queue.submit(task)

    def _patch_completed_outputs(self, event: dict[str, Any]) -> None:
        if not self.event_queue:
            return
        task = event.get("task")
        result = event.get("result")
        if not isinstance(task, dict) or not isinstance(result, dict):
            return
        combined_path = result.get("combined_ingest_path")
        if not combined_path:
            return
        task_id = str(task.get("id") or "")
        for dependent in self.event_queue.dependents_of(task_id):
            if dependent.type == "classify.run_legacy":
                self.event_queue.patch_payload(dependent.id, {"input_path": str(combined_path)})

    def _update_run_state(self, event: dict[str, Any], *, failed: bool = False) -> None:
        if not self.event_queue:
            return
        task = event.get("task")
        result = event.get("result")
        if not isinstance(task, dict):
            return
        run_id = task.get("pipeline_run_id")
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        project_root = payload.get("project_root")
        if not run_id or not project_root:
            return
        updates: dict[str, Any] = {"state": "failed" if failed else "running"}
        if isinstance(result, dict):
            for key in ("checkpoint_path", "combined_ingest_path", "stats"):
                if key in result:
                    updates[key] = result[key]
            if "error" in result:
                updates["error"] = result["error"]
        run_tasks = [item for item in self.event_queue.list() if item.pipeline_run_id == run_id]
        if run_tasks:
            if any(item.state == "failed" for item in run_tasks):
                updates["state"] = "failed"
            elif all(item.state in TERMINAL_STATES for item in run_tasks):
                updates["state"] = "succeeded"
        try:
            RunRepository(Path(str(project_root))).update(str(run_id), **updates)
        except KeyError:
            return
