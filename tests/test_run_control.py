from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.app.server import create_app
from modnews.cli.local_client import LocalClient
from modnews.core.task import TaskEvent


class RunControlTest(unittest.TestCase):
    def test_run_cancel_marks_queued_tasks_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            client.container.event_queue.register(
                TaskEvent(id="task-1", type="diagnostic.echo", pipeline_run_id="run-1", payload={"project_root": tmp})
            )
            client.container.runs().create("run-1", {})

            result = client.run_cancel("run-1", "test cancel")

            self.assertEqual(result["run"]["state"], "cancelled")
            self.assertEqual(result["cancelled_tasks"][0]["state"], "cancelled")
            self.assertEqual(client.container.event_queue.result("task-1")["cancel_reason"], "test cancel")

    def test_run_resume_drains_queued_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            client.container.event_queue.register(
                TaskEvent(id="task-1", type="diagnostic.echo", pipeline_run_id="run-1", payload={"project_root": tmp})
            )
            client.container.runs().create("run-1", {})

            result = client.run_resume("run-1")

            self.assertEqual(result["tasks"][0]["state"], "succeeded")
            self.assertEqual(client.container.event_queue.result("task-1")["payload"]["project_root"], tmp)

    def test_run_control_api_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp))
            with app.app_context():
                from modnews.app.context import local_client

                client_obj = local_client()
                client_obj.container.event_queue.register(TaskEvent(id="task-1", type="diagnostic.echo", pipeline_run_id="run-1"))
                client_obj.container.runs().create("run-1", {})
            http = app.test_client()

            response = http.post("/api/runs/run-1/cancel", json={"reason": "api cancel"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["run"]["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()
