from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from modnews.core.config import load_config
from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository

from .task_builder import (
    build_classify_extraction_task,
    build_classify_merge_task,
    build_combine_ingest_task_for_run,
    build_report_generate_task,
)

FollowupBuilder = Callable[[EventQueue, dict[str, object], dict[str, object]], TaskEvent | None]


@dataclass(frozen=True, slots=True)
class FollowupRule:
    trigger: str
    builder_id: str
    task_type: str | None = None
    step_prefix: str | None = None

    def matches(self, task: dict[str, object]) -> bool:
        current_task_type = str(task.get("type") or "")
        current_step_id = str(task.get("step_id") or "")
        if self.task_type is not None and current_task_type != self.task_type:
            return False
        if self.step_prefix is not None and not current_step_id.startswith(self.step_prefix):
            return False
        return True


@dataclass(frozen=True, slots=True)
class RegisteredFollowupBuilder:
    builder_id: str
    build: FollowupBuilder


def register_followup_for_event(
    queue: EventQueue | None,
    event: dict[str, object],
    rules: tuple[FollowupRule, ...],
) -> list[dict[str, object]]:
    task = event_task(event)
    if queue is None or not task:
        return []
    for rule in rules:
        if not rule.matches(task):
            continue
        builder = get_registered_followup_builder(rule.builder_id)
        followup = builder.build(queue, event, task)
        if followup is None:
            return []
        return register_task(queue, followup, trigger=rule.trigger)
    return []


def register_task(queue: EventQueue, task: TaskEvent, *, trigger: str) -> list[dict[str, object]]:
    if any(existing.id == task.id for existing in queue.list()):
        return []
    queue.register(task)
    return [
        {
            "action": "register_task",
            "trigger": trigger,
            "task_id": task.id,
            "task_type": task.type,
            "step_id": task.step_id,
            "depends_on": list(task.depends_on),
        }
    ]


def event_task(event: dict[str, object]) -> dict[str, object]:
    value = event.get("task")
    return value if isinstance(value, dict) else {}


def event_run_id(task: dict[str, object]) -> str:
    return str(task.get("pipeline_run_id") or "")


def event_project_root(task: dict[str, object]) -> str:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    return str(payload.get("project_root") or "")


def event_config_path(task: dict[str, object]) -> str | None:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    value = payload.get("config")
    if value is None:
        return None
    return str(value)


def classification_enabled(config_path: str | None) -> bool:
    if not config_path:
        return True
    return bool(load_config(config_path).classification.enabled)


def report_enabled_for_run(project_root: str, run_id: str) -> bool:
    if not project_root or not run_id:
        return False
    record = RunRepository(Path(project_root)).get(run_id)
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return True
    if bool(payload.get("disable_report")):
        return False
    if bool(payload.get("disable_classification")):
        return False
    return True


def build_combine_ingest_followup(
    queue: EventQueue,
    _event: dict[str, object],
    task: dict[str, object],
) -> TaskEvent | None:
    run_id = event_run_id(task)
    project_root = event_project_root(task)
    if not run_id or not project_root:
        return None
    ingest_task_ids = sorted(
        queued.id
        for queued in queue.list()
        if queued.pipeline_run_id == run_id and queued.step_id and queued.step_id.startswith("ingest/")
    )
    if not ingest_task_ids:
        return None
    return build_combine_ingest_task_for_run(
        run_id=run_id,
        project_root=project_root,
        ingest_task_ids=ingest_task_ids,
    )[0]


def build_classify_extraction_followup(
    _queue: EventQueue,
    _event: dict[str, object],
    task: dict[str, object],
) -> TaskEvent | None:
    run_id = event_run_id(task)
    project_root = event_project_root(task)
    if not run_id or not project_root:
        return None
    config_path = event_config_path(task)
    if not classification_enabled(config_path):
        return None
    return build_classify_extraction_task(
        run_id=run_id,
        project_root=project_root,
        config_path=config_path,
        depends_on=[str(task["id"])],
    )


def build_classify_merge_followup(
    _queue: EventQueue,
    _event: dict[str, object],
    task: dict[str, object],
) -> TaskEvent | None:
    run_id = event_run_id(task)
    project_root = event_project_root(task)
    if not run_id or not project_root:
        return None
    config_path = event_config_path(task)
    if not classification_enabled(config_path):
        return None
    return build_classify_merge_task(
        run_id=run_id,
        project_root=project_root,
        config_path=config_path,
        depends_on=[str(task["id"])],
    )


def build_report_followup(
    _queue: EventQueue,
    _event: dict[str, object],
    task: dict[str, object],
) -> TaskEvent | None:
    run_id = event_run_id(task)
    project_root = event_project_root(task)
    if not run_id or not project_root:
        return None
    config_path = event_config_path(task)
    if not classification_enabled(config_path):
        return None
    if not report_enabled_for_run(project_root, run_id):
        return None
    return build_report_generate_task(
        run_id=run_id,
        project_root=project_root,
        config_path=config_path,
        depends_on=[str(task["id"])],
    )


REGISTERED_FOLLOWUP_BUILDERS: tuple[RegisteredFollowupBuilder, ...] = (
    RegisteredFollowupBuilder(
        builder_id="combine_ingest_for_run",
        build=build_combine_ingest_followup,
    ),
    RegisteredFollowupBuilder(
        builder_id="classify_extraction_after_combine",
        build=build_classify_extraction_followup,
    ),
    RegisteredFollowupBuilder(
        builder_id="classify_merge_after_extraction",
        build=build_classify_merge_followup,
    ),
    RegisteredFollowupBuilder(
        builder_id="report_after_classify_merge",
        build=build_report_followup,
    ),
)

REGISTERED_FOLLOWUP_BUILDER_BY_ID: dict[str, RegisteredFollowupBuilder] = {
    builder.builder_id: builder
    for builder in REGISTERED_FOLLOWUP_BUILDERS
}

FOLLOWUP_BUILDERS: dict[str, FollowupBuilder] = {
    builder.builder_id: builder.build
    for builder in REGISTERED_FOLLOWUP_BUILDERS
}


def get_registered_followup_builder(builder_id: str) -> RegisteredFollowupBuilder:
    return REGISTERED_FOLLOWUP_BUILDER_BY_ID[builder_id]
