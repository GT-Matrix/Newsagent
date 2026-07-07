from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from modnews.service.pipeline.step import PipelineStepDescriptor
from modnews.service.task_entrypoints import run_planned_tasks
from modnews.service.extraction.task_registry import (
    build_registered_web_source_task,
    get_registered_extraction_task,
)


@dataclass(slots=True)
class WebSourceRuntimeFacade:
    project_root: Path
    queue: Any
    queue_show: Callable[[str], dict[str, Any]]
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None

    def run_source(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = str(payload.get("task_id") or f"web-source-{source_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
        run_id = str(payload.get("run_id") or f"web-source-{source_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
        task = build_registered_web_source_task(
            get_registered_extraction_task("web_source.run"),
            project_root=self.project_root,
            run_id=run_id,
            source_id=source_id,
            config_path=payload.get("config"),
            limit=int(payload["limit"]) if payload.get("limit") is not None else 10,
            max_concurrency=1,
        )
        if task_id:
            task.id = task_id  # type: ignore[misc]
        if payload.get("scrape_date") is not None:
            task.payload["scrape_date"] = payload.get("scrape_date")
        task.concurrency_key = f"web_source:{source_id}"
        result = run_planned_tasks(
            project_root=self.project_root,
            queue=self.queue,
            queue_show=self.queue_show,
            run_id=run_id,
            tasks=[task],
            create_payload={
                "source": "manual_web_source_entrypoint",
                "source_id": source_id,
                "limit": task.payload.get("limit"),
                "scrape_date": task.payload.get("scrape_date"),
                "config": payload.get("config"),
            },
            pipeline_descriptors=self.pipeline_descriptors,
        )
        task_payload = result["tasks"][0] if result["tasks"] else {}
        job = task_payload.get("result", {}).get("job") if isinstance(task_payload.get("result"), dict) else None
        return {
            **result,
            "task": task_payload,
            "item": job,
        }
