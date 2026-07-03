from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .history import HistoryDedupeConfig


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


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
    max_retries: int = 5
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
    embedding_concurrency: int = 8
    event_candidate_count: int = 5
    merge_candidate_count: int = 5
    time_window_hours: int = 72
    suspect_mode: str = "discard"
    checkpoint_path: Path | None = None
    llm: LlmConfig = field(default_factory=lambda: LlmConfig(model="qwen-plus"))
    embedding: EmbeddingConfig = field(default_factory=lambda: EmbeddingConfig(model="text-embedding-v4"))


@dataclass(slots=True)
class PaperAttachConfig:
    enabled: bool = True
    output_path: Path = field(default_factory=lambda: Path("output/arxiv_papers.json"))
    decisions_output_path: Path = field(default_factory=lambda: Path("output/paper_attach_decisions.json"))
    source: str = "huggingface_papers_trending"
    sources: list[str] = field(default_factory=lambda: ["huggingface_papers_trending"])
    limit: int = 40
    huggingface_limit: int = 30
    huggingface_url: str = "https://huggingface.co/papers/trending"
    query: str = (
        "cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.CV OR cat:stat.ML "
        'OR all:"large language model" OR all:"LLM" OR all:"agent"'
    )
    sort_by: str = "submittedDate"
    sort_order: str = "descending"
    max_summary_chars: int = 700


@dataclass(slots=True)
class PipelineConfig:
    output_path: Path
    proxy_url: str | None
    newsnow_api_url: str
    rss_api_url: str | None
    site_lists_api_url: str | None
    linux_do_api_url: str | None
    newsnow_sources_path: Path
    newsnow_cache_dir: Path | None
    rss_sources_path: Path
    ingest_steps: list[StepConfig]
    classification: ClassificationConfig
    paper_attach: PaperAttachConfig
    history_dedupe: HistoryDedupeConfig


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
        config.paper_attach.enabled = False
    return config


