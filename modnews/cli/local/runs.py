from __future__ import annotations

from datetime import datetime
from typing import Any

from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.core.progress import BUS, emit


class RunsLocalMixin:
    def run_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-main")
        runs = RunRepository(self.project_root)
        runs.create(run_id, payload)
        if not payload.get("legacy_pipeline"):
            request = {
                "project_root": str(self.project_root),
                "run_id": run_id,
                "config": payload.get("config"),
                "only": payload.get("only"),
                "only_ingest_steps": payload.get("only_ingest_steps"),
                "disable_classification": payload.get("disable_classification"),
            }
            planned = self.container.pipeline_manager.start_run(request)
            runs.update(run_id, state="queued", task_ids=[task["id"] for task in planned["registered_tasks"]])
            if not payload.get("background", True):
                BUS.clear()
                emit("pipeline_start", started_at=datetime.now().astimezone().isoformat(timespec="seconds"), run_id=run_id)
                self.container.event_queue.drain_ready()
            return {"ok": True, "run": runs.get(run_id), "tasks": planned["registered_tasks"]}

        task_id = str(payload.get("task_id") or f"pipeline-{run_id}")
        task = TaskEvent(
            id=task_id,
            type="pipeline.run_legacy",
            pipeline_run_id=run_id,
            step_id="pipeline",
            payload={
                "project_root": str(self.project_root),
                "run_id": run_id,
                "config": payload.get("config"),
                "only": payload.get("only"),
                "only_ingest_steps": payload.get("only_ingest_steps"),
                "disable_classification": payload.get("disable_classification"),
            },
            concurrency_key="pipeline",
            max_concurrency=1,
        )
        self.container.event_queue.register(task)
        runs.update(run_id, state="queued", task_id=task_id)
        if payload.get("background", True):
            return {"ok": True, "run": runs.get(run_id), "task": task.to_dict()}
        BUS.clear()
        emit("pipeline_start", started_at=datetime.now().astimezone().isoformat(timespec="seconds"), run_id=run_id)
        self.container.event_queue.drain_ready()
        task_payload = self.queue_show(task_id)
        run_record = runs.get(run_id)
        ok = task_payload.get("state") == "succeeded"
        if ok:
            emit("pipeline_done", run_id=run_id, output_path=run_record.get("output_path"), stats=run_record.get("stats", {}))
        else:
            emit("pipeline_error", run_id=run_id, error=task_payload.get("result", {}).get("error"))
        return {"ok": ok, "run": run_record, "task": task_payload}

    def run_list(self) -> list[dict[str, Any]]:
        return RunRepository(self.project_root).list()

    def run_status(self, run_id: str | None = None) -> dict[str, Any]:
        if run_id:
            return RunRepository(self.project_root).get(run_id)
        return {"runs": self.run_list(), "state": self.state()}

    def run_resume(self, run_id: str) -> dict[str, Any]:
        runs = RunRepository(self.project_root)
        record = runs.get(run_id)
        before = self._run_tasks(run_id)
        self.container.event_queue.drain_ready()
        after = self._run_tasks(run_id)
        remaining = [task for task in after if task["state"] in {"queued", "blocked", "running"}]
        state = "running" if remaining else record.get("state", "queued")
        if state in {"queued", "cancelled"}:
            state = "queued"
        runs.update(run_id, state=state)
        return {"ok": True, "run": runs.get(run_id), "before": before, "tasks": after}

    def run_cancel(self, run_id: str, reason: str = "cancelled by user") -> dict[str, Any]:
        runs = RunRepository(self.project_root)
        runs.get(run_id)
        cancelled = []
        skipped = []
        for task in self.container.event_queue.list():
            if task.pipeline_run_id != run_id:
                continue
            if task.state in {"queued", "blocked"}:
                cancelled_task = self.container.event_queue.cancel(task.id, reason=reason)
                cancelled.append(cancelled_task.to_dict())
            else:
                skipped.append(task.to_dict())
        runs.update(run_id, state="cancelled", cancel_reason=reason)
        return {"ok": True, "run": runs.get(run_id), "cancelled_tasks": cancelled, "skipped_tasks": skipped}

    def _run_tasks(self, run_id: str) -> list[dict[str, Any]]:
        return [task.to_dict() for task in self.container.event_queue.list() if task.pipeline_run_id == run_id]
