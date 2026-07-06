from __future__ import annotations

from dataclasses import dataclass

from modnews.core.task import TaskEvent


@dataclass(frozen=True, slots=True)
class RegisteredTaskSummary:
    id: str
    builder_id: str
    task_type: str | None = None
    task_prefix: str | None = None

    def matches(self, task: TaskEvent) -> bool:
        if self.task_type is not None:
            return task.type == self.task_type
        if self.task_prefix is not None:
            return task.type.startswith(self.task_prefix)
        return False


REGISTERED_TASK_SUMMARIES: tuple[RegisteredTaskSummary, ...] = (
    RegisteredTaskSummary(
        id="report.generate",
        task_type="report.generate",
        builder_id="report",
    ),
    RegisteredTaskSummary(
        id="web_source.run",
        task_type="web_source.run",
        builder_id="web_source",
    ),
)

REGISTERED_TASK_SUMMARY_BY_ID: dict[str, RegisteredTaskSummary] = {
    item.id: item
    for item in REGISTERED_TASK_SUMMARIES
}


def get_registered_task_summary(summary_id: str) -> RegisteredTaskSummary:
    return REGISTERED_TASK_SUMMARY_BY_ID[summary_id]


def resolve_task_summary(task: TaskEvent) -> RegisteredTaskSummary | None:
    for item in REGISTERED_TASK_SUMMARIES:
        if item.matches(task):
            return item
    return None
