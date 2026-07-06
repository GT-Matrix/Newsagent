from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modnews.core.task import TaskEvent

from .steps import build_registered_classify_steps


@dataclass(frozen=True, slots=True)
class RegisteredClassifyTask:
    task_type: str
    step_id: str
    task_id_suffix: str
    auto_publish: bool
    step_names: tuple[str, ...]

    def build_steps(self):
        return build_registered_classify_steps(*self.step_names)


REGISTERED_CLASSIFY_TASKS: tuple[RegisteredClassifyTask, ...] = (
    RegisteredClassifyTask(
        task_type="classify.clustered_event_extraction",
        step_id="classify/clustered_event_extraction",
        task_id_suffix="clustered-event-extraction",
        auto_publish=False,
        step_names=("start_checkpoint", "clustered_event_extraction"),
    ),
    RegisteredClassifyTask(
        task_type="classify.clustered_event_merge",
        step_id="classify/clustered_event_merge",
        task_id_suffix="clustered-event-merge",
        auto_publish=True,
        step_names=("clustered_event_merge",),
    ),
)

REGISTERED_CLASSIFY_TASK_BY_TYPE: dict[str, RegisteredClassifyTask] = {
    spec.task_type: spec
    for spec in REGISTERED_CLASSIFY_TASKS
}


def get_registered_classify_task(task_type: str) -> RegisteredClassifyTask:
    return REGISTERED_CLASSIFY_TASK_BY_TYPE[task_type]


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
            "input_path": input_path,
        },
        depends_on=list(depends_on or []),
        concurrency_key="classify",
        max_concurrency=1,
    )
