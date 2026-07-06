from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.repository.runtime_config_repository import RuntimeConfigRepository
from modnews.repository.runtime_config_store import RuntimeConfigStore
from modnews.repository.runtime_config_sources import (
    delete_rss_item as delete_rss_item_data,
    delete_site_list_item as delete_site_list_item_data,
    enabled_newsnow_sources as enabled_newsnow_sources_data,
    enabled_rss_sources as enabled_rss_sources_data,
    restore_builtin_sources as restore_builtin_sources_data,
    update_newsnow_item as update_newsnow_item_data,
    update_rss as update_rss_data,
    update_rss_item as update_rss_item_data,
    update_site_list_item as update_site_list_item_data,
)


class SourceConfigStore(RuntimeConfigStore):
    def restore_builtin_sources(self) -> dict[str, Any]:
        return self._mutate(
            lambda data: restore_builtin_sources_data(
                data,
                rss_seed_path=self.rss_seed_path,
                newsnow_seed_path=self.newsnow_seed_path,
            )
        )

    def update_rss(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return self._mutate(lambda data: update_rss_data(data, items))

    def update_rss_item(self, source_id: str, row: dict[str, Any]) -> dict[str, Any]:
        return self._mutate(lambda data: update_rss_item_data(data, source_id, row))

    def delete_rss_item(self, source_id: str) -> dict[str, Any]:
        return self._mutate(lambda data: delete_rss_item_data(data, source_id))

    def update_newsnow_item(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self._mutate(lambda data: update_newsnow_item_data(data, source_id, patch))

    def update_site_list_item(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self._mutate(lambda data: update_site_list_item_data(data, source_id, patch))

    def delete_site_list_item(self, source_id: str) -> dict[str, Any]:
        return self._mutate(lambda data: delete_site_list_item_data(data, source_id))

    def enabled_rss_sources(self) -> list[dict[str, Any]]:
        return self._query(enabled_rss_sources_data)

    def enabled_newsnow_sources(self) -> list[dict[str, Any]]:
        return self._query(enabled_newsnow_sources_data)


class SourceConfigRepository(RuntimeConfigRepository):
    def __init__(self, project_root: Path) -> None:
        super().__init__(project_root)
        self.store = source_config_store(project_root)

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

    def delete_site(self, source_id: str) -> dict[str, Any]:
        return self.store.delete_site_list_item(source_id)

    def enabled_rss_sources(self) -> list[dict[str, Any]]:
        return self.store.enabled_rss_sources()

    def enabled_newsnow_sources(self) -> list[dict[str, Any]]:
        return self.store.enabled_newsnow_sources()


def source_config_store(project_root: Path) -> SourceConfigStore:
    return SourceConfigStore(project_root)


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
