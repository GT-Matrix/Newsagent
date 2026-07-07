from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modnews.core.event_queue import EventQueue
from modnews.service.pipeline.registry import PipelineRegistry
from modnews.service.pipeline.run_state import append_step_callback_events, update_run_state


@dataclass(slots=True)
class PipelineEventRuntime:
    registry: PipelineRegistry
    event_queue: EventQueue | None

    def handle(self, event: dict[str, object], *, event_type: str) -> list[dict[str, object]]:
        if self.event_queue is None:
            return []
        if event_type == "task.completed":
            callback_events = self._notify(event, handler_name="on_task_completed")
            self._dispatch_followups(event, failed=False)
            return callback_events
        if event_type == "task.failed":
            callback_events = self._notify(event, handler_name="on_task_failed", failed=True)
            self._dispatch_followups(event, failed=True)
            return callback_events
        if event_type == "task.blocked":
            return self._notify(event, handler_name="on_task_blocked", blocked=True)
        return []

    def _notify(
        self,
        event: dict[str, object],
        *,
        handler_name: str,
        failed: bool = False,
        blocked: bool = False,
    ) -> list[dict[str, object]]:
        update_run_state(self.event_queue, event, failed=failed, blocked=blocked)
        callback_events = self.registry.notify(handler_name, event, self.event_queue)
        if callback_events:
            update_run_state(self.event_queue, event, failed=failed, blocked=blocked)
            self._persist_callback_events(event, callback_events)
        return callback_events

    def _dispatch_followups(self, event: dict[str, object], *, failed: bool) -> None:
        if failed or self.event_queue is None:
            return
        for task in self.registry.plan_followup(event):
            self.event_queue.submit(task)

    def _persist_callback_events(self, event: dict[str, object], callback_events: list[dict[str, object]]) -> None:
        task = event.get("task")
        if not isinstance(task, dict):
            return
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        project_root = payload.get("project_root")
        run_id = task.get("pipeline_run_id")
        if not project_root or not run_id:
            return
        append_step_callback_events(Path(str(project_root)), str(run_id), callback_events)
