from __future__ import annotations

import unittest
from typing import Callable, TypeVar

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.classify.batch_executor import (
    BatchExecutionItem,
    EventQueueBatchExecutionBackend,
    build_batch_items,
    default_batch_backend,
    describe_batch_items,
    run_batch_parallel,
)
from modnews.service.classify.batch_profile import (
    CLUSTERED_EMBEDDING_BATCH,
    CLUSTERED_EVENT_EXTRACTION_BATCH,
    CLUSTERED_EVENT_MERGE_BATCH,
    RELEVANCE_BATCH,
    run_profiled_batch,
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
                    "queue_task_type": None,
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

        with self.assertRaisesRegex(RuntimeError, "explicit queue_task_type"):
            run_batch_parallel(
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

    def test_event_queue_backend_uses_fixed_queue_task_type_when_present(self) -> None:
        queue = EventQueue()
        backend = EventQueueBatchExecutionBackend(
            queue,
            run_id="run-1",
            step_id="classify/embedding",
            base_payload={"project_root": "/tmp/project", "config": "/tmp/project/config.json"},
        )
        queue.register_executor("classify.embedding", lambda task: {"batch_result": {"key": "x", "vector": [1.0]}})

        result = run_profiled_batch(
            lambda value: {"key": value["key"], "vector": [2.0]},
            [{"key": "x", "text": "hello"}],
            profile=type("Profile", (), {
                "task_type": "classify.embedding",
                "concurrency_key": "classify.embedding",
                "queue_task_type": "classify.embedding",
                "labels": {"stage": "clustered"},
            })(),
            max_workers=1,
            backend=backend,
        )

        self.assertEqual(result, [{"key": "x", "vector": [1.0]}])
        task = queue.list()[0]
        self.assertEqual(task.type, "classify.embedding")
        self.assertEqual(task.payload["project_root"], "/tmp/project")
        self.assertEqual(task.payload["item_payload"], {"key": "x", "text": "hello"})

    def test_event_queue_backend_supports_fixed_relevance_queue_task_type(self) -> None:
        queue = EventQueue()
        backend = EventQueueBatchExecutionBackend(
            queue,
            run_id="run-1",
            step_id="classify/relevance",
            base_payload={"project_root": "/tmp/project", "config": "/tmp/project/config.json"},
        )
        queue.register_executor("classify.batch_relevance", lambda task: {"batch_result": {"items": task.payload["item_payload"]}})

        result = run_profiled_batch(
            lambda value: {"items": [{"index": 0, "status": "candidate"}]},
            [[{"index": 0, "title": "hello", "platform": "x", "pubtime": None, "url_domain": "example.com"}]],
            profile=RELEVANCE_BATCH,
            max_workers=1,
            backend=backend,
        )

        self.assertEqual(result, [{"items": [{"index": 0, "title": "hello", "platform": "x", "pubtime": None, "url_domain": "example.com"}]}])
        task = queue.list()[0]
        self.assertEqual(task.type, "classify.batch_relevance")

    def test_event_queue_backend_supports_fixed_clustered_extraction_queue_task_type(self) -> None:
        queue = EventQueue()
        backend = EventQueueBatchExecutionBackend(
            queue,
            run_id="run-1",
            step_id="classify/clustered_event_extraction",
            base_payload={"project_root": "/tmp/project", "config": "/tmp/project/config.json"},
        )
        queue.register_executor(
            "classify.clustered_event_extraction.batch",
            lambda task: {"batch_result": {"items": task.payload["item_payload"]}},
        )

        result = run_profiled_batch(
            lambda value: {"events": []},
            [[{"index": 0, "title": "hello", "platform": "x", "pubtime": None, "url_domain": "example.com"}]],
            profile=CLUSTERED_EVENT_EXTRACTION_BATCH,
            max_workers=1,
            backend=backend,
        )

        self.assertEqual(result, [{"items": [{"index": 0, "title": "hello", "platform": "x", "pubtime": None, "url_domain": "example.com"}]}])
        task = queue.list()[0]
        self.assertEqual(task.type, "classify.clustered_event_extraction.batch")

    def test_event_queue_backend_supports_fixed_clustered_merge_queue_task_type(self) -> None:
        queue = EventQueue()
        backend = EventQueueBatchExecutionBackend(
            queue,
            run_id="run-1",
            step_id="classify/clustered_event_merge",
            base_payload={"project_root": "/tmp/project", "config": "/tmp/project/config.json"},
        )
        queue.register_executor(
            "classify.clustered_event_merge.batch",
            lambda task: {"batch_result": {"events": task.payload["item_payload"]}},
        )

        result = run_profiled_batch(
            lambda value: {"merge_groups": []},
            [[{"event_id": "evt_1", "event_label": "hello"}]],
            profile=CLUSTERED_EVENT_MERGE_BATCH,
            max_workers=1,
            backend=backend,
        )

        self.assertEqual(result, [{"events": [{"event_id": "evt_1", "event_label": "hello"}]}])
        task = queue.list()[0]
        self.assertEqual(task.type, "classify.clustered_event_merge.batch")

    def test_default_backend_context_routes_batches_to_event_queue(self) -> None:
        queue = EventQueue()
        backend = EventQueueBatchExecutionBackend(queue, run_id="run-1", step_id="classify/default")

        with default_batch_backend(backend):
            with self.assertRaisesRegex(RuntimeError, "explicit queue_task_type"):
                run_batch_parallel(
                    lambda value: value + 10,
                    [1, 2],
                    max_workers=2,
                    task_type="classify.embedding",
                    concurrency_key="classify.embedding",
                )

    def test_profiled_batch_reuses_standard_task_metadata(self) -> None:
        backend = RecordingBackend()

        result = run_profiled_batch(
            lambda value: value + 1,
            [1, 2],
            profile=RELEVANCE_BATCH,
            max_workers=3,
            batch_indexes=[1, 2],
            batch_count=2,
            backend=backend,
        )

        self.assertEqual(result, [2, 3])
        self.assertEqual([item.metadata.task_name() for item in backend.seen], [
            "classify.batch_relevance[1/2]",
            "classify.batch_relevance[2/2]",
        ])
        self.assertEqual(backend.seen[0].metadata.concurrency_key, "classify.llm")
        self.assertEqual(backend.seen[0].metadata.labels, {"stage": "relevance"})

    def test_event_queue_backend_keeps_fixed_queue_task_types_as_only_runtime_path(self) -> None:
        queue = EventQueue()
        backend = EventQueueBatchExecutionBackend(
            queue,
            run_id="run-1",
            step_id="classify/embedding",
            base_payload={"project_root": "/tmp/project", "config": "/tmp/project/config.json"},
        )
        queue.register_executor("classify.embedding", lambda task: {"batch_result": {"key": task.payload["item_payload"]["key"], "vector": [1.0]}})

        result = run_profiled_batch(
            lambda value: {"key": value["key"], "vector": [2.0]},
            [{"key": "evt_1", "text": "hello"}],
            profile=CLUSTERED_EMBEDDING_BATCH,
            max_workers=1,
            backend=backend,
        )

        self.assertEqual(result, [{"key": "evt_1", "vector": [1.0]}])
        self.assertEqual({task.type for task in queue.list()}, {"classify.embedding"})

    def test_event_queue_backend_inherits_parent_task_runtime_policy(self) -> None:
        queue = EventQueue()
        parent_task = TaskEvent(
            id="classify-parent-1",
            type="classify.clustered_event_extraction",
            pipeline_run_id="run-1",
            step_id="classify/clustered_event_extraction",
            priority=7,
            recovery_policy="fail_running",
            max_attempts=3,
            retry_backoff_seconds=45,
            payload={"project_root": "/tmp/project", "config": "/tmp/project/config.json"},
        )
        backend = EventQueueBatchExecutionBackend(
            queue,
            base_payload=parent_task.payload,
            base_task=parent_task,
        )
        queue.register_executor("classify.embedding", lambda task: {"batch_result": {"key": task.payload["item_payload"]["key"], "vector": [1.0]}})

        result = run_profiled_batch(
            lambda value: {"key": value["key"], "vector": [2.0]},
            [{"key": "evt_1", "text": "hello"}],
            profile=CLUSTERED_EMBEDDING_BATCH,
            max_workers=1,
            backend=backend,
        )

        self.assertEqual(result, [{"key": "evt_1", "vector": [1.0]}])
        task = queue.list()[0]
        self.assertEqual(task.pipeline_run_id, "run-1")
        self.assertEqual(task.priority, 7)
        self.assertEqual(task.recovery_policy, "fail_running")
        self.assertEqual(task.max_attempts, 3)
        self.assertEqual(task.retry_backoff_seconds, 45)
        self.assertEqual(task.parent_task_id, "classify-parent-1")
        self.assertIsNotNone(task.task_group_id)
        self.assertEqual(task.payload["task_group_id"], task.task_group_id)
        self.assertEqual(task.payload["parent_task_id"], "classify-parent-1")
        self.assertEqual(task.payload["parent_task_type"], "classify.clustered_event_extraction")

    def test_event_queue_backend_uses_group_summary_for_failure_reporting(self) -> None:
        queue = EventQueue()
        backend = EventQueueBatchExecutionBackend(
            queue,
            run_id="run-1",
            step_id="classify/embedding",
            base_payload={"project_root": "/tmp/project", "config": "/tmp/project/config.json"},
        )

        def fail_second(task: TaskEvent) -> dict[str, object]:
            item_payload = task.payload.get("item_payload") if isinstance(task.payload.get("item_payload"), dict) else {}
            if item_payload.get("key") == "evt_2":
                raise RuntimeError("boom")
            return {"batch_result": {"key": task.payload["item_payload"]["key"], "vector": [1.0]}}

        queue.register_executor("classify.embedding", fail_second)

        with self.assertRaisesRegex(RuntimeError, "did not fully succeed") as raised:
            run_profiled_batch(
                lambda value: {"key": value["key"], "vector": [2.0]},
                [{"key": "evt_1", "text": "hello"}, {"key": "evt_2", "text": "world"}],
                profile=CLUSTERED_EMBEDDING_BATCH,
                max_workers=1,
                backend=backend,
            )

        self.assertIn("'failed': 1", str(raised.exception))
        self.assertIn("boom", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
