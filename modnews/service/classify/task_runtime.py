from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modnews.core.task import TaskEvent

from .runner import ClassifyRuntime
from .state import ClassifyState
from .io import resolve_input_path
from .runtime_build import (
    build_classify_runtime_for_context,
    build_classify_state_from_resolved_input,
    resolve_classify_state_input,
    resolve_classify_task_environment,
)
from .task_registry import get_registered_classify_task


@dataclass(slots=True)
class ClusteredTaskRuntime:
    project_root: Path
    run_id: str
    input_path: Path
    state: ClassifyState
    runtime: ClassifyRuntime


def prepare_clustered_task_runtime(task: TaskEvent) -> ClusteredTaskRuntime:
    spec = get_registered_classify_task(task.type)
    env = resolve_classify_task_environment(task)
    input_path = resolve_input_path(env.project_root, env.run_id, task.payload.get("input_path"), env.config.output_path)
    resolved_state_input = resolve_classify_state_input(
        env.project_root,
        env.run_id,
        input_path=input_path,
        prefer_run_checkpoint=True,
    )
    state = build_classify_state_from_resolved_input(resolved_state_input)
    runtime = build_classify_runtime_for_context(
        env.ctx,
        env.config.classification,
        write_fixed_outputs=bool(task.payload.get("write_fixed_outputs", spec.default_write_fixed_outputs)),
    )
    return ClusteredTaskRuntime(
        project_root=env.project_root,
        run_id=env.run_id,
        input_path=input_path,
        state=state,
        runtime=runtime,
    )
