from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.service.classify.queue_runtime import submit_clustered_classify_run
from modnews.service.pipeline.step import PipelineStepDescriptor


def run_classify_tasks(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    run_id: str | None,
    input_path: str | None,
    config: str | None = None,
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any]:
    return submit_clustered_classify_run(
        project_root=project_root,
        queue=queue,
        queue_show=queue_show,
        run_id=run_id,
        input_path=input_path,
        config=config,
        pipeline_descriptors=pipeline_descriptors,
    )
