from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.bootstrap import configure_services
from modnews.repository.cache import CacheRepository
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.outputs import OutputRepository
from modnews_pipeline.config import apply_runtime_overrides, load_config
from modnews_pipeline.extractors.registry import registry_from_project
from modnews_pipeline.extractors.repair import RepairManager
from modnews_pipeline.paths import runtime_paths
from modnews_pipeline.pipeline import run_pipeline
from modnews_pipeline.progress import BUS, emit, sse
from modnews_pipeline.sources import source_config_store
from modnews_pipeline.web_extraction.contract import WebSource
from modnews_pipeline.web_extraction.job_store import WebJobStore
from modnews_pipeline.web_extraction.orchestrator import WebExtractionOrchestrator


class LocalClient:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.container = configure_services(self.project_root)

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

    def queue_status(self) -> dict[str, Any]:
        return {"counts": self.container.event_queue.status()}

    def queue_list(self, states: set[str] | None = None) -> list[dict[str, Any]]:
        return [task.to_dict() for task in self.container.event_queue.list(states)]

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
        if parts[0] == "steps" and len(parts) >= 3:
            return self.config_update_step(parts[1], {".".join(parts[2:]): value})
        if parts[0] == "classification":
            return self.config_update_classification({".".join(parts[1:]): value})
        data = self.config_show()
        target = data
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
        return source_config_store(self.project_root).save(data)

    def run_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        BUS.clear()
        emit("pipeline_start", started_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        config = load_config(payload.get("config"))
        apply_runtime_overrides(
            config,
            only_ingest_steps=payload.get("only_ingest_steps") or payload.get("only"),
            disable_classification=bool(payload.get("disable_classification")),
        )
        result_holder: dict[str, Any] = {"state": "running"}

        def target() -> None:
            try:
                result = run_pipeline(config)
                result_holder.update({"state": "succeeded", "output_path": str(result.output_path), "total": len(result.items)})
                emit("pipeline_done", output_path=str(result.output_path), stats={"total": len(result.items), "events": len(result.events)})
            except Exception as exc:
                result_holder.update({"state": "failed", "error": str(exc)})
                emit("pipeline_error", error=str(exc))

        if payload.get("background", True):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            return {"ok": True, "state": "started"}
        target()
        return {"ok": result_holder.get("state") == "succeeded", **result_holder}

    def run_list(self) -> list[dict[str, Any]]:
        return CheckpointRepository(self.project_root).list()

    def run_status(self, run_id: str | None = None) -> dict[str, Any]:
        return {"run_id": run_id, "state": self.state()}

    def extractors_list(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in registry_from_project(self.project_root).list()]

    def extractor_set_enabled(self, source_id: str, enabled: bool) -> dict[str, Any]:
        return registry_from_project(self.project_root).set_enabled(source_id, enabled).to_dict()

    def extractor_delete(self, source_id: str) -> None:
        registry_from_project(self.project_root).delete(source_id)

    def web_jobs(self) -> list[dict[str, Any]]:
        return WebJobStore(self.project_root).list()

    def web_job(self, job_id: str, include_events: bool = False) -> dict[str, Any]:
        return WebJobStore(self.project_root).get_dict(job_id, include_events=include_events)

    def web_job_events(self, job_id: str) -> list[dict[str, Any]]:
        return WebJobStore(self.project_root).events(job_id)

    def web_source_run(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        config = source_config_store(self.project_root).load()
        raw = config.get("sources", {}).get("site_lists", {}).get(source_id)
        if not isinstance(raw, dict):
            return {"ok": False, "error": "source not found"}
        source = WebSource.from_config(source_id, raw)
        limit = int(payload.get("limit") or config.get("steps", {}).get("site_lists", {}).get("limit_per_site", 10))
        scrape_date = str(payload.get("scrape_date") or datetime.now().astimezone().isoformat(timespec="seconds"))
        job = WebExtractionOrchestrator(self.project_root).run_source(source, scrape_date=scrape_date, limit=limit)
        return {"ok": True, "item": job.to_dict()}

    def repair_tasks(self) -> list[dict[str, Any]]:
        return RepairManager(self.project_root, registry_from_project(self.project_root)).list_tasks()

    def repair_task(self, task_id: str) -> dict[str, Any]:
        return RepairManager(self.project_root, registry_from_project(self.project_root)).get_task(task_id)

    def repair_create(self, payload: dict[str, Any]) -> dict[str, Any]:
        task = RepairManager(self.project_root, registry_from_project(self.project_root)).create_task(
            str(payload["source_id"]),
            reason=str(payload.get("reason") or "manual repair request"),
            auto_start=bool(payload.get("auto_start", True)),
        )
        return {"ok": True, "item": task.to_dict()}

    def repair_retry(self, task_id: str) -> dict[str, Any]:
        task = RepairManager(self.project_root, registry_from_project(self.project_root)).retry_task(task_id)
        return {"ok": True, "item": task.to_dict()}

    def repair_promote(self, task_id: str) -> dict[str, Any]:
        task = RepairManager(self.project_root, registry_from_project(self.project_root)).promote_task(task_id)
        return {"ok": True, "item": task.to_dict()}

    def repair_delete(self, task_id: str) -> dict[str, Any]:
        RepairManager(self.project_root, registry_from_project(self.project_root)).delete_task(task_id)
        return {"ok": True}

    def outputs_status(self) -> dict[str, Any]:
        return OutputRepository(self.project_root).state()

    def cache_status(self) -> dict[str, Any]:
        return CacheRepository(self.project_root).state()

    def cache_clear(self, *, llm: bool, embedding: bool) -> dict[str, Any]:
        return {
            "ok": True,
            "removed": CacheRepository(self.project_root).clear(llm=llm, embedding=embedding),
            "outputs": self.outputs_status(),
        }

    def checkpoints_list(self, run_id: str | None = None) -> list[dict[str, Any]]:
        return CheckpointRepository(self.project_root).list(run_id)
