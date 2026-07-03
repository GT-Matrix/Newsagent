from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modnews.core.paths import runtime_paths
from modnews.repository.runtime_config import runtime_config_store

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class StepConfig:
    type: str
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LlmConfig:
    model: str
    base_url: str | None = None
    api_key: str | None = None
    cache_path: Path | None = None
    temperature: float = 0.0
    timeout_seconds: int = 90
    max_retries: int = 5
    simulate_cache_stream: bool = False
    cache_first_token_delay_seconds: float = 1.0
    cache_tokens_per_second: float = 120.0


@dataclass(slots=True)
class EmbeddingConfig:
    model: str
    base_url: str | None = None
    api_key: str | None = None
    cache_path: Path | None = None
    timeout_seconds: int = 60
    simulate_cache_stream: bool = False
    cache_first_token_delay_seconds: float = 1.0
    cache_tokens_per_second: float = 120.0


@dataclass(slots=True)
class ClassificationConfig:
    enabled: bool = True
    output_path: Path = field(default_factory=lambda: Path("output/news_with_events.json"))
    events_output_path: Path = field(default_factory=lambda: Path("output/events.json"))
    discarded_output_path: Path = field(default_factory=lambda: Path("output/discarded_news.json"))
    batch_size: int = 40
    batch_concurrency: int = 20
    event_candidate_count: int = 5
    merge_candidate_count: int = 5
    time_window_hours: int = 72
    suspect_mode: str = "discard"
    checkpoint_path: Path | None = None
    llm: LlmConfig = field(default_factory=lambda: LlmConfig(model="qwen-plus"))
    embedding: EmbeddingConfig = field(default_factory=lambda: EmbeddingConfig(model="text-embedding-v4"))


@dataclass(slots=True)
class PipelineConfig:
    project_root: Path
    output_path: Path
    proxy_url: str | None
    newsnow_api_url: str
    rss_api_url: str | None
    site_lists_api_url: str | None
    newsnow_sources_path: Path
    newsnow_cache_dir: Path | None
    rss_sources_path: Path
    ingest_steps: list[StepConfig]
    classification: ClassificationConfig


def apply_runtime_overrides(
    config: PipelineConfig,
    *,
    only_ingest_steps: list[str] | None = None,
    disable_classification: bool = False,
) -> PipelineConfig:
    if only_ingest_steps:
        allowed = set(only_ingest_steps)
        config.ingest_steps = [
            StepConfig(type=step.type, enabled=step.enabled and step.type in allowed, options=dict(step.options))
            for step in config.ingest_steps
        ]
    if disable_classification:
        config.classification.enabled = False
    return config


