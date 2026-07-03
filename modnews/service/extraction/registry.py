from __future__ import annotations

import importlib.util
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from modnews.service.extraction.contract import ExtractorRunInput, ExtractorRunResult, validate_result
from modnews.service.extraction.metadata import ExtractorMetadata, read_metadata, replace_metadata_comment


@dataclass(slots=True)
class ExtractorRecord:
    metadata: ExtractorMetadata
    root: Path
    current_dir: Path
    extractor_path: Path
    manifest_path: Path
    manifest: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "root": str(self.root),
            "current_dir": str(self.current_dir),
            "extractor_path": str(self.extractor_path),
            "manifest_path": str(self.manifest_path),
            "manifest": self.manifest,
        }


class ExtractorRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root

    def list(self) -> list[ExtractorRecord]:
        if not self.root.exists():
            return []
        records: list[ExtractorRecord] = []
        for source_dir in sorted(path for path in self.root.iterdir() if path.is_dir()):
            try:
                records.append(self.get(source_dir.name))
            except Exception:
                continue
        return records

    def get(self, source_id: str) -> ExtractorRecord:
        source_root = self.root / source_id
        current_dir = source_root / "current"
        extractor_path = current_dir / "extractor.py"
        manifest_path = current_dir / "manifest.json"
        metadata = read_metadata(extractor_path)
        manifest = _read_json(manifest_path, {})
        return ExtractorRecord(
            metadata=metadata,
            root=source_root,
            current_dir=current_dir,
            extractor_path=extractor_path,
            manifest_path=manifest_path,
            manifest=manifest,
        )

    def set_enabled(self, source_id: str, enabled: bool) -> ExtractorRecord:
        record = self.get(source_id)
        record.metadata.status = "enabled" if enabled else "disabled"
        record.metadata.updated_at = _now()
        replace_metadata_comment(record.extractor_path, record.metadata)
        manifest = dict(record.manifest)
        manifest["status"] = record.metadata.status
        manifest["updated_at"] = record.metadata.updated_at
        _write_json(record.manifest_path, manifest)
        return self.get(source_id)

    def delete(self, source_id: str) -> None:
        target = self.root / source_id
        if target.exists():
            shutil.rmtree(target)

    def run(self, source_id: str, payload: ExtractorRunInput) -> ExtractorRunResult:
        record = self.get(source_id)
        if record.metadata.status != "enabled":
            raise RuntimeError(f"extractor {source_id} is {record.metadata.status}")
        runner = _load_runner(record.extractor_path)
        raw = runner(payload.to_dict())
        result = raw if isinstance(raw, ExtractorRunResult) else ExtractorRunResult.from_dict(raw)
        validate_result(result)
        return result


def registry_from_project(project_root: Path) -> ExtractorRegistry:
    return ExtractorRegistry(project_root / "extractors")


def _load_runner(path: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    spec = importlib.util.spec_from_file_location(f"modnews_managed_extractor_{path.parent.parent.name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load extractor module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runner = getattr(module, "run", None)
    if not callable(runner):
        raise RuntimeError(f"extractor {path} does not expose run(payload)")
    return runner


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
