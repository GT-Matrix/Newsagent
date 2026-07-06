from __future__ import annotations

from dataclasses import dataclass

from modnews.core.task import TaskEvent


@dataclass(frozen=True, slots=True)
class RegisteredTaskDomainView:
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


REGISTERED_TASK_DOMAIN_VIEWS: tuple[RegisteredTaskDomainView, ...] = (
    RegisteredTaskDomainView(
        id="web_source.run",
        task_type="web_source.run",
        builder_id="web_source",
    ),
    RegisteredTaskDomainView(
        id="extractor.repair.codex",
        task_type="extractor.repair.codex",
        builder_id="repair_codex",
    ),
    RegisteredTaskDomainView(
        id="classify.task",
        task_prefix="classify.",
        builder_id="classify",
    ),
    RegisteredTaskDomainView(
        id="report.generate",
        task_type="report.generate",
        builder_id="report",
    ),
    RegisteredTaskDomainView(
        id="pipeline.combine_ingest",
        task_type="pipeline.combine_ingest",
        builder_id="pipeline_combine_ingest",
    ),
    RegisteredTaskDomainView(
        id="ingest.task",
        task_prefix="ingest.",
        builder_id="ingest",
    ),
)

REGISTERED_TASK_DOMAIN_VIEW_BY_ID: dict[str, RegisteredTaskDomainView] = {
    item.id: item
    for item in REGISTERED_TASK_DOMAIN_VIEWS
}


def get_registered_task_domain_view(view_id: str) -> RegisteredTaskDomainView:
    return REGISTERED_TASK_DOMAIN_VIEW_BY_ID[view_id]


def resolve_task_domain_view(task: TaskEvent) -> RegisteredTaskDomainView | None:
    for view in REGISTERED_TASK_DOMAIN_VIEWS:
        if view.matches(task):
            return view
    return None
