from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

from .batch_executor import run_batch_parallel

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class BatchTaskProfile:
    task_type: str
    concurrency_key: str
    queue_task_type: str | None = None
    labels: dict[str, str] = field(default_factory=dict)


CLUSTERED_EMBEDDING_BATCH = BatchTaskProfile(
    task_type="classify.embedding",
    concurrency_key="classify.embedding",
    queue_task_type="classify.embedding",
    labels={"stage": "clustered"},
)

CLUSTERED_EVENT_EXTRACTION_BATCH = BatchTaskProfile(
    task_type="classify.clustered_event_extraction.batch",
    concurrency_key="classify.llm",
    labels={"stage": "clustered_event_extraction"},
)

CLUSTERED_EVENT_MERGE_BATCH = BatchTaskProfile(
    task_type="classify.clustered_event_merge.batch",
    concurrency_key="classify.llm",
    labels={"stage": "clustered_event_merge"},
)

RELEVANCE_BATCH = BatchTaskProfile(
    task_type="classify.batch_relevance",
    concurrency_key="classify.llm",
    queue_task_type="classify.batch_relevance",
    labels={"stage": "relevance"},
)


def run_profiled_batch(
    fn,
    items: list[T],
    *,
    profile: BatchTaskProfile,
    max_workers: int,
    batch_indexes: list[int | None] | None = None,
    batch_count: int | None = None,
    backend=None,
) -> list[R]:
    return run_batch_parallel(
        fn,
        items,
        max_workers=max_workers,
        task_type=profile.task_type,
        concurrency_key=profile.concurrency_key,
        queue_task_type=profile.queue_task_type,
        batch_indexes=batch_indexes,
        batch_count=batch_count,
        labels=profile.labels,
        backend=backend,
    )
