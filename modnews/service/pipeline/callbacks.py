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
    task_id = str(task.get("id") or "")
    for dependent in queue.dependents_of(task_id):
        if dependent.type == "classify.run_legacy":
            queue.patch_payload(dependent.id, {"input_path": str(combined_path)})
