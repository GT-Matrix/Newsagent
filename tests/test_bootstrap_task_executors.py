from __future__ import annotations

import unittest

from modnews.bootstrap.service_registry import configure_services


class BootstrapTaskExecutorTest(unittest.TestCase):
    def test_bootstrap_does_not_register_legacy_queue_task_types(self) -> None:
        container = configure_services()

        self.assertNotIn("pipeline.run_legacy", container.event_queue._executors)
        self.assertNotIn("classify.run_legacy", container.event_queue._executors)
        self.assertNotIn("classify.clustered_pipeline", container.event_queue._executors)
        self.assertNotIn("classify.batch_item", container.event_queue._executors)
        self.assertNotIn("classify.batch_relevance", container.event_queue._executors)
        self.assertIn("pipeline.combine_ingest", container.event_queue._executors)
        self.assertIn("classify.embedding", container.event_queue._executors)
        self.assertIn("classify.clustered_event_extraction.batch", container.event_queue._executors)
        self.assertIn("classify.clustered_event_merge.batch", container.event_queue._executors)
        self.assertIn("classify.clustered_event_extraction", container.event_queue._executors)
        self.assertIn("classify.clustered_event_merge", container.event_queue._executors)


if __name__ == "__main__":
    unittest.main()
