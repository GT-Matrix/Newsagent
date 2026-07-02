from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    project_root: Path
    runtime_dir: Path
    output_dir: Path
    process_dir: Path
    cache_dir: Path
    agent_work_dir: Path

    @property
    def config_path(self) -> Path:
        return self.runtime_dir / "config.json"

    @property
    def legacy_source_config_path(self) -> Path:
        return self.runtime_dir / "source_config.json"

    @property
    def combined_news_path(self) -> Path:
        return self.output_dir / "combined_news.json"

    @property
    def news_with_events_path(self) -> Path:
        return self.output_dir / "news_with_events.json"

    @property
    def events_path(self) -> Path:
        return self.output_dir / "events.json"

    @property
    def discarded_news_path(self) -> Path:
        return self.output_dir / "discarded_news.json"

    @property
    def papers_path(self) -> Path:
        return self.output_dir / "papers.json"

    @property
    def paper_attach_decisions_path(self) -> Path:
        return self.process_dir / "paper_attach_decisions.json"

    @property
    def classification_checkpoint_path(self) -> Path:
        return self.process_dir / "classification_progress.json"

    @property
    def llm_cache_path(self) -> Path:
        return self.cache_dir / "llm_classification_cache.sqlite3"

    @property
    def embedding_cache_path(self) -> Path:
        return self.cache_dir / "event_vector_cache.sqlite3"

    @property
    def newsnow_cache_dir(self) -> Path:
        return self.cache_dir / "newsnow"


def runtime_paths(project_root: Path) -> RuntimePaths:
    root = project_root.resolve()
    runtime_dir = _path_env("MODNEWS_RUNTIME_DIR", root / "runtime", root)
    output_dir = _path_env("MODNEWS_OUTPUT_DIR", root / "output", root)
    process_dir = _path_env("MODNEWS_PROCESS_DIR", root / "var" / "process", root)
    cache_dir = _path_env("MODNEWS_CACHE_DIR", root / "var" / "cache", root)
    agent_work_dir = _path_env("MODNEWS_AGENT_WORK_DIR", root / ".agent_work", root)
    return RuntimePaths(
        project_root=root,
        runtime_dir=runtime_dir,
        output_dir=output_dir,
        process_dir=process_dir,
        cache_dir=cache_dir,
        agent_work_dir=agent_work_dir,
    )


def _path_env(name: str, default: Path, project_root: Path) -> Path:
    value = os.environ.get(name)
    if not value:
        return default.resolve()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()
