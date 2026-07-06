from __future__ import annotations

from typing import Any

from .repair_store import RepairTask, write_json
from .repair_support import now


def queue_repair_task(task: RepairTask) -> RepairTask:
    task.status = "queued"
    task.error = None
    task.updated_at = now()
    return task


def start_repair_task(task: RepairTask, command: list[str]) -> RepairTask:
    task.status = "running"
    task.error = None
    task.updated_at = now()
    task.command = command
    return task


def fail_repair_task(task: RepairTask, error: str) -> RepairTask:
    task.status = "failed"
    task.error = error
    task.updated_at = now()
    return task


def apply_repair_final_result(task: RepairTask, result: dict[str, Any]) -> RepairTask:
    final_status = result.get("status")
    if final_status == "skipped_unrepairable":
        task.status = "blocked"
        task.error = str(result.get("summary") or "blocked or unrepairable")
        write_json(
            task.work_dir / "blocked.json",
            {
                "status": "blocked",
                "source_id": task.source_id,
                "summary": task.error,
                "next_steps": result.get("next_steps") if isinstance(result.get("next_steps"), list) else [],
                "updated_at": now(),
            },
        )
    elif final_status in {"fixed", "needs_review"}:
        task.status = "succeeded"
        task.error = None
    else:
        task.status = "failed"
        task.error = str(result.get("summary") or f"codex returned status {final_status}")
    task.updated_at = now()
    return task
