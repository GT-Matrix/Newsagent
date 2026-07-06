from __future__ import annotations

import unittest

from modnews.bootstrap.service_registry import configure_services
from modnews.service.classify.batch_task_registry import REGISTERED_BATCH_TASKS
from modnews.service.classify.task_execution import REGISTERED_CLASSIFY_TASK_EXECUTORS
from modnews.service.ingest.tasks import REGISTERED_INGEST_TASK_EXECUTORS
from modnews.service.pipeline.tasks import REGISTERED_PIPELINE_TASK_EXECUTORS


class BootstrapTaskExecutorTest(unittest.TestCase):
    def test_bootstrap_does_not_register_legacy_queue_task_types(self) -> None:
        container = configure_services()

        self.assertNotIn("pipeline.run_legacy", container.event_queue._executors)
        self.assertNotIn("classify.run_legacy", container.event_queue._executors)
        self.assertNotIn("classify.clustered_pipeline", container.event_queue._executors)
        self.assertNotIn("classify.batch_item", container.event_queue._executors)
        self.assertNotIn("classify.batch_relevance", container.event_queue._executors)
        self.assertIn("pipeline.combine_ingest", container.event_queue._executors)
        self.assertTrue({spec.task_type for spec in REGISTERED_BATCH_TASKS}.issubset(set(container.event_queue._executors)))
        self.assertTrue(set(REGISTERED_CLASSIFY_TASK_EXECUTORS).issubset(set(container.event_queue._executors)))
        self.assertTrue(set(REGISTERED_INGEST_TASK_EXECUTORS).issubset(set(container.event_queue._executors)))
        self.assertTrue(set(REGISTERED_PIPELINE_TASK_EXECUTORS).issubset(set(container.event_queue._executors)))


if __name__ == "__main__":
    unittest.main()
