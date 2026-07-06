from __future__ import annotations

from typing import Any

from modnews.core.event_queue import EventQueue


def patch_completed_outputs(queue: EventQueue, event: dict[str, Any]) -> None:
    task = event.get("task")
    result = event.get("result")
    if not isinstance(task, dict) or not isinstance(result, dict):
        return
    run_id = task.get("pipeline_run_id")
    task_type = task.get("type")
    combined_path = result.get("combined_ingest_path")
    checkpoint_path = result.get("checkpoint_path")
    for queued_task in queue.list():
        if queued_task.pipeline_run_id != run_id:
            continue
        if combined_path and queued_task.type.startswith("classify."):
            queue.patch_payload(queued_task.id, {"input_path": str(combined_path)})
        if queued_task.type == "report.generate":
            if task_type == "classify.clustered_event_merge" and checkpoint_path:
                queue.patch_payload(queued_task.id, {"input_path": str(checkpoint_path)})
