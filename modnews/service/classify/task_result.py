from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modnews.core.config import ClassificationConfig
from modnews.core.task import TaskEvent
from modnews.service.pipeline.checkpoint import CheckpointManager

from .checkpoint import write_outputs, write_run_output_artifacts
from .io import append_run_checkpoint
from .runner import ClassifyRunResult


@dataclass(frozen=True, slots=True)
class ClassifyTaskSnapshot:
    step_id: str
    checkpoint_meta: dict[str, object]
    stats: dict[str, object]


def build_classify_checkpoint_meta(run_result: ClassifyRunResult) -> dict[str, object]:
    state = run_result.state
    final_step = run_result.last_step_result
    checkpoint_meta = final_step.checkpoint_meta if final_step and final_step.checkpoint_meta else {"stage": state.stage}
    return dict(checkpoint_meta)


def build_classify_run_stats(run_result: ClassifyRunResult) -> dict[str, object]:
    state = run_result.state
    final_step = run_result.last_step_result
    stats = final_step.stats if final_step and final_step.stats else {
        "item_count": len(state.items),
        "event_count": len(state.events),
        "discarded_count": len(state.discarded),
        "processed_candidates": state.processed_candidates,
        "total_candidates": state.total_candidates,
        "merged_event_count": state.merged_event_count,
    }
    return dict(stats)


def build_classify_task_snapshot(
    *,
    step_id: str,
    run_result: ClassifyRunResult,
) -> ClassifyTaskSnapshot:
    return ClassifyTaskSnapshot(
        step_id=step_id,
        checkpoint_meta=build_classify_checkpoint_meta(run_result),
        stats=build_classify_run_stats(run_result),
    )


def persist_classify_task_result(
    *,
    project_root: Path,
    run_id: str,
    task: TaskEvent,
    input_path: Path,
    run_result: ClassifyRunResult,
    config: ClassificationConfig,
    snapshot: ClassifyTaskSnapshot,
    auto_publish: bool = False,
) -> dict[str, object]:
    checkpoint = CheckpointManager(project_root)
    state = run_result.state
    output_refs = write_run_output_artifacts(
        checkpoint,
        run_id,
        snapshot.step_id,
        task.id,
        state.items,
        state.event_records,
        state.discarded,
        snapshot.checkpoint_meta,
    )
    if bool(task.payload.get("write_fixed_outputs")):
        write_outputs(config, state.items, state.event_records, state.discarded, snapshot.checkpoint_meta)
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": snapshot.step_id,
        "task_id": task.id,
        "status": "succeeded",
        "input_refs": {"items": str(input_path)},
        "output_refs": output_refs,
        "stats": snapshot.stats,
        "error": None,
    }
    checkpoint_path = checkpoint.write(run_id, snapshot.step_id, task.id, checkpoint_payload)
    append_run_checkpoint(project_root, run_id, checkpoint_path)
    result: dict[str, Any] = {
        "checkpoint_path": str(checkpoint_path),
        "stats": snapshot.stats,
    }
    if auto_publish:
        result["auto_publish_checkpoint"] = str(checkpoint_path)
    return result
