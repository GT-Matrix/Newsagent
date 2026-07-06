from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.service.extraction.metadata import replace_metadata_comment
from modnews.service.extraction.registry import ExtractorRecord
from modnews.service.extraction.repair_store import read_json, write_json
from modnews.service.extraction.repair_support import infer_name_from_task, infer_url_from_task, now


def apply_promoted_metadata(
    record: ExtractorRecord,
    *,
    result: dict[str, Any],
    extractor_path: Path,
    task_md_path: Path,
) -> ExtractorRecord:
    record.metadata.version = str(result.get("version") or record.metadata.version)
    record.metadata.status = "enabled"
    record.metadata.updated_at = now()
    if not record.metadata.target_url:
        inferred_url = infer_target_url(extractor_path) or infer_url_from_task(task_md_path)
        record.metadata.target_url = inferred_url
    if record.metadata.name == record.metadata.id:
        record.metadata.name = infer_name_from_task(task_md_path) or record.metadata.name
    replace_metadata_comment(record.extractor_path, record.metadata)
    return record


def write_promoted_manifest(
    record: ExtractorRecord,
    *,
    source_manifest_path: Path,
    task_id: str,
) -> dict[str, Any]:
    manifest = read_json(source_manifest_path, {})
    manifest.update(
        {
            "id": record.metadata.id,
            "status": "enabled",
            "updated_at": record.metadata.updated_at,
            "promoted_from_task": task_id,
        }
    )
    write_json(record.manifest_path, manifest)
    return manifest


def sync_source_config_for_record(project_root: Path, record: ExtractorRecord) -> None:
    from modnews.repository.source_config import source_config_store

    source_config_store(project_root).update_site_list_item(
        record.metadata.id,
        {
            "enabled": True,
            "name": record.metadata.name or record.metadata.id,
            "url": record.metadata.target_url,
            "content_type": record.metadata.kind or "news",
            "extractor_id": record.metadata.id,
            "tags": record.metadata.tags,
        },
    )


def infer_target_url(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("DEFAULT_URL"):
            parts = line.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip().strip("\"'")
    return None
