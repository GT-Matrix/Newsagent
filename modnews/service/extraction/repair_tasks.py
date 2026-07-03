from __future__ import annotations

from pathlib import Path

from modnews.core.progress import emit
from modnews.core.task import TaskBlocked, TaskEvent
from modnews.service.extraction.registry import registry_from_project
from modnews.service.extraction.repair import RepairManager

MAX_CODEX_LOG_TAIL_CHARS = 12000


def run_codex_repair_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    repair_task_id = str(task.payload["repair_task_id"])
    manager = RepairManager(project_root, registry_from_project(project_root))
    manager.run_task(repair_task_id)
    repair_task = manager.get_task(repair_task_id)
    log_summary = _codex_log_summary(repair_task)
    emit(
        "codex_repair_log",
        repair_task_id=repair_task_id,
        source_id=repair_task.get("source_id"),
        status=repair_task.get("status"),
        **log_summary,
    )
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


def _codex_log_summary(repair_task: dict[str, object]) -> dict[str, object]:
    log_path = Path(str(repair_task.get("log_path") or ""))
    if not log_path.exists():
        return {"codex_log_path": str(log_path) if str(log_path) else None, "codex_log_tail": "", "codex_log_bytes": 0}
    text = log_path.read_text(encoding="utf-8", errors="replace")
    return {
        "codex_log_path": str(log_path),
        "codex_log_tail": text[-MAX_CODEX_LOG_TAIL_CHARS:],
        "codex_log_bytes": len(text.encode("utf-8", errors="replace")),
    }
