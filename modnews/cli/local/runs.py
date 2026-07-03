from __future__ import annotations

from datetime import datetime
from typing import Any

from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews_pipeline.progress import BUS, emit


class RunsLocalMixin:
    def run_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-main")
        task_id = str(payload.get("task_id") or f"pipeline-{run_id}")
        runs = RunRepository(self.project_root)
        runs.create(run_id, payload)
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
        self.container.event_queue.run(task_id)
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
