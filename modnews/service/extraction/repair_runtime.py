from __future__ import annotations

import subprocess

from modnews.service.extraction.repair_state_ops import (
    apply_repair_final_result,
    fail_repair_task,
    start_repair_task,
)
from modnews.service.extraction.repair_codex import build_codex_command, validate_final_result
from modnews.service.extraction.repair_store import RepairTask, read_json


def run_repair_task(task: RepairTask) -> RepairTask:
    command = build_codex_command(task)
    start_repair_task(task, command)
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
                fail_repair_task(task, result_error)
            else:
                apply_repair_final_result(task, read_json(task.result_path, {}))
        else:
            fail_repair_task(task, f"codex exited with code {process.returncode}")
    except Exception as exc:
        fail_repair_task(task, str(exc))
    return task
