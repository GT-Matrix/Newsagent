from __future__ import annotations

from pathlib import Path

from modnews.core.task import TaskEvent
from .task_registry import (
    build_registered_classify_task,
    get_registered_classify_task,
)


def build_clustered_event_extraction_task(
    *,
    project_root: Path,
    run_id: str,
    input_path: str | None,
    config: str | None = None,
    depends_on: list[str] | None = None,
) -> TaskEvent:
    return build_registered_classify_task(
        get_registered_classify_task("classify.clustered_event_extraction"),
        project_root=project_root,
        run_id=run_id,
        input_path=input_path,
        config=config,
        depends_on=depends_on,
    )


def build_clustered_event_merge_task(
    *,
    project_root: Path,
    run_id: str,
    input_path: str | None,
    config: str | None = None,
    depends_on: list[str] | None = None,
) -> TaskEvent:
    return build_registered_classify_task(
        get_registered_classify_task("classify.clustered_event_merge"),
        project_root=project_root,
        run_id=run_id,
        input_path=input_path,
        config=config,
        depends_on=depends_on,
    )
