from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.progress import BUS, emit
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.manager import PipelineManager
from modnews.service.pipeline.run_state import initialize_run_state, sync_run_state
from modnews.service.pipeline.runtime_store import overlay_run_record


@dataclass(slots=True)
class PipelineRuntimeFacade:
    project_root: Path
    queue: EventQueue
    pipeline_manager: PipelineManager

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-main")
        runs = RunRepository(self.project_root)
        descriptors = self.pipeline_manager.describe_steps()
        runs.create(run_id, payload)
        request = {
            "project_root": str(self.project_root),
            "run_id": run_id,
            "config": payload.get("config"),
            "only": payload.get("only"),
            "only_ingest_steps": payload.get("only_ingest_steps"),
            "disable_classification": payload.get("disable_classification"),
            "disable_report": payload.get("disable_report"),
        }
        planned = self.pipeline_manager.start_run(request)
        initialize_run_state(
            self.project_root,
            run_id,
            [self.queue.get(task["id"]) for task in planned["registered_tasks"]],
            pipeline_descriptors=descriptors,
        )
        runs.update(run_id, state="queued", task_ids=[task["id"] for task in planned["registered_tasks"]])
        if payload.get("background", True):
            return {"ok": True, "run": overlay_run_record(self.project_root, runs.get(run_id)), "tasks": planned["registered_tasks"]}
        BUS.clear()
        emit("pipeline_start", started_at=datetime.now().astimezone().isoformat(timespec="seconds"), run_id=run_id)
        self.queue.drain_ready()
        run_record = overlay_run_record(self.project_root, runs.get(run_id))
        tasks = self.run_tasks(run_id)
        ok = bool(tasks) and all(task.get("state") == "succeeded" for task in tasks)
        if ok:
            emit("pipeline_done", run_id=run_id, output_path=run_record.get("output_path"), stats=run_record.get("stats", {}))
        else:
            failed = next((task for task in tasks if task.get("state") in {"failed", "blocked", "cancelled"}), {})
            emit("pipeline_error", run_id=run_id, error=failed.get("status_reason") or failed.get("state"))
        return {"ok": ok, "run": run_record, "tasks": tasks}

    def resume(self, run_id: str) -> dict[str, Any]:
        runs = RunRepository(self.project_root)
        record = runs.get(run_id)
        before = self.run_tasks(run_id)
        self.queue.drain_ready()
        after = self.run_tasks(run_id)
        remaining = [task for task in after if task["state"] in {"queued", "waiting", "running"}]
        state = "running" if remaining else record.get("state", "queued")
        if state in {"queued", "cancelled"}:
            state = "queued"
        sync_run_state(
            self.project_root,
            self.queue,
            run_id,
            override_state=state,
            pipeline_descriptors=self.pipeline_manager.describe_steps(),
        )
        return {"ok": True, "run": overlay_run_record(self.project_root, runs.get(run_id)), "before": before, "tasks": after}

    def cancel(self, run_id: str, reason: str = "cancelled by user") -> dict[str, Any]:
        runs = RunRepository(self.project_root)
        runs.get(run_id)
        cancelled = []
        skipped = []
        for task in self.queue.list():
            if task.pipeline_run_id != run_id:
                continue
            if task.state in {"queued", "waiting", "blocked"}:
                cancelled_task = self.queue.cancel(task.id, reason=reason)
                cancelled.append(cancelled_task.to_dict())
            else:
                skipped.append(task.to_dict())
        sync_run_state(
            self.project_root,
            self.queue,
            run_id,
            override_state="cancelled",
            extra_updates={"cancel_reason": reason},
            pipeline_descriptors=self.pipeline_manager.describe_steps(),
        )
        return {"ok": True, "run": overlay_run_record(self.project_root, runs.get(run_id)), "cancelled_tasks": cancelled, "skipped_tasks": skipped}

    def run_tasks(self, run_id: str) -> list[dict[str, Any]]:
        return [task.to_dict() for task in self.queue.list() if task.pipeline_run_id == run_id]
