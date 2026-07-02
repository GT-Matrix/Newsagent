from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


TERMINAL_STATES = {"succeeded", "failed", "repaired", "skipped_unrepairable"}


@dataclass(slots=True)
class WebSource:
    id: str
    name: str
    url: str
    enabled: bool = True
    content_type: str = "news"
    extractor_id: str | None = None
    tags: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    repair_policy: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_config(cls, source_id: str, raw: dict[str, Any]) -> "WebSource":
        extractor_id = raw.get("extractor_id")
        return cls(
            id=source_id,
            name=str(raw.get("name") or source_id),
            url=str(raw.get("url") or ""),
            enabled=bool(raw.get("enabled", True)),
            content_type=str(raw.get("content_type") or "news"),
            extractor_id=str(extractor_id) if extractor_id else None,
            tags=[str(item) for item in raw.get("tags", []) if item not in (None, "")],
            options=raw.get("options") if isinstance(raw.get("options"), dict) else {},
            repair_policy=raw.get("repair_policy") if isinstance(raw.get("repair_policy"), dict) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WebJob:
    id: str
    source_id: str
    source_name: str
    extractor_id: str | None
    content_type: str
    url: str
    state: str
    created_at: str
    updated_at: str
    attempts: int = 0
    max_attempts: int = 3
    item_count: int = 0
    error_type: str | None = None
    error: str | None = None
    repair_task_id: str | None = None
    output_path: str | None = None
    raw_result_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExtractorFailure:
    error_type: str
    message: str
    retryable: bool = False
    unrepairable: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