def build_config(raw: dict[str, Any] | None = None, base_dir: str | Path | None = None) -> PipelineConfig:
    raw = raw or {}
    project_root = Path(base_dir).resolve() if base_dir else _project_root()
    package_root = project_root / "modnews_pipeline"
    ingest_steps_raw = raw.get("ingest_steps", raw.get("steps"))
    steps = [
        StepConfig(
            type=step["type"],
            enabled=step.get("enabled", True),
            options={k: v for k, v in step.items() if k not in {"type", "enabled"}},
        )
        for step in (
            ingest_steps_raw
            or [
                {"type": "rss", "enabled": True},
                {"type": "newsnow", "enabled": True, "columns": ["tech", "finance"]},
                {"type": "linux_do", "enabled": True, "limit": 30, "skip_pinned": True},
                {
                    "type": "site_lists",
                    "enabled": True,
                    "sites": ["anthropic", "aibase", "36kr_ai", "zhidx", "stanford_hai"],
                    "limit_per_site": 10,
                },
            ]
        )
    ]
    classification_raw = raw.get("classification", {})
    paper_attach_raw = raw.get("paper_attach", {})
    history_raw = raw.get("history_dedupe", {})
    llm_raw = classification_raw.get("llm", {})
    embedding_raw = classification_raw.get("embedding", {})

    return PipelineConfig(
        output_path=(project_root / raw.get("output_path", "output/combined_news.json")).resolve(),
        proxy_url=raw.get("proxy_url", os.environ.get("SOURCE_LAB_PROXY", "http://127.0.0.1:7897")),
        newsnow_api_url=raw.get(
            "newsnow_api_url",
            os.environ.get("NEWSNOW_API_URL", "https://newsnow.busiyi.world/api/s"),
        ),
        rss_api_url=raw.get("rss_api_url", os.environ.get("MODNEWS_RSS_API_URL")),
        site_lists_api_url=raw.get("site_lists_api_url", os.environ.get("MODNEWS_SITE_LISTS_API_URL")),
        linux_do_api_url=raw.get("linux_do_api_url", os.environ.get("MODNEWS_LINUX_DO_API_URL")),
        newsnow_sources_path=Path(
            raw.get(
                "newsnow_sources_path",
                package_root / "data" / "newsnow_sources.json",
            )
        ).resolve(),
        newsnow_cache_dir=Path(
            raw.get("newsnow_cache_dir", project_root / "mock_data" / "newsnow")
        ).resolve(),
        rss_sources_path=Path(
            raw.get("rss_sources_path", package_root / "data" / "rss_sources.json")
        ).resolve(),
        ingest_steps=steps,
        classification=ClassificationConfig(
            enabled=classification_raw.get("enabled", True),
            output_path=(project_root / classification_raw.get("output_path", "output/news_with_events.json")).resolve(),
            events_output_path=(
                project_root / classification_raw.get("events_output_path", "output/events.json")
            ).resolve(),
            discarded_output_path=(
                project_root / classification_raw.get("discarded_output_path", "output/discarded_news.json")
            ).resolve(),
            batch_size=classification_raw.get("batch_size", 40),
            batch_concurrency=classification_raw.get(
                "batch_concurrency",
                int(os.environ.get("CLASSIFICATION_BATCH_CONCURRENCY", "20")),
            ),
            embedding_concurrency=classification_raw.get(
                "embedding_concurrency",
                int(os.environ.get("EMBEDDING_CONCURRENCY", "8")),
            ),
            event_candidate_count=classification_raw.get("event_candidate_count", 5),
            merge_candidate_count=classification_raw.get("merge_candidate_count", 5),
            time_window_hours=classification_raw.get("time_window_hours", 72),
            suspect_mode=classification_raw.get(
                "suspect_mode",
                os.environ.get("CLASSIFICATION_SUSPECT_MODE", "discard"),
            ),
            llm=LlmConfig(
                model=llm_raw.get("model", os.environ.get("LLM_MODEL", "qwen-plus")),
                base_url=llm_raw.get("base_url", os.environ.get("LLM_BASE_URL")),
                api_key=llm_raw.get("api_key", os.environ.get("LLM_API_KEY")),
                cache_path=(
                    (project_root / llm_raw.get("cache_path", "output/llm_classification_cache.sqlite3")).resolve()
                    if llm_raw.get("cache_path", "output/llm_classification_cache.sqlite3")
                    else None
                ),
                temperature=llm_raw.get("temperature", 0.0),
                timeout_seconds=llm_raw.get("timeout_seconds", 90),
                max_retries=llm_raw.get("max_retries", int(os.environ.get("LLM_MAX_RETRIES", "5"))),
                simulate_cache_stream=llm_raw.get(
                    "simulate_cache_stream",
                    _env_bool("CACHE_SIMULATION_ENABLED", False),
                ),
                cache_first_token_delay_seconds=float(
                    llm_raw.get(
                        "cache_first_token_delay_seconds",
                        os.environ.get("CACHE_SIMULATION_FIRST_TOKEN_DELAY_SECONDS", "1.0"),
                    )
                ),
                cache_tokens_per_second=float(
                    llm_raw.get(
                        "cache_tokens_per_second",
                        os.environ.get("CACHE_SIMULATION_TOKENS_PER_SECOND", "120"),
                    )
                ),
            ),
            embedding=EmbeddingConfig(
                model=embedding_raw.get("model", os.environ.get("EMBEDDING_MODEL", "text-embedding-v4")),
                base_url=embedding_raw.get("base_url", os.environ.get("EMBEDDING_BASE_URL")),
                api_key=embedding_raw.get("api_key", os.environ.get("EMBEDDING_API_KEY")),
                cache_path=(
                    (project_root / embedding_raw.get("cache_path", "output/event_vector_cache.sqlite3")).resolve()
                    if embedding_raw.get("cache_path", "output/event_vector_cache.sqlite3")
                    else None
                ),
                timeout_seconds=embedding_raw.get("timeout_seconds", 60),
                max_retries=embedding_raw.get("max_retries", int(os.environ.get("EMBEDDING_MAX_RETRIES", "5"))),
                simulate_cache_stream=embedding_raw.get(
                    "simulate_cache_stream",
                    _env_bool("CACHE_SIMULATION_ENABLED", False),
                ),
                cache_first_token_delay_seconds=float(
                    embedding_raw.get(
                        "cache_first_token_delay_seconds",
                        os.environ.get("CACHE_SIMULATION_FIRST_TOKEN_DELAY_SECONDS", "1.0"),
                    )
                ),
                cache_tokens_per_second=float(
                    embedding_raw.get(
                        "cache_tokens_per_second",
                        os.environ.get("CACHE_SIMULATION_TOKENS_PER_SECOND", "120"),
                    )
                ),
            ),
            checkpoint_path=(
                (project_root / classification_raw.get("checkpoint_path", "output/classification_progress.json")).resolve()
                if classification_raw.get("checkpoint_path", "output/classification_progress.json")
                else None
            ),
        ),
        history_dedupe=HistoryDedupeConfig(
            enabled=history_raw.get("enabled", True),
            history_path=(project_root / history_raw.get("history_path", "output/event_history.json")).resolve(),
            lookback_days=int(history_raw.get("lookback_days", 14)),
            similarity_threshold=float(history_raw.get("similarity_threshold", 0.72)),
        ),
        paper_attach=PaperAttachConfig(
            enabled=paper_attach_raw.get("enabled", True),
            output_path=(project_root / paper_attach_raw.get("output_path", "output/arxiv_papers.json")).resolve(),
            decisions_output_path=(
                project_root / paper_attach_raw.get("decisions_output_path", "output/paper_attach_decisions.json")
            ).resolve(),
            source=paper_attach_raw.get("source", "huggingface_papers_trending"),
            sources=_paper_sources(paper_attach_raw),
            limit=int(paper_attach_raw.get("limit", 40)),
            huggingface_limit=int(paper_attach_raw.get("huggingface_limit", 30)),
            huggingface_url=paper_attach_raw.get("huggingface_url", "https://huggingface.co/papers/trending"),
            query=paper_attach_raw.get(
                "query",
                (
                    "cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.CV OR cat:stat.ML "
                    'OR all:"large language model" OR all:"LLM" OR all:"agent"'
                ),
            ),
            sort_by=paper_attach_raw.get("sort_by", "submittedDate"),
            sort_order=paper_attach_raw.get("sort_order", "descending"),
            max_summary_chars=int(paper_attach_raw.get("max_summary_chars", 700)),
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


def _paper_sources(raw: dict[str, Any]) -> list[str]:
    value = raw.get("sources")
    if isinstance(value, list):
        sources = [str(item).strip() for item in value if str(item).strip()]
        return sources or ["huggingface_papers_trending"]
    source = str(raw.get("source") or "huggingface_papers_trending").strip()
    if source in {"all", "default"}:
        return ["huggingface_papers_trending"]
    return [source or "huggingface_papers_trending"]
