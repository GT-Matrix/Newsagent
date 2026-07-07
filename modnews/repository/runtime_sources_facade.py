from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modnews.repository.source_config import source_config_repository


@dataclass(slots=True)
class RuntimeSourcesFacade:
    project_root: Path

    def list(self, source_type: str | None = None) -> list[dict[str, Any]]:
        return source_config_repository(self.project_root).list(source_type)

    def update_rss(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return source_config_repository(self.project_root).update_rss(items)

    def upsert_rss(self, source_id: str, row: dict[str, Any]) -> dict[str, Any]:
        return source_config_repository(self.project_root).upsert_rss(source_id, row)

    def disable_rss(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).disable_rss(source_id)

    def delete_rss(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).delete_rss(source_id)

    def update_newsnow(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_repository(self.project_root).update_newsnow(source_id, patch)

    def upsert_site(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_repository(self.project_root).upsert_site(source_id, patch)

    def disable_site(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).disable_site(source_id)

    def delete_site(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).delete_site(source_id)
