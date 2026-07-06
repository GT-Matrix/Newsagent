from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.app.server import create_app
from modnews.cli.local_client import LocalClient
from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.pipeline.manager import PipelineManager


class RunControlTest(unittest.TestCase):
    def test_run_start_registers_task_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            result = client.run_start({"background": True, "disable_classification": True})

            self.assertTrue(result["ok"])
            self.assertIn("tasks", result)
            self.assertNotIn("task", result)
            self.assertIn("pipeline-", result["tasks"][-1]["id"])
            task_types = [task["type"] for task in result["tasks"]]
            self.assertEqual(task_types[-1], "pipeline.combine_ingest")
            self.assertIn("ingest.run_step", task_types)
            self.assertNotIn("classify.clustered_event_extraction", task_types)
            self.assertNotIn("report.generate", task_types)

    def test_run_start_registers_classify_and_report_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            result = client.run_start({"background": True})

            task_types = [task["type"] for task in result["tasks"]]
            self.assertIn("classify.clustered_event_extraction", task_types)
            self.assertIn("classify.clustered_event_merge", task_types)
            self.assertIn("report.generate", task_types)
            self.assertLess(task_types.index("classify.clustered_event_merge"), task_types.index("report.generate"))

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

    def test_blocked_step_callback_can_safely_skip_task(self) -> None:
        class SkipBlockedStep:
            id = "skip_blocked"

            def plan(self, state, completed_event=None):
                return []

            def on_task_blocked(self, event, queue):
                task = event.get("task")
                if isinstance(task, dict):
                    queue.skip(str(task["id"]), reason="optional source blocked")

        queue = EventQueue()
        manager = PipelineManager()
        manager.bind(queue, None)  # type: ignore[arg-type]
        manager.register_step(SkipBlockedStep())
        queue.register_executor("diagnostic.echo", lambda _task: {"value": "ok"})
        queue.register(TaskEvent(id="blocked", type="diagnostic.missing"))
        queue.register(TaskEvent(id="dependent", type="diagnostic.echo", depends_on=["blocked"]))

        queue.drain_ready()
        manager.on_task_blocked({"task": queue.get("blocked").to_dict(), "result": queue.result("blocked")})

        self.assertEqual(queue.get("blocked").state, "skipped")
        self.assertEqual(queue.get("dependent").state, "succeeded")


if __name__ == "__main__":
    unittest.main()
