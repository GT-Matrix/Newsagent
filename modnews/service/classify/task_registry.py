from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from modnews.core.task import TaskEvent

from .steps import get_registered_classify_flow


@dataclass(frozen=True, slots=True)
class RegisteredClassifyTask:
    task_type: str
    step_id: str
    task_id_suffix: str
    auto_publish: bool
    flow_name: str
    concurrency_key: str = "classify"
    max_concurrency: int = 1
    default_input_path: str | None = None
    default_write_fixed_outputs: bool = False

    @property
    def step_names(self) -> tuple[str, ...]:
        return get_registered_classify_flow(self.flow_name).step_names

    def build_steps(self):
        return get_registered_classify_flow(self.flow_name).build_steps()


REGISTERED_CLASSIFY_TASKS: tuple[RegisteredClassifyTask, ...] = (
    RegisteredClassifyTask(
        task_type="classify.clustered_event_extraction",
        step_id="classify/clustered_event_extraction",
        task_id_suffix="clustered-event-extraction",
        auto_publish=False,
        flow_name="clustered_event_extraction_task",
        default_input_path="__combined_ingest__",
    ),
    RegisteredClassifyTask(
        task_type="classify.clustered_event_merge",
        step_id="classify/clustered_event_merge",
        task_id_suffix="clustered-event-merge",
        auto_publish=True,
        flow_name="clustered_event_merge_task",
        default_input_path="__combined_ingest__",
    ),
)

REGISTERED_CLASSIFY_TASK_BY_TYPE: dict[str, RegisteredClassifyTask] = {
    spec.task_type: spec
    for spec in REGISTERED_CLASSIFY_TASKS
}


def get_registered_classify_task(task_type: str) -> RegisteredClassifyTask:
    return REGISTERED_CLASSIFY_TASK_BY_TYPE[task_type]


def resolve_clustered_classify_run_id(run_id: str | None) -> str:
    return run_id or f"classify-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


def build_registered_classify_task(
    spec: RegisteredClassifyTask,
    *,
    project_root: Path,
    run_id: str,
    input_path: str | None,
    config: str | None = None,
    depends_on: list[str] | None = None,
) -> TaskEvent:
    return TaskEvent(
        id=f"classify-{run_id}-{spec.task_id_suffix}",
        type=spec.task_type,
        pipeline_run_id=run_id,
        step_id=spec.step_id,
        payload={
            "project_root": str(project_root),
            "run_id": run_id,
            "config": config,
            "input_path": input_path if input_path is not None else spec.default_input_path,
            "write_fixed_outputs": spec.default_write_fixed_outputs,
        },
        depends_on=list(depends_on or []),
        concurrency_key=spec.concurrency_key,
        max_concurrency=spec.max_concurrency,
    )
