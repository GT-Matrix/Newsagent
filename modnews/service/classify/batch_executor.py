from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Generic, Protocol, TypeVar

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class BatchExecutionMetadata:
    task_type: str
    concurrency_key: str
    max_concurrency: int
    item_index: int
    item_count: int
    batch_index: int | None = None
    batch_count: int | None = None
    labels: dict[str, str] = field(default_factory=dict)

    def task_name(self) -> str:
        if self.batch_index is not None and self.batch_count is not None:
            return f"{self.task_type}[{self.batch_index}/{self.batch_count}]"
        return f"{self.task_type}[{self.item_index + 1}/{self.item_count}]"


@dataclass(frozen=True, slots=True)
class BatchExecutionItem(Generic[T]):
    payload: T
    metadata: BatchExecutionMetadata


class BatchExecutionBackend(Protocol):
    def run(self, fn: Callable[[T], R], items: list[BatchExecutionItem[T]]) -> list[R]:
        ...


class ThreadedBatchExecutionBackend:
    def run(self, fn: Callable[[T], R], items: list[BatchExecutionItem[T]]) -> list[R]:
        if not items:
            return []
        workers = max(1, min(item.metadata.max_concurrency for item in items))
        if workers == 1:
            return [fn(item.payload) for item in items]

        results: dict[int, R] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fn, item.payload): index for index, item in enumerate(items)}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        return [results[index] for index in range(len(items))]


def build_batch_items(
    items: list[T],
    *,
    task_type: str,
    concurrency_key: str,
    max_concurrency: int,
    batch_indexes: list[int | None] | None = None,
    batch_count: int | None = None,
    labels: dict[str, str] | None = None,
) -> list[BatchExecutionItem[T]]:
    item_count = len(items)
    result: list[BatchExecutionItem[T]] = []
    for index, payload in enumerate(items):
        batch_index = batch_indexes[index] if batch_indexes is not None else None
        result.append(
            BatchExecutionItem(
                payload=payload,
                metadata=BatchExecutionMetadata(
                    task_type=task_type,
                    concurrency_key=concurrency_key,
                    max_concurrency=max(1, max_concurrency),
                    item_index=index,
                    item_count=item_count,
                    batch_index=batch_index,
                    batch_count=batch_count if batch_index is not None else None,
                    labels=labels or {},
                ),
            )
        )
    return result


def run_batch_parallel(
    fn: Callable[[T], R],
    items: list[T] | list[BatchExecutionItem[T]],
    *,
    max_workers: int,
    task_type: str = "classify.batch",
    concurrency_key: str | None = None,
    batch_indexes: list[int | None] | None = None,
    batch_count: int | None = None,
    labels: dict[str, str] | None = None,
    backend: BatchExecutionBackend | None = None,
) -> list[R]:
    execution_items = _coerce_items(
        items,
        task_type=task_type,
        concurrency_key=concurrency_key or task_type,
        max_concurrency=max_workers,
        batch_indexes=batch_indexes,
        batch_count=batch_count,
        labels=labels,
    )
    return (backend or ThreadedBatchExecutionBackend()).run(fn, execution_items)


def _coerce_items(
    items: list[T] | list[BatchExecutionItem[T]],
    *,
    task_type: str,
    concurrency_key: str,
    max_concurrency: int,
    batch_indexes: list[int | None] | None,
    batch_count: int | None,
    labels: dict[str, str] | None,
) -> list[BatchExecutionItem[T]]:
    if not items:
        return []
    first = items[0]
    if isinstance(first, BatchExecutionItem):
        return items  # type: ignore[return-value]
    return build_batch_items(
        items,  # type: ignore[arg-type]
        task_type=task_type,
        concurrency_key=concurrency_key,
        max_concurrency=max_concurrency,
        batch_indexes=batch_indexes,
        batch_count=batch_count,
        labels=labels,
    )


def describe_batch_items(items: list[BatchExecutionItem[object]]) -> list[dict[str, object]]:
    return [
        {
            "task_type": item.metadata.task_type,
            "task_name": item.metadata.task_name(),
            "concurrency_key": item.metadata.concurrency_key,
            "max_concurrency": item.metadata.max_concurrency,
            "item_index": item.metadata.item_index,
            "item_count": item.metadata.item_count,
            "batch_index": item.metadata.batch_index,
            "batch_count": item.metadata.batch_count,
            "labels": item.metadata.labels,
        }
        for item in items
    ]
