from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.service.pipeline.step import PipelineStepDescriptor
from modnews.service.report.runtime_facade import ReportRuntimeFacade


def run_report_tasks(
    *,
    project_root: Path,
    queue: Any,
    queue_show: Any,
    input_path: str,
    run_id: str | None = None,
    output_dir: str | None = None,
    date: str | None = None,
    config: str | None = None,
    pipeline_descriptors: list[PipelineStepDescriptor] | None = None,
) -> dict[str, Any]:
    return ReportRuntimeFacade(
        project_root=project_root,
        queue=queue,
        queue_show=queue_show,
        pipeline_descriptors=pipeline_descriptors,
    ).run(
        {
            "input": input_path,
            "run_id": run_id,
            "output_dir": output_dir,
            "date": date,
            "config": config,
        }
    )
