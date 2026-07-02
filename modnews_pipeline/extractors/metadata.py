from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

METADATA_PREFIX = "# MODNEWS_EXTRACTOR "


@dataclass(slots=True)
class ExtractorMetadata:
    id: str
    name: str
    kind: str
    version: str
    status: str = "enabled"
    entrypoint: str = "extractor.py:run"
    target_url: str | None = None
    schedule: str | None = None
    tags: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    notes: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExtractorMetadata":
        return cls(
            id=str(raw.get("id") or ""),
            name=str(raw.get("name") or ""),
            kind=str(raw.get("kind") or "generic"),
            version=str(raw.get("version") or "0.0.0"),
            status=str(raw.get("status") or "enabled"),
            entrypoint=str(raw.get("entrypoint") or "extractor.py:run"),
            target_url=_optional_str(raw.get("target_url")),
            schedule=_optional_str(raw.get("schedule")),
            tags=[str(item) for item in raw.get("tags", []) if item not in (None, "")],
            created_at=_optional_str(raw.get("created_at")),
            updated_at=_optional_str(raw.get("updated_at")),
            notes=_optional_str(raw.get("notes")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_metadata(path: Path) -> ExtractorMetadata:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines()[:40]:
        if line.startswith(METADATA_PREFIX):
            payload = line[len(METADATA_PREFIX) :].strip()
            return ExtractorMetadata.from_dict(json.loads(payload))
    raise ValueError(f"missing {METADATA_PREFIX.strip()} metadata in {path}")


def metadata_comment(metadata: ExtractorMetadata) -> str:
    payload = json.dumps(metadata.to_dict(), ensure_ascii=False, sort_keys=True)
    return f"{METADATA_PREFIX}{payload}"


def replace_metadata_comment(path: Path, metadata: ExtractorMetadata) -> None:
    text = path.read_text(encoding="utf-8")
    replacement = metadata_comment(metadata)
    if re.search(rf"^{re.escape(METADATA_PREFIX)}.*$", text, flags=re.MULTILINE):
        text = re.sub(rf"^{re.escape(METADATA_PREFIX)}.*$", replacement, text, count=1, flags=re.MULTILINE)
    else:
        text = f"{replacement}\n{text}"
    path.write_text(text, encoding="utf-8")


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
