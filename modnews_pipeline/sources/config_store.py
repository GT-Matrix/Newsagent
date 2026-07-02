from __future__ import annotations

from pathlib import Path

from modnews_pipeline.runtime_config import RuntimeConfigStore, runtime_config_store


SourceConfigStore = RuntimeConfigStore


def source_config_store(project_root: Path) -> RuntimeConfigStore:
    return runtime_config_store(project_root)
