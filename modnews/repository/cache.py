from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.core.config import load_config


class CacheRepository:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def state(self) -> dict[str, Any]:
        config = load_config()
        return {
            "llm": self._path_info(config.classification.llm.cache_path),
            "embedding": self._path_info(config.classification.embedding.cache_path),
        }

    def clear(self, *, llm: bool = False, embedding: bool = False) -> list[str]:
        config = load_config()
        targets = []
        if llm:
            targets.append(config.classification.llm.cache_path)
        if embedding:
            targets.append(config.classification.embedding.cache_path)
        removed = []
        for path in targets:
            if path and path.exists():
                path.unlink()
                removed.append(str(path))
        return removed

    def _path_info(self, path: Path | None) -> dict[str, Any]:
        return {"path": str(path) if path else None, "exists": bool(path and path.exists())}
