from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from modnews.core.paths import runtime_paths
from modnews.repository.runtime_config_io import now as current_time
from modnews.repository.runtime_config_io import read_json, write_config
from modnews.repository.runtime_config_lifecycle import load_runtime_config, save_runtime_config
from modnews.repository.runtime_config_mutations import apply_classification_patch, apply_step_patch
from modnews.repository.runtime_config_sources import rss_row

T = TypeVar("T")


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
        return load_runtime_config(
            path=self.path,
            legacy_source_config_path=self.legacy_source_config_path,
            rss_seed_path=self.rss_seed_path,
            newsnow_seed_path=self.newsnow_seed_path,
            current_time=current_time,
            read_json=read_json,
            write_config=write_config,
            rss_row=rss_row,
        )

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        return save_runtime_config(
            path=self.path,
            data=data,
            current_time=current_time,
            write_config=write_config,
            rss_row=rss_row,
        )

    def update_step(self, step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self._mutate(lambda data: apply_step_patch(data, step_id, patch))

    def update_classification(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self._mutate(lambda data: apply_classification_patch(data, patch))

    def _mutate(self, mutate: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        data = self.load()
        data = mutate(data)
        return self.save(data)

    def _query(self, query: Callable[[dict[str, Any]], T]) -> T:
        return query(self.load())


def runtime_config_store(project_root: Path) -> RuntimeConfigStore:
    return RuntimeConfigStore(project_root)
