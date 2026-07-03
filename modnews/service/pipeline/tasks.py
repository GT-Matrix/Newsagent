from __future__ import annotations

from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.repository.runs import RunRepository
from modnews_pipeline.config import apply_runtime_overrides, load_config
from modnews_pipeline.pipeline import run_pipeline


def run_legacy_pipeline_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    run_id = task.pipeline_run_id or str(task.payload["run_id"])
    runs = RunRepository(project_root)
    checkpoints = CheckpointManager(project_root)
    runs.update(run_id, state="running", task_id=task.id)
    try:
        config = load_config(task.payload.get("config"))
        apply_runtime_overrides(
            config,
            only_ingest_steps=task.payload.get("only_ingest_steps") or task.payload.get("only"),
            disable_classification=bool(task.payload.get("disable_classification")),
        )
        result = run_pipeline(config)
        checkpoint_payload = {
            "run_id": run_id,
            "step_id": "pipeline",
            "task_id": task.id,
            "status": "succeeded",
            "output_refs": {"combined_news": str(result.output_path)},
            "stats": {"total": len(result.items), "events": len(result.events)},
            "error": None,
        }
        checkpoint_path = checkpoints.write(run_id, "pipeline", task.id, checkpoint_payload)
        runs.update(
            run_id,
            state="succeeded",
            output_path=str(result.output_path),
            checkpoint_path=str(checkpoint_path),
            stats=checkpoint_payload["stats"],
        )
        return {"run": runs.get(run_id), "checkpoint_path": str(checkpoint_path), "auto_publish_checkpoint": str(checkpoint_path)}
    except Exception as exc:
        checkpoint_payload = {
            "run_id": run_id,
            "step_id": "pipeline",
            "task_id": task.id,
            "status": "failed",
            "output_refs": {},
            "stats": {},
            "error": str(exc),
        }
        checkpoint_path = checkpoints.write(run_id, "pipeline", task.id, checkpoint_payload)
        runs.update(run_id, state="failed", error=str(exc), checkpoint_path=str(checkpoint_path))
        raise
