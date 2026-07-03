from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ExtractorRunInput:
    source_id: str
    url: str
    scrape_date: str
    limit: int = 40
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExtractedPaper:
    platform: str
    title: str
    url: str
    pubtime: str | None
    scrape_date: str
    summary: str | None = None
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    primary_category: str | None = None
    paper_id: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExtractedPaper":
        return cls(
            platform=str(raw.get("platform") or ""),
            title=str(raw.get("title") or ""),
            url=str(raw.get("url") or ""),
            pubtime=_optional_str(raw.get("pubtime")),
            scrape_date=str(raw.get("scrape_date") or ""),
            summary=_optional_str(raw.get("summary")),
            authors=_str_list(raw.get("authors")),
            categories=_str_list(raw.get("categories")),
            primary_category=_optional_str(raw.get("primary_category")),
            paper_id=_optional_str(raw.get("paper_id")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExtractorRunResult:
    ok: bool
    items: list[ExtractedPaper] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    extractor_version: str = "unknown"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ExtractorRunResult":
        return cls(
            ok=bool(raw.get("ok")),
            items=[
                ExtractedPaper.from_dict(item)
                for item in raw.get("items", [])
                if isinstance(item, dict)
            ],
            diagnostics=raw.get("diagnostics") if isinstance(raw.get("diagnostics"), dict) else {},
            extractor_version=str(raw.get("extractor_version") or "unknown"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "items": [item.to_dict() for item in self.items],
            "diagnostics": dict(self.diagnostics),
            "extractor_version": self.extractor_version,
        }


def validate_result(result: ExtractorRunResult) -> None:
    if result.ok and not result.items:
        raise ValueError("extractor reported ok but returned no items")
    for index, item in enumerate(result.items):
        missing = [name for name in ("platform", "title", "url", "scrape_date") if not getattr(item, name)]
        if missing:
            raise ValueError(f"item {index} missing required fields: {', '.join(missing)}")

def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "")]
