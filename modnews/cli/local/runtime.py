from __future__ import annotations

import json
import os
from typing import Any

from modnews.core.env import ensure_runtime_env
from modnews.core.progress import BUS, sse
from modnews.repository.outputs import OutputRepository
from modnews.repository.runtime_config_facade import RuntimeConfigFacade
from modnews.repository.source_config import source_config_repository


class RuntimeLocalMixin:
    def state(self) -> dict[str, Any]:
        payload = BUS.snapshot()
        payload["outputs"] = OutputRepository(self.project_root).state()
        payload["pipeline"] = {"steps": self.pipeline_steps()}
        return payload

    def pipeline_steps(self) -> list[dict[str, Any]]:
        return [
            {
                "step_id": descriptor.step_id,
                "title": descriptor.title,
                "group": descriptor.group,
                "kind": descriptor.kind,
                "description": descriptor.description,
                "depends_on": list(descriptor.depends_on),
                "callback_handlers": list(descriptor.callback_handlers),
                "concrete_step_ids": list(descriptor.concrete_step_ids),
                "concrete_step_prefixes": list(descriptor.concrete_step_prefixes),
                "followups": [
                    {
                        "trigger": followup.trigger,
                        "builder_id": followup.builder_id,
                        "task_type": followup.task_type,
                        "step_prefix": followup.step_prefix,
                    }
                    for followup in descriptor.followups
                ],
            }
            for descriptor in self.container.pipeline_manager.describe_steps()
        ]

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
        return self._runtime_config().show(include_paths=include_paths)

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
        return self._runtime_config().source_diagnostics()

    def config_update_step(self, step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return self._runtime_config().update_step(step_id, patch)

    def config_update_classification(self, patch: dict[str, Any]) -> dict[str, Any]:
        return self._runtime_config().update_classification(patch)

    def config_restore_builtins(self) -> dict[str, Any]:
        return self._runtime_config().restore_builtins()

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
        return self._runtime_config().set_value(key_path, value)

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

    def _runtime_config(self) -> RuntimeConfigFacade:
        return RuntimeConfigFacade(self.project_root)

    def sources_site_disable(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).disable_site(source_id)

    def sources_site_delete(self, source_id: str) -> dict[str, Any]:
        return source_config_repository(self.project_root).delete_site(source_id)
