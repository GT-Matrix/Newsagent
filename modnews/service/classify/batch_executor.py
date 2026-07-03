from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Protocol, TypeVar
from uuid import uuid4

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent

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


class EventQueueBatchExecutionBackend:
    def __init__(
        self,
        queue: EventQueue,
        *,
        run_id: str | None = None,
        step_id: str | None = None,
        task_type_prefix: str = "classify.batch_item",
        auto_drain: bool = True,
    ) -> None:
        self.queue = queue
        self.run_id = run_id
        self.step_id = step_id
        self.task_type_prefix = task_type_prefix
        self.auto_drain = auto_drain

    def run(self, fn: Callable[[T], R], items: list[BatchExecutionItem[T]]) -> list[R]:
        if not items:
            return []

        task_type = f"{self.task_type_prefix}.{uuid4().hex}"
        payloads = {self._task_id(task_type, item): item.payload for item in items}

        def execute(task: TaskEvent) -> dict[str, Any]:
            item_payload = payloads[task.id]
            return {"batch_result": fn(item_payload)}

        self.queue.register_executor(task_type, execute)
        try:
            task_ids: list[str] = []
            for item in items:
                task = self._task_for_item(task_type, item)
                task_ids.append(task.id)
                self.queue.register(task)

            if self.auto_drain:
                self.queue.drain_ready()

            results: list[R] = []
            for task_id in task_ids:
                task = self.queue.get(task_id)
                if task.state != "succeeded":
                    result = self.queue.result(task_id)
                    reason = result.get("error") or result.get("blocked_reason") or f"task ended as {task.state}"
                    raise RuntimeError(f"batch task {task_id} did not succeed: {reason}")
                result = self.queue.result(task_id)
                results.append(result["batch_result"])
            return results
        finally:
            self.queue.unregister_executor(task_type)

    def _task_id(self, task_type: str, item: BatchExecutionItem[object]) -> str:
        metadata = item.metadata
        index = metadata.batch_index if metadata.batch_index is not None else metadata.item_index + 1
        return f"{task_type}:{index}"

    def _task_for_item(self, task_type: str, item: BatchExecutionItem[object]) -> TaskEvent:
        metadata = item.metadata
        return TaskEvent(
            id=self._task_id(task_type, item),
            type=task_type,
            pipeline_run_id=self.run_id,
            step_id=self.step_id or metadata.labels.get("stage") or metadata.task_type,
            payload={
                "batch": describe_batch_items([item])[0],
                "labels": metadata.labels,
            },
            concurrency_key=metadata.concurrency_key,
            max_concurrency=metadata.max_concurrency,
            checkpoint_policy="none",
        )


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
