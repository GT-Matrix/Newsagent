from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modnews.core.task import TaskEvent


@dataclass(frozen=True, slots=True)
class RegisteredPipelineTask:
    task_type: str
    step_id: str
    task_id_suffix: str
    concurrency_key_prefix: str
    max_concurrency: int


REGISTERED_PIPELINE_TASKS: tuple[RegisteredPipelineTask, ...] = (
    RegisteredPipelineTask(
        task_type="pipeline.combine_ingest",
        step_id="pipeline/combine_ingest",
        task_id_suffix="combine-ingest",
        concurrency_key_prefix="pipeline",
        max_concurrency=1,
    ),
)

REGISTERED_PIPELINE_TASK_BY_TYPE: dict[str, RegisteredPipelineTask] = {
    spec.task_type: spec
    for spec in REGISTERED_PIPELINE_TASKS
}


def get_registered_pipeline_task(task_type: str) -> RegisteredPipelineTask:
    return REGISTERED_PIPELINE_TASK_BY_TYPE[task_type]


def build_registered_pipeline_task(
    spec: RegisteredPipelineTask,
    *,
    project_root: Path,
    run_id: str,
    depends_on: list[str] | None = None,
) -> TaskEvent:
    return TaskEvent(
        id=f"pipeline-{run_id}-{spec.task_id_suffix}",
        type=spec.task_type,
        pipeline_run_id=run_id,
        step_id=spec.step_id,
        payload={
            "project_root": str(project_root),
            "run_id": run_id,
        },
        depends_on=list(depends_on or []),
        concurrency_key=f"{spec.concurrency_key_prefix}:{run_id}",
        max_concurrency=spec.max_concurrency,
    )
