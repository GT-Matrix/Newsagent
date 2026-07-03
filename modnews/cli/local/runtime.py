from __future__ import annotations

import json
from typing import Any

from modnews.repository.outputs import OutputRepository
from modnews.core.paths import runtime_paths
from modnews.repository.source_config import source_config_store
from modnews_pipeline.progress import BUS, sse


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
        payload = source_config_store(self.project_root).load()
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

    def config_update_step(self, step_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_store(self.project_root).update_step(step_id, patch)

    def config_update_classification(self, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_store(self.project_root).update_classification(patch)

    def config_restore_builtins(self) -> dict[str, Any]:
        return source_config_store(self.project_root).restore_builtin_sources()

    def rss_update(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return source_config_store(self.project_root).update_rss(items)

    def rss_update_item(self, source_id: str, row: dict[str, Any]) -> dict[str, Any]:
        return source_config_store(self.project_root).update_rss_item(source_id, row)

    def rss_delete_item(self, source_id: str) -> dict[str, Any]:
        return source_config_store(self.project_root).delete_rss_item(source_id)

    def newsnow_update_item(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_store(self.project_root).update_newsnow_item(source_id, patch)

    def site_list_update_item(self, source_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return source_config_store(self.project_root).update_site_list_item(source_id, patch)

    def config_set(self, key_path: str, value: Any) -> dict[str, Any]:
        parts = key_path.split(".")
        if len(parts) < 2:
            raise ValueError("config key must include a section")
        data = self.config_show()
        if parts[0] == "steps" and len(parts) >= 3:
            step = data.setdefault("steps", {}).setdefault(parts[1], {})
            _set_nested(step, parts[2:], value)
            return source_config_store(self.project_root).save(data)
        if parts[0] == "classification":
            classification = data.setdefault("classification", {})
            _set_nested(classification, parts[1:], value)
            return source_config_store(self.project_root).save(data)
        target = data
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
        return source_config_store(self.project_root).save(data)


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
