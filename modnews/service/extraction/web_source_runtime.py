from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from modnews.service.extraction.task_registry import (
    build_registered_web_source_task,
    get_registered_extraction_task,
)


@dataclass(slots=True)
class WebSourceRuntimeFacade:
    project_root: Path
    queue: Any
    queue_show: Callable[[str], dict[str, Any]]

    def run_source(self, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        task_id = str(payload.get("task_id") or f"web-source-{source_id}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
        task = build_registered_web_source_task(
            get_registered_extraction_task("web_source.run"),
            project_root=self.project_root,
            run_id=str(payload.get("run_id") or "manual"),
            source_id=source_id,
            config_path=payload.get("config"),
            limit=int(payload["limit"]) if payload.get("limit") is not None else 10,
            max_concurrency=1,
        )
        if task_id:
            task.id = task_id  # type: ignore[misc]
        if payload.get("scrape_date") is not None:
            task.payload["scrape_date"] = payload.get("scrape_date")
        task.step_id = "web_source"
        task.concurrency_key = f"web_source:{source_id}"
        self.queue.submit(task)
        result = self.queue_show(task.id)
        job = result.get("result", {}).get("job") if isinstance(result.get("result"), dict) else None
        return {"ok": result.get("state") == "succeeded", "task": result, "item": job}
