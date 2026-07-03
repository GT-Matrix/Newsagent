from __future__ import annotations

from pathlib import Path

from modnews.repository.runtime_config import RuntimeConfigRepository, RuntimeConfigStore, runtime_config_store

SourceConfigRepository = RuntimeConfigRepository
SourceConfigStore = RuntimeConfigStore


def source_config_store(project_root: Path) -> RuntimeConfigStore:
    return runtime_config_store(project_root)
