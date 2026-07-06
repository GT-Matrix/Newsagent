from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths
from modnews.repository.source_config import source_config_repository


@dataclass(slots=True)
class RuntimeConfigFacade:
    project_root: Path

    def show(self, *, include_paths: bool = False) -> dict[str, Any]:
        payload = source_config_repository(self.project_root).load()
        if include_paths:
            paths = runtime_paths(self.project_root)
            payload["paths"] = {
                "runtime_dir": str(paths.runtime_dir),
                "config_path": str(paths.config_path),
                "output_dir": str(paths.output_dir),
                "process_dir": str(paths.process_dir),
                "cache_dir": str(paths.cache_dir),
                "agent_work_dir": str(paths.agent_work_dir),
            }
        return payload

    def update_step(self, step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_repository(self.project_root).update_step(step_id, patch)

    def update_classification(self, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_repository(self.project_root).update_classification(patch)

    def restore_builtins(self) -> dict[str, Any]:
        return source_config_repository(self.project_root).restore_builtin_sources()
