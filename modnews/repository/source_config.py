from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.repository.runtime_config import RuntimeConfigStore, runtime_config_store

SourceConfigStore = RuntimeConfigStore


class SourceConfigRepository:
    def __init__(self, project_root: Path) -> None:
        self.store = runtime_config_store(project_root)

    def load(self) -> dict[str, Any]:
        return self.store.load()

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.store.save(data)

    def update_step(self, step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_step(step_id, patch)

    def update_classification(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_classification(patch)

    def list(self, source_type: str | None = None) -> list[dict[str, Any]]:
        sources = self.load().get("sources", {})
        if source_type:
            return _rows(source_type, sources.get(source_type))
        rows: list[dict[str, Any]] = []
        for current_type, value in sources.items():
            rows.extend(_rows(str(current_type), value))
        return rows

    def restore_builtin_sources(self) -> dict[str, Any]:
        return self.store.restore_builtin_sources()

    def update_rss(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self.store.update_rss(items)

    def upsert_rss(self, source_id: str, row: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_rss_item(source_id, row)

    def disable_rss(self, source_id: str) -> dict[str, Any]:
        return self.store.update_rss_item(source_id, {"id": source_id, "enabled": False})

    def delete_rss(self, source_id: str) -> dict[str, Any]:
        return self.store.delete_rss_item(source_id)

    def update_newsnow(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_newsnow_item(source_id, patch)

    def disable_newsnow(self, source_id: str) -> dict[str, Any]:
        return self.store.update_newsnow_item(source_id, {"enabled": False})

    def upsert_site(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_site_list_item(source_id, patch)

    def disable_site(self, source_id: str) -> dict[str, Any]:
        return self.store.update_site_list_item(source_id, {"enabled": False})

    def enabled_rss_sources(self) -> list[dict[str, Any]]:
        return self.store.enabled_rss_sources()

    def enabled_newsnow_sources(self) -> list[dict[str, Any]]:
        return self.store.enabled_newsnow_sources()


def source_config_store(project_root: Path) -> RuntimeConfigStore:
    return runtime_config_store(project_root)


def source_config_repository(project_root: Path) -> SourceConfigRepository:
    return SourceConfigRepository(project_root)


def _rows(source_type: str, value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [{"source_type": source_type, **row} for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [
            {"source_type": source_type, "id": source_id, **row}
            for source_id, row in value.items()
            if isinstance(row, dict)
        ]
    return []
