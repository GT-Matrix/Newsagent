from __future__ import annotations

from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.pipeline.registry import PipelineRegistry
from modnews.service.pipeline.step import PipelinePlanContext


def start_pipeline_run(
    registry: PipelineRegistry,
    event_queue: EventQueue | None,
    request: dict[str, Any],
    *,
    submit: bool,
) -> dict[str, Any]:
    run_id = str(request.get("run_id") or "local")
    tasks = registry.plan_run(PipelinePlanContext(run_id=run_id, request=request))
    if event_queue:
        for task in tasks:
            if submit:
                event_queue.submit(task)
            else:
                event_queue.register(task)
    return {"run_id": run_id, "registered_tasks": [task.to_dict() for task in tasks]}
