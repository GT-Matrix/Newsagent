from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, TypeVar

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent

from .batch_queue_runtime import ClassifyBatchQueueRuntime
from .batch_items import BatchExecutionItem, describe_batch_items

T = TypeVar("T")
R = TypeVar("R")


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


@dataclass(slots=True)
class EventQueueBatchExecutionBackend:
    queue: EventQueue
    run_id: str | None = None
    step_id: str | None = None
    base_payload: dict[str, Any] = field(default_factory=dict)
    base_task: TaskEvent | None = None
    auto_drain: bool = True

    def run(self, fn: Callable[[T], R], items: list[BatchExecutionItem[T]]) -> list[R]:
        del fn
        runtime = ClassifyBatchQueueRuntime(
            queue=self.queue,
            run_id=self.run_id,
            step_id=self.step_id,
            base_payload=self.base_payload,
            base_task=self.base_task,
            auto_drain=self.auto_drain,
        )
        return runtime.submit_and_collect(items)  # type: ignore[return-value]
