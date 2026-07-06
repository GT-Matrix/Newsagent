from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_store import RepairTask
from modnews.service.extraction.repair_support import (
    now,
    write_bootstrap_extractor,
    write_contract_schema,
    write_final_schema,
    write_task_md,
)


def create_repair_task(
    *,
    tasks_root: Path,
    registry: ExtractorRegistry,
    source_id: str,
    reason: str,
    source_metadata: dict[str, Any] | None = None,
) -> RepairTask:
    try:
        record = registry.get(source_id)
        current_dir = record.current_dir
        bootstrap = False
    except Exception:
        current_dir = None
        bootstrap = True

    task_id = f"{source_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    work_dir = tasks_root / source_id / task_id
    work_dir.mkdir(parents=True, exist_ok=True)
    if current_dir:
        shutil.copytree(current_dir, work_dir / "current", dirs_exist_ok=True)
    else:
        write_bootstrap_extractor(work_dir / "current", source_id, source_metadata or {})

    (work_dir / "fixtures").mkdir(exist_ok=True)
    (work_dir / "schema").mkdir(exist_ok=True)
    result_path = work_dir / "result.json"
    log_path = work_dir / "codex.jsonl"
    write_contract_schema(work_dir / "schema" / "extractor_result.schema.json")
    write_final_schema(work_dir / "schema" / "final_message.schema.json")
    write_task_md(work_dir / "TASK.md", source_id, reason, source_metadata or {}, bootstrap=bootstrap)

    current_now = now()
    return RepairTask(
        id=task_id,
        source_id=source_id,
        status="queued",
        work_dir=work_dir,
        created_at=current_now,
        updated_at=current_now,
        log_path=log_path,
        result_path=result_path,
    )
