from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modnews.service.extraction.contract import ExtractorRunInput, ExtractorRunResult, validate_result
from modnews.service.extraction.metadata import ExtractorMetadata, read_metadata, replace_metadata_comment
from modnews.service.extraction.registry_support import load_runner, now, read_manifest, write_manifest


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
        manifest = read_manifest(manifest_path, {})
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
        record.metadata.updated_at = now()
        replace_metadata_comment(record.extractor_path, record.metadata)
        manifest = dict(record.manifest)
        manifest["status"] = record.metadata.status
        manifest["updated_at"] = record.metadata.updated_at
        write_manifest(record.manifest_path, manifest)
        return self.get(source_id)

    def delete(self, source_id: str) -> None:
        target = self.root / source_id
        if target.exists():
            shutil.rmtree(target)

    def run(self, source_id: str, payload: ExtractorRunInput) -> ExtractorRunResult:
        record = self.get(source_id)
        if record.metadata.status != "enabled":
            raise RuntimeError(f"extractor {source_id} is {record.metadata.status}")
        runner = load_runner(record.extractor_path)
        raw = runner(payload.to_dict())
        result = raw if isinstance(raw, ExtractorRunResult) else ExtractorRunResult.from_dict(raw)
        validate_result(result)
        return result


def registry_from_project(project_root: Path) -> ExtractorRegistry:
    return ExtractorRegistry(project_root / "extractors")
