from __future__ import annotations

import subprocess
from typing import Any

from modnews.service.extraction.repair_store import RepairTask, read_json, write_json
from modnews.service.extraction.repair_support import build_codex_command, now, validate_final_result


def run_repair_task(task: RepairTask) -> RepairTask:
    command = build_codex_command(task)
    task.status = "running"
    task.updated_at = now()
    task.command = command
    try:
        with task.log_path.open("w", encoding="utf-8") as log:
            process = subprocess.run(
                command,
                cwd=task.work_dir,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=1800,
                check=False,
            )
        if process.returncode == 0:
            result_error = validate_final_result(task.result_path)
            if result_error:
                task.status = "failed"
                task.error = result_error
            else:
                apply_final_status(task, read_json(task.result_path, {}))
        else:
            task.status = "failed"
            task.error = f"codex exited with code {process.returncode}"
    except Exception as exc:
        task.status = "failed"
        task.error = str(exc)
    finally:
        task.updated_at = now()
    return task


def apply_final_status(task: RepairTask, result: dict[str, Any]) -> None:
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
