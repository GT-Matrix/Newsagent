from __future__ import annotations

from dataclasses import dataclass

from modnews.core.task import TaskEvent


@dataclass(frozen=True, slots=True)
class RegisteredTaskReadModelMeta:
    id: str
    task_type: str | None = None
    task_prefix: str | None = None
    publish_targets: tuple[tuple[str, str], ...] = ()
    classify_task_kind: str | None = None

    def matches(self, task: TaskEvent) -> bool:
        if self.task_type is not None:
            return task.type == self.task_type
        if self.task_prefix is not None:
            return task.type.startswith(self.task_prefix)
        return False


REGISTERED_TASK_READ_MODEL_META: tuple[RegisteredTaskReadModelMeta, ...] = (
    RegisteredTaskReadModelMeta(
        id="classify.embedding",
        task_type="classify.embedding",
        classify_task_kind="embedding_batch",
        publish_targets=(
            ("news_with_events", "news_with_events"),
            ("events", "events"),
            ("discarded_news", "discarded_news"),
            ("classification_progress", "checkpoint"),
        ),
    ),
    RegisteredTaskReadModelMeta(
        id="classify.batch_relevance",
        task_type="classify.batch_relevance",
        classify_task_kind="relevance_batch",
        publish_targets=(
            ("news_with_events", "news_with_events"),
            ("events", "events"),
            ("discarded_news", "discarded_news"),
            ("classification_progress", "checkpoint"),
        ),
    ),
    RegisteredTaskReadModelMeta(
        id="classify.clustered_event_extraction.batch",
        task_type="classify.clustered_event_extraction.batch",
        classify_task_kind="clustered_event_extraction_batch",
        publish_targets=(
            ("news_with_events", "news_with_events"),
            ("events", "events"),
            ("discarded_news", "discarded_news"),
            ("classification_progress", "checkpoint"),
        ),
    ),
    RegisteredTaskReadModelMeta(
        id="classify.clustered_event_merge.batch",
        task_type="classify.clustered_event_merge.batch",
        classify_task_kind="clustered_event_merge_batch",
        publish_targets=(
            ("news_with_events", "news_with_events"),
            ("events", "events"),
            ("discarded_news", "discarded_news"),
            ("classification_progress", "checkpoint"),
        ),
    ),
    RegisteredTaskReadModelMeta(
        id="classify.clustered_event_extraction",
        task_type="classify.clustered_event_extraction",
        classify_task_kind="clustered_event_extraction",
        publish_targets=(
            ("news_with_events", "news_with_events"),
            ("events", "events"),
            ("discarded_news", "discarded_news"),
            ("classification_progress", "checkpoint"),
        ),
    ),
    RegisteredTaskReadModelMeta(
        id="classify.clustered_event_merge",
        task_type="classify.clustered_event_merge",
        classify_task_kind="clustered_event_merge",
        publish_targets=(
            ("news_with_events", "news_with_events"),
            ("events", "events"),
            ("discarded_news", "discarded_news"),
            ("classification_progress", "checkpoint"),
        ),
    ),
    RegisteredTaskReadModelMeta(
        id="classify.task",
        task_prefix="classify.",
        classify_task_kind="classify_task",
        publish_targets=(
            ("news_with_events", "news_with_events"),
            ("events", "events"),
            ("discarded_news", "discarded_news"),
            ("classification_progress", "checkpoint"),
        ),
    ),
    RegisteredTaskReadModelMeta(
        id="report.generate",
        task_type="report.generate",
        publish_targets=(
            ("report_markdown", "report_markdown"),
            ("report_debug_markdown", "report_debug_markdown"),
            ("report_events", "report_events"),
            ("report_trend_summary", "report_trend_summary"),
        ),
    ),
    RegisteredTaskReadModelMeta(
        id="pipeline.combine_ingest",
        task_type="pipeline.combine_ingest",
        publish_targets=(("items", "combined_news"),),
    ),
)

REGISTERED_TASK_READ_MODEL_META_BY_ID: dict[str, RegisteredTaskReadModelMeta] = {
    item.id: item
    for item in REGISTERED_TASK_READ_MODEL_META
}


def get_registered_task_read_model_meta(meta_id: str) -> RegisteredTaskReadModelMeta:
    return REGISTERED_TASK_READ_MODEL_META_BY_ID[meta_id]


def resolve_task_read_model_meta(task: TaskEvent) -> RegisteredTaskReadModelMeta | None:
    for item in REGISTERED_TASK_READ_MODEL_META:
        if item.matches(task):
            return item
    return None
