from __future__ import annotations

from typing import Any

from modnews.core.event_queue import EventQueue


def patch_completed_outputs(queue: EventQueue, event: dict[str, Any]) -> None:
    task = event.get("task")
    result = event.get("result")
    if not isinstance(task, dict) or not isinstance(result, dict):
        return
    combined_path = result.get("combined_ingest_path")
    if not combined_path:
        return
    run_id = task.get("pipeline_run_id")
    for queued_task in queue.list():
        if queued_task.pipeline_run_id != run_id:
            continue
        if queued_task.type.startswith("classify."):
            queue.patch_payload(queued_task.id, {"input_path": str(combined_path)})
