from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modnews.core.config import load_config
from modnews.core.task import TaskEvent

from .runner import ClassifyRuntime
from .state import ClassifyState
from .io import resolve_input_path
from .runtime_build import build_classify_runtime, build_classify_state_from_resolved_input, resolve_classify_state_input
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
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
    config = load_config(task.payload.get("config"), project_root=project_root)
    input_path = resolve_input_path(project_root, run_id, task.payload.get("input_path"), config.output_path)
    resolved_state_input = resolve_classify_state_input(
        project_root,
        run_id,
        input_path=input_path,
        prefer_run_checkpoint=True,
    )
    state = build_classify_state_from_resolved_input(resolved_state_input)
    runtime = build_classify_runtime(
        config,
        write_fixed_outputs=bool(task.payload.get("write_fixed_outputs", spec.default_write_fixed_outputs)),
    )
    return ClusteredTaskRuntime(
        project_root=project_root,
        run_id=run_id,
        input_path=input_path,
        state=state,
        runtime=runtime,
    )
