from __future__ import annotations

import json
from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.repository.runs import RunRepository
from modnews.core.config import apply_runtime_overrides, load_config
from modnews_pipeline.pipeline import run_pipeline


def combine_ingest_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    run_id = task.pipeline_run_id or str(task.payload["run_id"])
    runs = RunRepository(project_root)
    checkpoints = CheckpointManager(project_root)
    try:
        record = runs.get(run_id)
    except KeyError:
        runs.create(run_id, {"source": "pipeline_task_graph"})
        record = runs.get(run_id)
    items: list[dict[str, object]] = []
    input_refs: dict[str, str] = {}
    for checkpoint_path in record.get("checkpoints", []):
        checkpoint_file = Path(str(checkpoint_path))
        if not checkpoint_file.exists():
            continue
        checkpoint = json.loads(checkpoint_file.read_text(encoding="utf-8"))
        step_id = str(checkpoint.get("step_id") or "")
        if not step_id.startswith("ingest/"):
            continue
        artifact_path = checkpoint.get("output_refs", {}).get("items")
        if not artifact_path:
            continue
        artifact_file = Path(str(artifact_path))
        rows = json.loads(artifact_file.read_text(encoding="utf-8"))
        if isinstance(rows, list):
            items.extend(row for row in rows if isinstance(row, dict))
            input_refs[step_id] = str(artifact_file)
    artifact_path = checkpoints.write_artifact(run_id, "pipeline/combine_ingest", task.id, "items.json", items)
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": "pipeline/combine_ingest",
        "task_id": task.id,
        "status": "succeeded",
        "input_refs": input_refs,
        "output_refs": {"items": str(artifact_path)},
        "stats": {"item_count": len(items)},
        "error": None,
    }
    checkpoint_path = checkpoints.write(run_id, "pipeline/combine_ingest", task.id, checkpoint_payload)
    run_checkpoints = list(record.get("checkpoints", []))
    run_checkpoints.append(str(checkpoint_path))
    runs.update(run_id, checkpoints=run_checkpoints, combined_ingest_path=str(artifact_path))
    return {
        "checkpoint_path": str(checkpoint_path),
        "combined_ingest_path": str(artifact_path),
        "stats": checkpoint_payload["stats"],
    }


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
