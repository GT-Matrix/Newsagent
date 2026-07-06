from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from modnews.core.env import ensure_runtime_env
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

    def env_health(self) -> dict[str, Any]:
        env_file = ensure_runtime_env(self.project_root)
        return {
            "env_file": str(env_file) if env_file else None,
            "models": {
                "llm": {
                    "model": os.environ.get("LLM_MODEL"),
                    "base_url": os.environ.get("LLM_BASE_URL"),
                    "api_key_present": bool(os.environ.get("LLM_API_KEY")),
                    "timeout_seconds": os.environ.get("LLM_TIMEOUT_SECONDS"),
                    "max_retries": os.environ.get("LLM_MAX_RETRIES"),
                },
                "embedding": {
                    "model": os.environ.get("EMBEDDING_MODEL"),
                    "base_url": os.environ.get("EMBEDDING_BASE_URL"),
                    "api_key_present": bool(os.environ.get("EMBEDDING_API_KEY")),
                    "timeout_seconds": os.environ.get("EMBEDDING_TIMEOUT_SECONDS"),
                },
            },
            "runtime": {
                "news_mode": os.environ.get("NEWS_MODE"),
                "source_lab_proxy": os.environ.get("SOURCE_LAB_PROXY"),
                "newsnow_api_url": os.environ.get("NEWSNOW_API_URL"),
                "rss_api_url_present": bool(os.environ.get("MODNEWS_RSS_API_URL")),
                "site_lists_api_url_present": bool(os.environ.get("MODNEWS_SITE_LISTS_API_URL")),
                "cache_simulation_enabled": os.environ.get("CACHE_SIMULATION_ENABLED"),
            },
            "paths": {
                name: {"value": os.environ.get(name), "is_set": bool(os.environ.get(name))}
                for name in (
                    "MODNEWS_RUNTIME_DIR",
                    "MODNEWS_OUTPUT_DIR",
                    "MODNEWS_PROCESS_DIR",
                    "MODNEWS_CACHE_DIR",
                    "MODNEWS_AGENT_WORK_DIR",
                )
            },
        }

    def source_diagnostics(self) -> dict[str, Any]:
        config = self.show()
        steps = config.get("steps", {})
        sources = config.get("sources", {})
        items: list[dict[str, Any]] = []

        rss_step = steps.get("rss", {}) if isinstance(steps.get("rss"), dict) else {}
        for row in sources.get("rss", []) if isinstance(sources.get("rss"), list) else []:
            if not isinstance(row, dict):
                continue
            active = bool(rss_step.get("enabled", True) and row.get("enabled", True))
            reasons = []
            if not rss_step.get("enabled", True):
                reasons.append("step_disabled")
            if not row.get("enabled", True):
                reasons.append("source_disabled")
            items.append(_diagnostic_row("rss", str(row.get("id") or ""), row.get("name"), active, reasons))

        newsnow_step = steps.get("newsnow", {}) if isinstance(steps.get("newsnow"), dict) else {}
        allowed_columns = set(newsnow_step.get("columns", ["tech", "finance"]))
        include_all = bool(newsnow_step.get("include_all", False))
        newsnow_sources = sources.get("newsnow", {}) if isinstance(sources.get("newsnow"), dict) else {}
        for source_id, row in newsnow_sources.items():
            if not isinstance(row, dict):
                continue
            allowed = include_all or row.get("column") in allowed_columns
            active = bool(newsnow_step.get("enabled", True) and row.get("enabled", True) and not row.get("redirect") and allowed)
            reasons = []
            if not newsnow_step.get("enabled", True):
                reasons.append("step_disabled")
            if not row.get("enabled", True):
                reasons.append("source_disabled")
            if row.get("redirect"):
                reasons.append("redirect_source")
            if not allowed:
                reasons.append("column_filtered")
            items.append(_diagnostic_row("newsnow", str(source_id), row.get("name"), active, reasons))

        site_step = steps.get("site_lists", {}) if isinstance(steps.get("site_lists"), dict) else {}
        site_ids = site_step.get("sites", [])
        site_filter = set(site_ids) if isinstance(site_ids, list) else set()
        site_sources = sources.get("site_lists", {}) if isinstance(sources.get("site_lists"), dict) else {}
        for source_id, row in site_sources.items():
            if not isinstance(row, dict):
                continue
            listed = not site_filter or source_id in site_filter
            active = bool(site_step.get("enabled", True) and row.get("enabled", True) and listed)
            reasons = []
            if not site_step.get("enabled", True):
                reasons.append("step_disabled")
            if not row.get("enabled", True):
                reasons.append("source_disabled")
            if not listed:
                reasons.append("not_in_sites")
            if not row.get("extractor_id"):
                reasons.append("missing_extractor")
            if not row.get("url"):
                reasons.append("missing_url")
            items.append(_diagnostic_row("site_lists", str(source_id), row.get("name"), active, reasons))

        return {
            "items": items,
            "summary": {
                "total": len(items),
                "active": sum(1 for item in items if item["active"]),
                "inactive": sum(1 for item in items if not item["active"]),
                "warnings": sum(1 for item in items if item["reasons"]),
            },
        }

    def set_value(self, key_path: str, value: Any) -> dict[str, Any]:
        parts = key_path.split(".")
        if len(parts) < 2:
            raise ValueError("config key must include a section")
        data = self.show()
        if parts[0] == "steps" and len(parts) >= 3:
            step = data.setdefault("steps", {}).setdefault(parts[1], {})
            _set_nested(step, parts[2:], value)
            return source_config_repository(self.project_root).save(data)
        if parts[0] == "classification":
            classification = data.setdefault("classification", {})
            _set_nested(classification, parts[1:], value)
            return source_config_repository(self.project_root).save(data)
        target = data
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
        return source_config_repository(self.project_root).save(data)


def _set_nested(target: dict[str, Any], parts: list[str], value: Any) -> None:
    if not parts:
        raise ValueError("missing config key")
    current = target
    for part in parts[:-1]:
        next_value = current.setdefault(part, {})
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[parts[-1]] = value


def _diagnostic_row(source_type: str, source_id: str, name: Any, active: bool, reasons: list[str]) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "id": source_id,
        "name": str(name or source_id),
        "active": active,
        "reasons": reasons,
    }
