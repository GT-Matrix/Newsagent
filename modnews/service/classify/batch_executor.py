from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator, TypeVar

from .batch_backends import BatchExecutionBackend, EventQueueBatchExecutionBackend, ThreadedBatchExecutionBackend
from .batch_items import (
    BatchExecutionItem,
    BatchExecutionMetadata,
    build_batch_items,
    coerce_batch_items,
    describe_batch_items,
)

T = TypeVar("T")
R = TypeVar("R")

_DEFAULT_BACKEND: ContextVar[BatchExecutionBackend | None] = ContextVar("classify_batch_backend", default=None)


def run_batch_parallel(
    fn: Callable[[T], R],
    items: list[T] | list[BatchExecutionItem[T]],
    *,
    max_workers: int,
    task_type: str = "classify.batch",
    concurrency_key: str | None = None,
    queue_task_type: str | None = None,
    batch_indexes: list[int | None] | None = None,
    batch_count: int | None = None,
    labels: dict[str, str] | None = None,
    backend: BatchExecutionBackend | None = None,
) -> list[R]:
    execution_items = coerce_batch_items(
        items,
        task_type=task_type,
        concurrency_key=concurrency_key or task_type,
        max_concurrency=max_workers,
        queue_task_type=queue_task_type,
        batch_indexes=batch_indexes,
        batch_count=batch_count,
        labels=labels,
    )
    return (backend or _DEFAULT_BACKEND.get() or ThreadedBatchExecutionBackend()).run(fn, execution_items)


@contextmanager
def default_batch_backend(backend: BatchExecutionBackend | None) -> Iterator[None]:
    token = _DEFAULT_BACKEND.set(backend)
    try:
        yield
    finally:
        _DEFAULT_BACKEND.reset(token)
