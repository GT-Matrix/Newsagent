from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from modnews.core.task import TaskEvent

TaskTitleBuilder = Callable[[TaskEvent], str]


@dataclass(frozen=True, slots=True)
class RegisteredTaskPresentation:
    id: str
    log_kind: str
    detail_kind: str
    title_builder: TaskTitleBuilder
    task_type: str | None = None
    task_prefix: str | None = None

    def matches(self, task: TaskEvent) -> bool:
        if self.task_type is not None:
            return task.type == self.task_type
        if self.task_prefix is not None:
            return task.type.startswith(self.task_prefix)
        return False


def _task_type_title(prefix: str) -> TaskTitleBuilder:
    def build(task: TaskEvent) -> str:
        return f"Run {prefix} task {task.type.removeprefix(prefix + '.')}"

    return build


def _pipeline_combine_title(_task: TaskEvent) -> str:
    return "Combine ingest outputs"


def _report_title(_task: TaskEvent) -> str:
    return "Generate report"


def _web_source_title(task: TaskEvent) -> str:
    source_id = str(task.payload.get("source_id") or "")
    return f"Run web source {source_id}" if source_id else "Run web source"


def _repair_title(task: TaskEvent) -> str:
    source_id = str(task.payload.get("source_id") or "")
    return f"Run extractor repair {source_id}" if source_id else "Run extractor repair"


def _clustered_extraction_title(_task: TaskEvent) -> str:
    return "Classify clustered event extraction"


def _clustered_merge_title(_task: TaskEvent) -> str:
    return "Classify clustered event merge"


def _embedding_title(task: TaskEvent) -> str:
    return _batch_title("Classify embedding batch", task)


def _relevance_title(task: TaskEvent) -> str:
    return _batch_title("Classify relevance batch", task)


def _classify_batch_title(task: TaskEvent) -> str:
    return _batch_title(task.type, task)


REGISTERED_TASK_PRESENTATIONS: tuple[RegisteredTaskPresentation, ...] = (
    RegisteredTaskPresentation(
        id="pipeline.combine_ingest",
        task_type="pipeline.combine_ingest",
        log_kind="task",
        detail_kind="ingest_task",
        title_builder=_pipeline_combine_title,
    ),
    RegisteredTaskPresentation(
        id="report.generate",
        task_type="report.generate",
        log_kind="report",
        detail_kind="report_task",
        title_builder=_report_title,
    ),
    RegisteredTaskPresentation(
        id="web_source.run",
        task_type="web_source.run",
        log_kind="web_job",
        detail_kind="web_source_task",
        title_builder=_web_source_title,
    ),
    RegisteredTaskPresentation(
        id="extractor.repair.codex",
        task_type="extractor.repair.codex",
        log_kind="codex",
        detail_kind="repair_task",
        title_builder=_repair_title,
    ),
    RegisteredTaskPresentation(
        id="classify.clustered_event_extraction",
        task_type="classify.clustered_event_extraction",
        log_kind="classify",
        detail_kind="classify_task",
        title_builder=_clustered_extraction_title,
    ),
    RegisteredTaskPresentation(
        id="classify.clustered_event_merge",
        task_type="classify.clustered_event_merge",
        log_kind="classify",
        detail_kind="classify_task",
        title_builder=_clustered_merge_title,
    ),
    RegisteredTaskPresentation(
        id="classify.embedding",
        task_type="classify.embedding",
        log_kind="classify",
        detail_kind="classify_task",
        title_builder=_embedding_title,
    ),
    RegisteredTaskPresentation(
        id="classify.batch_relevance",
        task_type="classify.batch_relevance",
        log_kind="classify",
        detail_kind="classify_task",
        title_builder=_relevance_title,
    ),
    RegisteredTaskPresentation(
        id="classify.clustered_event_extraction.batch",
        task_type="classify.clustered_event_extraction.batch",
        log_kind="classify",
        detail_kind="classify_task",
        title_builder=_classify_batch_title,
    ),
    RegisteredTaskPresentation(
        id="classify.clustered_event_merge.batch",
        task_type="classify.clustered_event_merge.batch",
        log_kind="classify",
        detail_kind="classify_task",
        title_builder=_classify_batch_title,
    ),
    RegisteredTaskPresentation(
        id="classify.batch",
        task_prefix="classify.",
        log_kind="classify",
        detail_kind="classify_task",
        title_builder=_task_type_title("classify"),
    ),
    RegisteredTaskPresentation(
        id="ingest.task",
        task_prefix="ingest.",
        log_kind="task",
        detail_kind="ingest_task",
        title_builder=_task_type_title("ingest"),
    ),
)

REGISTERED_TASK_PRESENTATION_BY_ID: dict[str, RegisteredTaskPresentation] = {
    item.id: item
    for item in REGISTERED_TASK_PRESENTATIONS
}


def get_registered_task_presentation(presentation_id: str) -> RegisteredTaskPresentation:
    return REGISTERED_TASK_PRESENTATION_BY_ID[presentation_id]


def resolve_task_presentation(task: TaskEvent) -> RegisteredTaskPresentation | None:
    for presentation in REGISTERED_TASK_PRESENTATIONS:
        if presentation.matches(task):
            return presentation
    return None


def default_task_title(task: TaskEvent) -> str:
    return task.type


def _batch_title(base: str, task: TaskEvent) -> str:
    batch = task.payload.get("batch")
    if isinstance(batch, dict):
        batch_index = batch.get("batch_index")
        batch_count = batch.get("batch_count")
        if isinstance(batch_index, int) and isinstance(batch_count, int):
            return f"{base} [{batch_index}/{batch_count}]"
    return base
