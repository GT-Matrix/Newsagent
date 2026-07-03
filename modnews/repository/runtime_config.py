from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews_pipeline.runtime_config import RuntimeConfigStore, runtime_config_store


class RuntimeConfigRepository:
    def __init__(self, project_root: Path) -> None:
        self.store: RuntimeConfigStore = runtime_config_store(project_root)

    def load(self) -> dict[str, Any]:
        return self.store.load()

    def save(self, data: dict[str, Any]) -> dict[str, Any]:
        return self.store.save(data)

    def update_step(self, step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_step(step_id, patch)

    def update_classification(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_classification(patch)
