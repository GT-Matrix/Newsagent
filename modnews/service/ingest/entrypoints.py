from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.service.ingest.queue_runtime import submit_ingest_step_run
from modnews.service.pipeline.step import PipelineStepDescriptor


def run_ingest_step_tasks(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    step_id: str,
    run_id: str | None = None,
    config_path: object = None,
    options: dict[str, Any] | None = None,
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any]:
    return submit_ingest_step_run(
        project_root=project_root,
        queue=queue,
        queue_show=queue_show,
        step_id=step_id,
        run_id=run_id,
        config_path=config_path,
        options=options,
        pipeline_descriptors=pipeline_descriptors,
    )
