from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from modnews.core.config import build_config
from modnews.core.paths import runtime_paths


class OutputRepository:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def state(self, config: Any | None = None) -> dict[str, Any]:
        config = config or build_config(base_dir=self.project_root)
        return {key: self._path_info(path) for key, path in self.paths(config).items()}

    def paths(self, config: Any | None = None) -> dict[str, Path | None]:
        config = config or build_config(base_dir=self.project_root)
        report_dir = self.project_root / "data" / "output"
        paths = runtime_paths(self.project_root)
        return {
            "combined_news": paths.combined_news_path,
            "news_with_events": config.classification.output_path,
            "events": config.classification.events_output_path,
            "discarded_news": config.classification.discarded_output_path,
            "checkpoint": config.classification.checkpoint_path,
            "llm_cache": config.classification.llm.cache_path,
            "embedding_cache": config.classification.embedding.cache_path,
            "report_markdown": report_dir / "daily_report.md",
            "report_debug_markdown": report_dir / "daily_report_debug.md",
            "report_events": report_dir / "enriched_events.json",
            "report_evidence_events": report_dir / "evidence_events.json",
            "report_candidates": report_dir / "report_candidates.json",
            "report_review_candidates": report_dir / "review_candidates.json",
            "report_trend_summary": report_dir / "trend_summary.json",
        }

    def read_artifact(self, key: str) -> dict[str, Any]:
        paths = self.paths()
        if key not in paths:
            raise KeyError(key)
        path = paths[key]
        if path is None or not path.exists():
            raise FileNotFoundError(key)
        if path.suffix not in {".md", ".json", ".txt"}:
            raise ValueError(f"artifact is not previewable: {key}")
        return {
            "key": key,
            "path": str(path),
            "content_type": "application/json" if path.suffix == ".json" else "text/markdown" if path.suffix == ".md" else "text/plain",
            "content": path.read_text(encoding="utf-8"),
        }

    def publish_from_checkpoint(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        config = build_config(base_dir=self.project_root)
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
