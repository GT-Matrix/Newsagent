from __future__ import annotations

import json
import os
from typing import Any

from modnews.core.env import ensure_runtime_env
from modnews.repository.outputs import OutputRepository
from modnews.core.paths import runtime_paths
from modnews.core.progress import BUS, sse
from modnews.repository.source_config import source_config_repository


class RuntimeLocalMixin:
    def state(self) -> dict[str, Any]:
        payload = BUS.snapshot()
        payload["outputs"] = OutputRepository(self.project_root).state()
        return payload

    def event_stream(self):
        def stream():
            listener = BUS.listen()
            try:
                yield "retry: 1000\n\n"
                for event in BUS.snapshot()["events"]:
                    yield f"event: replay\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                while True:
                    yield sse(listener.get())
            finally:
                BUS.unlisten(listener)

        return stream()

    def events_list(self, limit: int = 100) -> list[dict[str, Any]]:
        return BUS.snapshot()["events"][-limit:]

    def config_show(self, include_paths: bool = False) -> dict[str, Any]:
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

    def config_env_health(self) -> dict[str, Any]:
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
        config = self.config_show()
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

    def config_update_step(self, step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_repository(self.project_root).update_step(step_id, patch)

    def config_update_classification(self, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_repository(self.project_root).update_classification(patch)

    def config_restore_builtins(self) -> dict[str, Any]:
        return source_config_repository(self.project_root).restore_builtin_sources()

    def rss_update(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return source_config_repository(self.project_root).update_rss(items)

    def rss_update_item(self, source_id: str, row: dict[str, Any]) -> dict[str, Any]:
        return source_config_repository(self.project_root).upsert_rss(source_id, row)

    def rss_delete_item(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).delete_rss(source_id)

    def newsnow_update_item(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_repository(self.project_root).update_newsnow(source_id, patch)

    def site_list_update_item(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_repository(self.project_root).upsert_site(source_id, patch)

    def site_list_delete_item(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).delete_site(source_id)

    def config_set(self, key_path: str, value: Any) -> dict[str, Any]:
        parts = key_path.split(".")
        if len(parts) < 2:
            raise ValueError("config key must include a section")
        data = self.config_show()
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

    def sources_list(self, source_type: str | None = None) -> list[dict[str, Any]]:
        return source_config_repository(self.project_root).list(source_type)

    def sources_rss_add(self, source_id: str, url: str, name: str | None = None, content_type: str = "news") -> dict[str, Any]:
        return source_config_repository(self.project_root).upsert_rss(
            source_id,
            {"id": source_id, "url": url, "name": name or source_id, "enabled": True, "content_type": content_type},
        )

    def sources_rss_disable(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).disable_rss(source_id)

    def sources_site_add(
        self,
        source_id: str,
        url: str,
        *,
        name: str | None = None,
        extractor_id: str | None = None,
        content_type: str = "news",
    ) -> dict[str, Any]:
        return source_config_repository(self.project_root).upsert_site(
            source_id,
            {
                "id": source_id,
                "url": url,
                "name": name or source_id,
                "enabled": True,
                "extractor_id": extractor_id or source_id,
                "content_type": content_type,
            },
        )

    def sources_site_disable(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).disable_site(source_id)

    def sources_site_delete(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).delete_site(source_id)


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
