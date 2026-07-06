from __future__ import annotations

from pathlib import Path

from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_promote_ops import (
    apply_promoted_metadata,
    sync_source_config_for_record,
    write_promoted_manifest,
)
from modnews.service.extraction.repair_state_ops import mark_repair_task_promoted
from modnews.service.extraction.repair_store import RepairTask, read_json
from modnews.service.extraction.repair_workspace import publish_repair_workspace


def promote_repair_task(project_root: Path, registry: ExtractorRegistry, task: RepairTask) -> RepairTask:
    result = read_json(task.result_path, {})
    if task.status != "succeeded" or result.get("status") not in {"fixed", "needs_review"}:
        raise RuntimeError("only succeeded fixed/needs_review tasks can be promoted")

    current_dir = task.work_dir / "current"
    extractor_path = current_dir / "extractor.py"
    manifest_path = current_dir / "manifest.json"
    if not extractor_path.exists():
        raise RuntimeError("task has no current/extractor.py")

    publish_repair_workspace(
        registry=registry,
        source_id=task.source_id,
        current_dir=current_dir,
    )

    try:
        record = registry.get(task.source_id)
        record = apply_promoted_metadata(
            record,
            result=result,
            extractor_path=extractor_path,
            task_md_path=task.work_dir / "TASK.md",
        )
        write_promoted_manifest(record, source_manifest_path=manifest_path, task_id=task.id)
        sync_source_config_for_record(project_root, record)
    except Exception:
        pass

    return mark_repair_task_promoted(task)
