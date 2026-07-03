from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from modnews.bootstrap import configure_services
from modnews.core.task import TaskEvent
from modnews.repository.cache import CacheRepository
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.outputs import OutputRepository
from modnews.repository.runs import RunRepository
from modnews_pipeline.extractors.registry import registry_from_project
from modnews_pipeline.extractors.repair import RepairManager
from modnews_pipeline.paths import runtime_paths
from modnews_pipeline.progress import BUS, emit, sse
from modnews_pipeline.sources import source_config_store
from modnews_pipeline.web_extraction.job_store import WebJobStore


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

    def queue_show(self, task_id: str) -> dict[str, Any]:
        task = self.container.event_queue.get(task_id).to_dict()
        task["result"] = self.container.event_queue.result(task_id)
        return task

    def queue_echo(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task = TaskEvent(id=task_id, type="diagnostic.echo", payload=payload)
        self.container.event_queue.dispatch(task)
        return self.queue_show(task_id)

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

    def run_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or f"{datetime.now().strftime('%Y%m%dT%H%M%S')}-main")
        task_id = str(payload.get("task_id") or f"pipeline-{run_id}")
        runs = RunRepository(self.project_root)
        run_record = runs.create(run_id, payload)
        task = TaskEvent(
            id=task_id,
            type="pipeline.run_legacy",
            pipeline_run_id=run_id,
            step_id="pipeline",
            payload={
                "project_root": str(self.project_root),
                "run_id": run_id,
                "config": payload.get("config"),
                "only": payload.get("only"),
                "only_ingest_steps": payload.get("only_ingest_steps"),
                "disable_classification": payload.get("disable_classification"),
            },
            concurrency_key="pipeline",
            max_concurrency=1,
        )
        self.container.event_queue.register(task)
        runs.update(run_id, state="queued", task_id=task_id)
        if payload.get("background", True):
            return {"ok": True, "run": runs.get(run_id), "task": task.to_dict()}
        BUS.clear()
        emit("pipeline_start", started_at=datetime.now().astimezone().isoformat(timespec="seconds"), run_id=run_id)
        self.container.event_queue.run(task_id)
        task_payload = self.queue_show(task_id)
        run_record = runs.get(run_id)
        ok = task_payload.get("state") == "succeeded"
        if ok:
            emit("pipeline_done", run_id=run_id, output_path=run_record.get("output_path"), stats=run_record.get("stats", {}))
        else:
            emit("pipeline_error", run_id=run_id, error=task_payload.get("result", {}).get("error"))
        return {"ok": ok, "run": run_record, "task": task_payload}

    def run_list(self) -> list[dict[str, Any]]:
        return RunRepository(self.project_root).list()

    def run_status(self, run_id: str | None = None) -> dict[str, Any]:
        if run_id:
            return RunRepository(self.project_root).get(run_id)
        return {"runs": self.run_list(), "state": self.state()}

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
        task_id = str(payload.get("task_id") or f"web-source-{source_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
        task = TaskEvent(
            id=task_id,
            type="web_source.run",
            step_id="web_source",
            payload={
                "project_root": str(self.project_root),
                "source_id": source_id,
                "limit": payload.get("limit"),
                "scrape_date": payload.get("scrape_date"),
            },
            concurrency_key=f"web_source:{source_id}",
            max_concurrency=1,
        )
        self.container.event_queue.dispatch(task)
        result = self.queue_show(task_id)
        job = result.get("result", {}).get("job") if isinstance(result.get("result"), dict) else None
        return {"ok": result.get("state") == "succeeded", "task": result, "item": job}

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
