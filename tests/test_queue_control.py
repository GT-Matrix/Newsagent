from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.app.server import create_app
from modnews.cli.local_client import LocalClient
from modnews.core.task import TaskEvent


class QueueControlTest(unittest.TestCase):
    def test_queue_cancel_marks_task_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            client.container.event_queue.register(TaskEvent(id="task-1", type="diagnostic.echo"))

            result = client.queue_cancel("task-1", "test cancel")

            self.assertTrue(result["ok"])
            self.assertEqual(result["task"]["state"], "cancelled")
            self.assertEqual(result["task"]["result"]["cancel_reason"], "test cancel")

    def test_queue_cancel_api_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp))
            with app.app_context():
                from modnews.app.context import local_client

                local_client().container.event_queue.register(TaskEvent(id="task-1", type="diagnostic.echo"))
            http = app.test_client()

            response = http.post("/api/queue/task-1/cancel", json={"reason": "api cancel"})

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["task"]["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()
