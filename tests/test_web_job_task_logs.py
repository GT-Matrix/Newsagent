from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.cli.local_client import LocalClient
from modnews.core.task import TaskEvent
from modnews.repository.web_jobs import WebJobStore
from modnews.service.extraction.web_contract import WebSource


class WebJobTaskLogTest(unittest.TestCase):
    def test_web_job_events_inside_task_are_written_to_task_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            def execute(_task: TaskEvent) -> dict[str, object]:
                store = WebJobStore(Path(tmp))
                job = store.create(
                    WebSource(id="site-1", name="Site", url="https://example.com", extractor_id="site-1"),
                    max_attempts=1,
                )
                store.append(job.id, "scrape_started", attempt=1, max_attempts=1)
                return {"job_id": job.id}

            client.container.event_queue.register_executor("diagnostic.web_job", execute)
            client.container.event_queue.submit(TaskEvent(id="web-job-task-1", type="diagnostic.web_job"))
            result = client.queue_show("web-job-task-1")

            log_types = {row["type"] for row in result["logs"]}
            self.assertIn("progress.web_job_event", log_types)
            web_events = [row for row in result["logs"] if row["type"] == "progress.web_job_event"]
            self.assertEqual({row["web_event_type"] for row in web_events}, {"job_created", "scrape_started"})


if __name__ == "__main__":
    unittest.main()
