from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from modnews_pipeline.config import load_config
from modnews_pipeline.paths import runtime_paths


class OutputRepository:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def state(self, config: Any | None = None) -> dict[str, Any]:
        config = config or load_config()
        paths = {
            "combined_news": runtime_paths(self.project_root).combined_news_path,
            "news_with_events": config.classification.output_path,
            "events": config.classification.events_output_path,
            "discarded_news": config.classification.discarded_output_path,
            "checkpoint": config.classification.checkpoint_path,
            "llm_cache": config.classification.llm.cache_path,
            "embedding_cache": config.classification.embedding.cache_path,
        }
        return {key: self._path_info(path) for key, path in paths.items()}

    def publish_from_checkpoint(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        config = load_config()
        paths = runtime_paths(self.project_root)
        targets = {
            "combined_news": paths.combined_news_path,
            "news_with_events": config.classification.output_path,
            "events": config.classification.events_output_path,
            "discarded_news": config.classification.discarded_output_path,
        }
        output_refs = checkpoint.get("output_refs") if isinstance(checkpoint.get("output_refs"), dict) else {}
        published = []
        skipped = []
        for key, target in targets.items():
            source_value = output_refs.get(key)
            if not source_value:
                skipped.append({"key": key, "reason": "missing_ref"})
                continue
            source = Path(str(source_value)).expanduser().resolve()
            if not source.exists():
                skipped.append({"key": key, "source": str(source), "reason": "source_missing"})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if source != target.resolve():
                shutil.copyfile(source, target)
            published.append({"key": key, "source": str(source), "target": str(target)})
        return {"published": published, "skipped": skipped, "outputs": self.state(config)}

    def _path_info(self, path: Path | None) -> dict[str, Any]:
        if not path:
            return {"path": None, "exists": False}
        info: dict[str, Any] = {"path": str(path), "exists": path.exists()}
        if path.exists():
            info["size_bytes"] = path.stat().st_size
            if path.suffix == ".json":
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    info["count"] = len(data) if isinstance(data, list) else len(data.get("items", []))
                    if isinstance(data, dict) and data.get("meta"):
                        info["meta"] = data["meta"]
                except Exception as exc:
                    info["error"] = str(exc)
        return info
