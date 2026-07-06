from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_store import RepairTask
from modnews.service.extraction.repair_support import (
    now,
    write_contract_schema,
    write_final_schema,
    write_task_md,
)
from modnews.service.extraction.repair_workspace import prepare_repair_workspace


def create_repair_task(
    *,
    tasks_root: Path,
    registry: ExtractorRegistry,
    source_id: str,
    reason: str,
    source_metadata: dict[str, Any] | None = None,
) -> RepairTask:
    workspace = prepare_repair_workspace(
        tasks_root=tasks_root,
        registry=registry,
        source_id=source_id,
        source_metadata=source_metadata,
    )
    write_contract_schema(workspace.work_dir / "schema" / "extractor_result.schema.json")
    write_final_schema(workspace.work_dir / "schema" / "final_message.schema.json")
    write_task_md(workspace.work_dir / "TASK.md", source_id, reason, source_metadata or {}, bootstrap=workspace.bootstrap)

    current_now = now()
    return RepairTask(
        id=workspace.task_id,
        source_id=source_id,
        status="queued",
        work_dir=workspace.work_dir,
        created_at=current_now,
        updated_at=current_now,
        log_path=workspace.log_path,
        result_path=workspace.result_path,
    )
