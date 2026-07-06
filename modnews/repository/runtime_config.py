from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths
from modnews.repository.runtime_config_defaults import (
    build_initial_config,
    editable_step_keys,
    merge_builtin_newsnow,
    merge_builtin_rss,
)
from modnews.repository.runtime_config_migration import migrate_runtime_config, needs_migration
from modnews.repository.runtime_config_normalize import normalize_config
from modnews.repository.runtime_config_io import now as current_time
from modnews.repository.runtime_config_io import read_json, write_config
from modnews.repository.runtime_config_sources import (
    delete_rss_item as delete_rss_item_data,
    delete_site_list_item as delete_site_list_item_data,
    enabled_newsnow_sources as enabled_newsnow_sources_data,
    enabled_rss_sources as enabled_rss_sources_data,
    restore_builtin_sources as restore_builtin_sources_data,
    rss_row,
    update_newsnow_item as update_newsnow_item_data,
    update_rss as update_rss_data,
    update_rss_item as update_rss_item_data,
    update_site_list_item as update_site_list_item_data,
)


@dataclass(slots=True)
class RuntimeConfigStore:
    project_root: Path

    @property
    def path(self) -> Path:
        return runtime_paths(self.project_root).config_path

    @property
    def legacy_source_config_path(self) -> Path:
        return runtime_paths(self.project_root).legacy_source_config_path

    @property
    def rss_seed_path(self) -> Path:
        return self.project_root / "modnews" / "data" / "rss_sources.json"

    @property
    def newsnow_seed_path(self) -> Path:
        return self.project_root / "modnews" / "data" / "newsnow_sources.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            self.save(self._initial_config())
            return read_json(self.path)
        original = read_json(self.path)
        data = original
        if needs_migration(data):
            data = self._migrate(data)
        data = normalize_config(data, now=current_time(), rss_row=rss_row)
        if data != original:
            self.save(data)
        return data

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        data = normalize_config(data, now=current_time(), rss_row=rss_row)
        data.setdefault("meta", {})["updated_at"] = current_time()
        write_config(self.path, data)
        return data

    def update_step(self, step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        step = data["steps"].setdefault(step_id, {})
        if not isinstance(step, dict):
            step = {}
            data["steps"][step_id] = step
        for key, value in patch.items():
            if key in editable_step_keys(step_id):
                step[key] = value
        return self.save(data)

    def update_classification(self, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        target = data.setdefault("classification", {})
        for key in (
            "enabled",
            "batch_size",
            "batch_concurrency",
            "event_candidate_count",
            "merge_candidate_count",
            "time_window_hours",
            "suspect_mode",
        ):
            if key in patch:
                target[key] = patch[key]
        return self.save(data)

    def update_rss(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        data = self.load()
        data = update_rss_data(data, items)
        return self.save(data)

    def update_rss_item(self, source_id: str, row: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        data = update_rss_item_data(data, source_id, row)
        return self.save(data)

    def delete_rss_item(self, source_id: str) -> dict[str, Any]:
        data = self.load()
        data = delete_rss_item_data(data, source_id)
        return self.save(data)

    def update_newsnow_item(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        data = update_newsnow_item_data(data, source_id, patch)
        return self.save(data)

    def update_site_list_item(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        data = update_site_list_item_data(data, source_id, patch)
        return self.save(data)

    def delete_site_list_item(self, source_id: str) -> dict[str, Any]:
        data = self.load()
        data = delete_site_list_item_data(data, source_id)
        return self.save(data)

    def restore_builtin_sources(self) -> dict[str, Any]:
        data = self.load()
        data = restore_builtin_sources_data(
            data,
            rss_seed_path=self.rss_seed_path,
            newsnow_seed_path=self.newsnow_seed_path,
        )
        return self.save(data)

    def enabled_rss_sources(self) -> list[dict[str, Any]]:
        return enabled_rss_sources_data(self.load())

    def enabled_newsnow_sources(self) -> list[dict[str, Any]]:
        return enabled_newsnow_sources_data(self.load())

    def _initial_config(self) -> dict[str, Any]:
        if self.legacy_source_config_path.exists():
            legacy = read_json(self.legacy_source_config_path)
            if isinstance(legacy, dict):
                return self._migrate(legacy)
        return build_initial_config(
            now=current_time(),
            rss_rows=[rss_row(row) for row in read_json(self.rss_seed_path, default=[])],
            newsnow_data=read_json(self.newsnow_seed_path, default={}),
        )

    def _migrate(self, data: dict[str, Any]) -> dict[str, Any]:
        return migrate_runtime_config(data, now=current_time(), rss_row=rss_row)


def runtime_config_store(project_root: Path) -> RuntimeConfigStore:
    return RuntimeConfigStore(project_root)


class RuntimeConfigRepository:
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
