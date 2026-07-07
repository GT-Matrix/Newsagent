from __future__ import annotations

import unittest

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.classify.batch_backends import EventQueueBatchExecutionBackend
from modnews.service.classify.batch_executor import default_batch_backend
from modnews.service.classify.batch_items import build_batch_items
from modnews.service.classify.batch_profile import CLUSTERED_EMBEDDING_BATCH
from modnews.service.classify.batch_queue_runtime import ClassifyBatchQueueRuntime
from modnews.service.classify.clustered_embedding import embed_rows_parallel
from modnews.service.classify.retriever import EventVectorRetriever
from modnews.core.config import EmbeddingConfig


class _FakeSession:
    def post(self, *args, **kwargs):  # pragma: no cover - should not be used
        raise AssertionError("network should not be used in queue runtime test")


class ClassifyBatchQueueRuntimeTest(unittest.TestCase):
    def test_runtime_submits_and_collects_embedding_batch_results(self) -> None:
        queue = EventQueue()
        queue.register_executor("classify.embedding", lambda task: {"batch_result": {"key": task.payload["item_payload"]["key"], "vector": [1.0]}})
        runtime = ClassifyBatchQueueRuntime(
            queue=queue,
            run_id="run-1",
            step_id="classify/clustered_event_extraction",
            base_payload={"project_root": "/tmp/project", "config": "/tmp/project/config.json"},
        )
        items = build_batch_items(
            [{"key": "evt-1", "text": "hello"}],
            task_type=CLUSTERED_EMBEDDING_BATCH.task_type,
            concurrency_key=CLUSTERED_EMBEDDING_BATCH.concurrency_key,
            max_concurrency=1,
            queue_task_type=CLUSTERED_EMBEDDING_BATCH.queue_task_type,
            labels=CLUSTERED_EMBEDDING_BATCH.labels,
        )

        result = runtime.submit_and_collect(items)

        self.assertEqual(result, [{"key": "evt-1", "vector": [1.0]}])

    def test_clustered_embedding_uses_default_batch_backend_and_parent_task(self) -> None:
        queue = EventQueue()
        queue.register_executor("classify.embedding", lambda task: {"batch_result": {"key": task.payload["item_payload"]["key"], "vector": [1.0, 2.0]}})
        task = TaskEvent(
            id="classify-parent-1",
            type="classify.clustered_event_extraction",
            pipeline_run_id="run-1",
            step_id="classify/clustered_event_extraction",
            payload={"project_root": "/tmp/project", "config": "/tmp/project/config.json"},
        )
        retriever = EventVectorRetriever(
            EmbeddingConfig(model="test", base_url=None, api_key=None, cache_path="/tmp/test-cache.json"),
            _FakeSession(),  # type: ignore[arg-type]
        )
        backend = EventQueueBatchExecutionBackend(
            queue=queue,
            run_id=task.pipeline_run_id,
            step_id=task.step_id,
            base_payload=task.payload,
            base_task=task,
        )

        with default_batch_backend(backend):
                rows = embed_rows_parallel([("evt-1", "hello")], retriever, concurrency=2)

        self.assertEqual(rows[0].key, "evt-1")
        self.assertEqual(rows[0].vector, [1.0, 2.0])
        queued = queue.list()[0]
        self.assertEqual(queued.parent_task_id, "classify-parent-1")
        self.assertEqual(queued.payload["parent_task_type"], "classify.clustered_event_extraction")


if __name__ == "__main__":
    unittest.main()