def build_config(raw: dict[str, Any] | None = None, base_dir: str | Path | None = None) -> PipelineConfig:
    override_raw = raw or {}
    project_root = Path(base_dir).resolve() if base_dir else _project_root()
    paths = runtime_paths(project_root)
    data_root = project_root / "modnews" / "data"
    runtime_raw = runtime_config_store(project_root).load()
    merged = _merge_runtime_override(runtime_raw, override_raw)
    steps_raw = merged.get("steps", {})
    steps = []
    for step_id in ("rss", "newsnow", "site_lists"):
        step_raw = steps_raw.get(step_id, {}) if isinstance(steps_raw, dict) else {}
        if not isinstance(step_raw, dict):
            step_raw = {}
        steps.append(
            StepConfig(
                type=step_id,
                enabled=step_raw.get("enabled", True),
                options={key: value for key, value in step_raw.items() if key != "enabled"},
            )
        )
    ingest_steps_raw = override_raw.get("ingest_steps")
    if isinstance(ingest_steps_raw, list):
        steps = [
            StepConfig(
                type=step["type"],
                enabled=step.get("enabled", True),
                options={k: v for k, v in step.items() if k not in {"type", "enabled"}},
            )
            for step in ingest_steps_raw
            if isinstance(step, dict) and step.get("type")
        ]
    classification_raw = merged.get("classification", {})
    return PipelineConfig(
        project_root=project_root,
        output_path=paths.combined_news_path,
        proxy_url=os.environ.get("SOURCE_LAB_PROXY", "http://127.0.0.1:7897"),
        newsnow_api_url=override_raw.get(
            "newsnow_api_url",
            os.environ.get("NEWSNOW_API_URL", "https://newsnow.busiyi.world/api/s"),
        ),
        rss_api_url=override_raw.get("rss_api_url", os.environ.get("MODNEWS_RSS_API_URL")),
        site_lists_api_url=override_raw.get("site_lists_api_url", os.environ.get("MODNEWS_SITE_LISTS_API_URL")),
        newsnow_sources_path=Path(
            override_raw.get(
                "newsnow_sources_path",
                data_root / "newsnow_sources.json",
            )
        ).resolve(),
        newsnow_cache_dir=paths.newsnow_cache_dir,
        rss_sources_path=Path(
            override_raw.get("rss_sources_path", data_root / "rss_sources.json")
        ).resolve(),
        ingest_steps=steps,
        classification=ClassificationConfig(
            enabled=classification_raw.get("enabled", True),
            output_path=paths.news_with_events_path,
            events_output_path=paths.events_path,
            discarded_output_path=paths.discarded_news_path,
            batch_size=classification_raw.get("batch_size", 40),
            batch_concurrency=classification_raw.get(
                "batch_concurrency",
                int(os.environ.get("CLASSIFICATION_BATCH_CONCURRENCY", "20")),
            ),
            event_candidate_count=classification_raw.get("event_candidate_count", 5),
            merge_candidate_count=classification_raw.get("merge_candidate_count", 5),
            time_window_hours=classification_raw.get("time_window_hours", 72),
            suspect_mode=classification_raw.get(
                "suspect_mode",
                os.environ.get("CLASSIFICATION_SUSPECT_MODE", "discard"),
            ),
            llm=LlmConfig(
                model=os.environ.get("LLM_MODEL", "qwen-plus"),
                base_url=os.environ.get("LLM_BASE_URL"),
                api_key=os.environ.get("LLM_API_KEY"),
                cache_path=paths.llm_cache_path,
                temperature=float(os.environ.get("LLM_TEMPERATURE", "0.0")),
                timeout_seconds=int(os.environ.get("LLM_TIMEOUT_SECONDS", "90")),
                max_retries=int(os.environ.get("LLM_MAX_RETRIES", "5")),
                simulate_cache_stream=_env_bool("CACHE_SIMULATION_ENABLED", False),
                cache_first_token_delay_seconds=float(os.environ.get("CACHE_SIMULATION_FIRST_TOKEN_DELAY_SECONDS", "1.0")),
                cache_tokens_per_second=float(os.environ.get("CACHE_SIMULATION_TOKENS_PER_SECOND", "120")),
            ),
            embedding=EmbeddingConfig(
                model=os.environ.get("EMBEDDING_MODEL", "text-embedding-v4"),
                base_url=os.environ.get("EMBEDDING_BASE_URL"),
                api_key=os.environ.get("EMBEDDING_API_KEY"),
                cache_path=paths.embedding_cache_path,
                timeout_seconds=int(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "60")),
                simulate_cache_stream=_env_bool("CACHE_SIMULATION_ENABLED", False),
                cache_first_token_delay_seconds=float(os.environ.get("CACHE_SIMULATION_FIRST_TOKEN_DELAY_SECONDS", "1.0")),
                cache_tokens_per_second=float(os.environ.get("CACHE_SIMULATION_TOKENS_PER_SECOND", "120")),
            ),
            checkpoint_path=paths.classification_checkpoint_path,
        ),
    )


def load_config(config_path: str | None = None) -> PipelineConfig:
    if not config_path:
        return build_config()
    config_file = Path(config_path).resolve()
    raw = json.loads(config_file.read_text(encoding="utf-8"))
    return build_config(raw, base_dir=config_file.parent)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _merge_runtime_override(runtime_raw: dict[str, Any], override_raw: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(runtime_raw, ensure_ascii=False))
    for key in ("steps", "classification"):
        if isinstance(override_raw.get(key), dict):
            _deep_update(merged.setdefault(key, {}), override_raw[key])
    return merged


def _deep_update(target: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if key in {
            "output_path",
            "events_output_path",
            "discarded_output_path",
            "checkpoint_path",
            "cache_path",
            "decisions_output_path",
        }:
            continue
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
