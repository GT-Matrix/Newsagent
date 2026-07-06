from __future__ import annotations

from modnews.repository.runtime_config_repository import RuntimeConfigRepository
from modnews.repository.runtime_config_store import RuntimeConfigStore, runtime_config_store

COMPATIBILITY_SHIM = True

__all__ = ["COMPATIBILITY_SHIM", "RuntimeConfigRepository", "RuntimeConfigStore", "runtime_config_store"]
