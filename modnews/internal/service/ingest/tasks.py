from __future__ import annotations

import json
from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.internal.service.ingest.registry import default_ingest_registry
from modnews.internal.service.pipeline.checkpoint import CheckpointManager
from modnews.repository.runs import RunRepository
from modnews_pipeline.config import load_config
from modnews_pipeline.context import PipelineContext


def run_ingest_step_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    step_id = str(task.payload["step_id"])
    run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
    config = load_config(task.payload.get("config"))
    ctx = PipelineContext.create(config)
    ctx.work_dir.mkdir(parents=True, exist_ok=True)
    registry = default_ingest_registry()
    step_cls = registry.get(step_id)
    options = task.payload.get("options")
    step = step_cls(**(options if isinstance(options, dict) else {}))
    items, result = step.run(ctx)

    checkpoint = CheckpointManager(project_root)
    output_refs = {"step_output": result.output_path} if result.output_path else {}
    artifact_payload = [item.to_dict() for item in items]
    artifact_path = checkpoint.write_artifact(run_id, f"ingest/{step_id}", task.id, "items.json", artifact_payload)
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": f"ingest/{step_id}",
        "task_id": task.id,
        "status": "succeeded" if not result.errors else "completed_with_errors",
        "input_refs": {},
        "output_refs": {**output_refs, "items": str(artifact_path)},
        "stats": {"item_count": len(items), "error_count": len(result.errors)},
        "error": "; ".join(result.errors) if result.errors else None,
    }
    checkpoint_path = checkpoint.write(run_id, f"ingest/{step_id}", task.id, checkpoint_payload)
    _append_run_checkpoint(project_root, run_id, checkpoint_path)
    return {
        "step": result.to_dict(),
        "item_count": len(items),
        "checkpoint_path": str(checkpoint_path),
        "artifact_path": str(artifact_path),
    }


def _append_run_checkpoint(project_root: Path, run_id: str, checkpoint_path: Path) -> None:
    runs = RunRepository(project_root)
    try:
        record = runs.get(run_id)
    except KeyError:
        runs.create(run_id, {"source": "manual_ingest_task"})
        record = runs.get(run_id)
    checkpoints = list(record.get("checkpoints", []))
    checkpoints.append(str(checkpoint_path))
    runs.update(run_id, checkpoints=checkpoints)
