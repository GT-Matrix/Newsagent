from __future__ import annotations

import unittest
from typing import Callable, TypeVar

from modnews.core.event_queue import EventQueue
from modnews.service.classify.batch_executor import (
    BatchExecutionItem,
    EventQueueBatchExecutionBackend,
    build_batch_items,
    default_batch_backend,
    describe_batch_items,
    run_batch_parallel,
)

T = TypeVar("T")
R = TypeVar("R")


class RecordingBackend:
    def __init__(self) -> None:
        self.seen: list[BatchExecutionItem[object]] = []

    def run(self, fn: Callable[[T], R], items: list[BatchExecutionItem[T]]) -> list[R]:
        self.seen = list(items)  # type: ignore[list-item]
        return [fn(item.payload) for item in items]


class BatchExecutorTest(unittest.TestCase):
    def test_preserves_input_order_with_threaded_backend(self) -> None:
        result = run_batch_parallel(
            lambda value: value * 2,
            [3, 1, 2],
            max_workers=2,
            task_type="classify.test",
            concurrency_key="classify.test",
        )

        self.assertEqual(result, [6, 2, 4])

    def test_passes_metadata_to_backend(self) -> None:
        backend = RecordingBackend()

        result = run_batch_parallel(
            lambda value: value + 1,
            [10, 20],
            max_workers=4,
            task_type="classify.batch_relevance",
            concurrency_key="classify.llm",
            batch_indexes=[1, 2],
            batch_count=2,
            labels={"stage": "relevance"},
            backend=backend,
        )

        self.assertEqual(result, [11, 21])
        self.assertEqual([item.metadata.task_name() for item in backend.seen], [
            "classify.batch_relevance[1/2]",
            "classify.batch_relevance[2/2]",
        ])
        self.assertEqual(backend.seen[0].metadata.concurrency_key, "classify.llm")
        self.assertEqual(backend.seen[0].metadata.max_concurrency, 4)
        self.assertEqual(backend.seen[0].metadata.labels, {"stage": "relevance"})

    def test_describes_batch_items_for_task_backends(self) -> None:
        items = build_batch_items(
            ["a"],
            task_type="classify.embedding",
            concurrency_key="classify.embedding",
            max_concurrency=3,
            labels={"stage": "clustered"},
        )

        self.assertEqual(
            describe_batch_items(items),
            [
                {
                    "task_type": "classify.embedding",
                    "task_name": "classify.embedding[1/1]",
                    "concurrency_key": "classify.embedding",
                    "max_concurrency": 3,
                    "item_index": 0,
                    "item_count": 1,
                    "batch_index": None,
                    "batch_count": None,
                    "labels": {"stage": "clustered"},
                }
            ],
        )

    def test_event_queue_backend_registers_batch_tasks(self) -> None:
        queue = EventQueue()
        backend = EventQueueBatchExecutionBackend(queue, run_id="run-1", step_id="classify/relevance")

        result = run_batch_parallel(
            lambda value: value.upper(),
            ["a", "b"],
            max_workers=2,
            task_type="classify.batch_relevance",
            concurrency_key="classify.llm",
            batch_indexes=[1, 2],
            batch_count=2,
            labels={"stage": "relevance"},
            backend=backend,
        )

        self.assertEqual(result, ["A", "B"])
        tasks = queue.list()
        self.assertEqual(len(tasks), 2)
        self.assertEqual([task.state for task in tasks], ["succeeded", "succeeded"])
        self.assertEqual({task.concurrency_key for task in tasks}, {"classify.llm"})
        self.assertEqual({task.max_concurrency for task in tasks}, {2})
        self.assertEqual([queue.result(task.id)["batch_result"] for task in tasks], ["A", "B"])
        self.assertEqual(queue._executors, {})

    def test_default_backend_context_routes_batches_to_event_queue(self) -> None:
        queue = EventQueue()
        backend = EventQueueBatchExecutionBackend(queue, run_id="run-1", step_id="classify/default")

        with default_batch_backend(backend):
            result = run_batch_parallel(
                lambda value: value + 10,
                [1, 2],
                max_workers=2,
                task_type="classify.embedding",
                concurrency_key="classify.embedding",
            )

        self.assertEqual(result, [11, 12])
        self.assertEqual(len(queue.list()), 2)
        self.assertEqual({task.type.rsplit(".", 1)[0] for task in queue.list()}, {"classify.batch_item"})


if __name__ == "__main__":
    unittest.main()
