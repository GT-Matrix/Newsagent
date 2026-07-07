from __future__ import annotations

from modnews.core.task import TaskBlocked


def build_repair_task_result(
    repair_task: dict[str, object],
    log_summary: dict[str, object],
) -> dict[str, object]:
    status = str(repair_task.get("status") or "")
    if status == "blocked":
        raise TaskBlocked(
            str(repair_task.get("error") or "repair task blocked"),
            details={"repair_task": repair_task, **log_summary},
        )
    if status != "succeeded":
        error = str(repair_task.get("error") or f"repair task ended as {status}")
        raise RuntimeError(f"{error}; codex_log={log_summary.get('codex_log_path')}")
    return {"repair_task": repair_task, **log_summary}
