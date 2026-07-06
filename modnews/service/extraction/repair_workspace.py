from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.service.extraction.registry import ExtractorRegistry
from modnews.service.extraction.repair_templates import write_bootstrap_extractor


@dataclass(frozen=True, slots=True)
class RepairWorkspace:
    task_id: str
    work_dir: Path
    result_path: Path
    log_path: Path
    bootstrap: bool


def prepare_repair_workspace(
    *,
    tasks_root: Path,
    registry: ExtractorRegistry,
    source_id: str,
    source_metadata: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> RepairWorkspace:
    metadata = source_metadata or {}
    existing_dir, bootstrap = _existing_extractor_dir(registry, source_id)
    resolved_task_id = task_id or build_repair_task_id(source_id)
    work_dir = tasks_root / source_id / resolved_task_id
    work_dir.mkdir(parents=True, exist_ok=True)
    if existing_dir is not None:
        shutil.copytree(existing_dir, work_dir / "current", dirs_exist_ok=True)
    else:
        write_bootstrap_extractor(work_dir / "current", source_id, metadata)
    (work_dir / "fixtures").mkdir(exist_ok=True)
    (work_dir / "schema").mkdir(exist_ok=True)
    return RepairWorkspace(
        task_id=resolved_task_id,
        work_dir=work_dir,
        result_path=work_dir / "result.json",
        log_path=work_dir / "codex.jsonl",
        bootstrap=bootstrap,
    )


def publish_repair_workspace(
    *,
    registry: ExtractorRegistry,
    source_id: str,
    current_dir: Path,
    version_tag: str | None = None,
) -> Path:
    target_dir = registry.root / source_id / "current"
    if target_dir.exists():
        version_dir = registry.root / source_id / "versions" / (version_tag or _version_tag())
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target_dir, version_dir)
        shutil.rmtree(target_dir)
    shutil.copytree(current_dir, target_dir)
    return target_dir


def build_repair_task_id(source_id: str) -> str:
    return f"{source_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def _existing_extractor_dir(registry: ExtractorRegistry, source_id: str) -> tuple[Path | None, bool]:
    try:
        record = registry.get(source_id)
        return record.current_dir, False
    except Exception:
        return None, True


def _version_tag() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")
