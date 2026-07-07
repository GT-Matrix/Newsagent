from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.service.classify.planner import build_clustered_event_extraction_task
from modnews.service.classify.task_registry import resolve_clustered_classify_run_id
from modnews.service.pipeline.step import PipelineStepDescriptor
from modnews.service.task_entrypoints import run_planned_tasks


def submit_clustered_classify_run(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    run_id: str | None,
    input_path: str | None,
    config: str | None = None,
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any]:
    task_run_id = str(resolve_clustered_classify_run_id(run_id))
    extraction_task = build_clustered_event_extraction_task(
        project_root=project_root,
        run_id=task_run_id,
        input_path=input_path,
        config=config,
    )
    return run_planned_tasks(
        project_root=project_root,
        queue=queue,
        queue_show=queue_show,
        run_id=task_run_id,
        tasks=[extraction_task],
        create_payload={"source": "manual_classify_entrypoint", "input_path": input_path, "config": config},
        task_result_scope="run",
        pipeline_descriptors=pipeline_descriptors,
    )
