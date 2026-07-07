from __future__ import annotations

from pathlib import Path

from modnews.core.config import ClassificationConfig
from modnews.core.task import TaskEvent

from .runner import ClassifyRunResult
from .task_registry import RegisteredClassifyTask
from .task_result import build_classify_task_snapshot, persist_classify_task_result


def write_classify_task_checkpoint(
    project_root: Path,
    run_id: str,
    task: TaskEvent,
    spec: RegisteredClassifyTask,
    input_path: Path,
    run_result: ClassifyRunResult,
    config: ClassificationConfig,
) -> dict[str, object]:
    snapshot = build_classify_task_snapshot(
        step_id=spec.step_id,
        run_result=run_result,
    )
    return persist_classify_task_result(
        project_root=project_root,
        run_id=run_id,
        task=task,
        input_path=input_path,
        run_result=run_result,
        config=config,
        snapshot=snapshot,
        auto_publish=spec.auto_publish,
    )
