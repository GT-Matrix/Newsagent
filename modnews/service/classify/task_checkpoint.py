from __future__ import annotations

from pathlib import Path

from modnews.core.config import ClassificationConfig
from modnews.core.task import TaskEvent
from modnews.service.pipeline.checkpoint import CheckpointManager

from .checkpoint import build_checkpoint_meta, write_outputs, write_run_output_artifacts
from .io import append_run_checkpoint
from .state import ClassifyState


def write_classify_task_checkpoint(
    project_root: Path,
    run_id: str,
    task: TaskEvent,
    step_id: str,
    input_path: Path,
    state: ClassifyState,
    config: ClassificationConfig,
    *,
    auto_publish: bool = False,
) -> dict[str, object]:
    checkpoint = CheckpointManager(project_root)
    meta = build_checkpoint_meta(
        state.items,
        state.event_records,
        state.discarded,
        stage=state.stage,
        processed_candidates=state.processed_candidates,
        total_candidates=state.total_candidates,
        merged_event_count=state.merged_event_count,
    )
    output_refs = write_run_output_artifacts(checkpoint, run_id, step_id, task.id, state.items, state.event_records, state.discarded, meta)
    if bool(task.payload.get("write_fixed_outputs")):
        write_outputs(config, state.items, state.event_records, state.discarded, meta)
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": step_id,
        "task_id": task.id,
        "status": "succeeded",
        "input_refs": {"items": str(input_path)},
        "output_refs": output_refs,
        "stats": {
            "item_count": len(state.items),
            "event_count": len(state.events),
            "discarded_count": len(state.discarded),
            "merged_event_count": state.merged_event_count,
        },
        "error": None,
    }
    checkpoint_path = checkpoint.write(run_id, step_id, task.id, checkpoint_payload)
    append_run_checkpoint(project_root, run_id, checkpoint_path)
    result: dict[str, object] = {
        "checkpoint_path": str(checkpoint_path),
        "stats": checkpoint_payload["stats"],
    }
    if auto_publish:
        result["auto_publish_checkpoint"] = str(checkpoint_path)
    return result
