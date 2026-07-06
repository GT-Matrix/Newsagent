from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from modnews.service.extraction.metadata import replace_metadata_comment
from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_store import RepairTask, read_json, write_json
from modnews.service.extraction.repair_support import infer_name_from_task, infer_url_from_task, now


def promote_repair_task(project_root: Path, registry: ExtractorRegistry, task: RepairTask) -> RepairTask:
    result = read_json(task.result_path, {})
    if task.status != "succeeded" or result.get("status") not in {"fixed", "needs_review"}:
        raise RuntimeError("only succeeded fixed/needs_review tasks can be promoted")

    current_dir = task.work_dir / "current"
    extractor_path = current_dir / "extractor.py"
    manifest_path = current_dir / "manifest.json"
    if not extractor_path.exists():
        raise RuntimeError("task has no current/extractor.py")

    target_dir = registry.root / task.source_id / "current"
    if target_dir.exists():
        version_dir = registry.root / task.source_id / "versions" / datetime.now().strftime("%Y%m%d%H%M%S")
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target_dir, version_dir)
        shutil.rmtree(target_dir)
    shutil.copytree(current_dir, target_dir)

    try:
        record = registry.get(task.source_id)
        record.metadata.version = result.get("version") or record.metadata.version
        record.metadata.status = "enabled"
        record.metadata.updated_at = now()
        if not record.metadata.target_url:
            inferred_url = infer_target_url(extractor_path) or infer_url_from_task(task.work_dir / "TASK.md")
            record.metadata.target_url = inferred_url
        if record.metadata.name == task.source_id:
            record.metadata.name = infer_name_from_task(task.work_dir / "TASK.md") or record.metadata.name
        replace_metadata_comment(record.extractor_path, record.metadata)
        manifest = read_json(manifest_path, {})
        manifest.update(
            {
                "id": task.source_id,
                "status": "enabled",
                "updated_at": record.metadata.updated_at,
                "promoted_from_task": task.id,
            }
        )
        write_json(record.manifest_path, manifest)

        from modnews.repository.source_config import source_config_store

        source_config_store(project_root).update_site_list_item(
            task.source_id,
            {
                "enabled": True,
                "name": record.metadata.name or task.source_id,
                "url": record.metadata.target_url,
                "content_type": record.metadata.kind or "news",
                "extractor_id": task.source_id,
                "tags": record.metadata.tags,
            },
        )
    except Exception:
        pass

    task.updated_at = now()
    return task


def infer_target_url(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("DEFAULT_URL"):
            parts = line.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip().strip("\"'")
    return None
