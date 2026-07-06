from __future__ import annotations

from datetime import datetime, timedelta
import tempfile
import unittest
from pathlib import Path

from modnews.app.server import create_app
from modnews.cli.local_client import LocalClient
from modnews.core.progress import emit
from modnews.core.task import TaskEvent


class QueueControlTest(unittest.TestCase):
    def test_queue_status_includes_snapshot_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            client.container.event_queue.register(TaskEvent(id="task-1", type="diagnostic.echo"))

            result = client.queue_status()

            self.assertIn("snapshot", result)
            self.assertEqual(result["snapshot"]["version"], 1)
            self.assertEqual(result["snapshot"]["task_count"], 1)
            self.assertIsNotNone(result["snapshot"]["saved_at"])

    def test_queue_status_includes_waiting_retry_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            next_attempt_at = (datetime.now().astimezone() + timedelta(minutes=1)).isoformat(timespec="seconds")
            client.container.event_queue.register(
                TaskEvent(
                    id="task-1",
                    type="diagnostic.echo",
                    state="waiting",
                    next_attempt_at=next_attempt_at,
                    status_reason=f"waiting until retry window {next_attempt_at}",
                )
            )

            result = client.queue_status()

            self.assertEqual(result["waiting_retry_ids"], ["task-1"])
            self.assertEqual(result["waiting_dependency_ids"], [])
            self.assertEqual(result["waiting_concurrency_ids"], [])
            self.assertEqual(result["blocked_dependency_ids"], [])
            self.assertEqual(result["blocked_business_ids"], [])
            self.assertEqual(result["next_retry_at"], next_attempt_at)

    def test_queue_status_separates_dependency_and_concurrency_waiting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            client.container.event_queue.register(TaskEvent(id="dep-1", type="diagnostic.echo", state="running"))
            client.container.event_queue.register(TaskEvent(id="wait-dep", type="diagnostic.echo", depends_on=["dep-1"]))
            client.container.event_queue.register(TaskEvent(id="run-slot", type="diagnostic.echo", state="running", concurrency_key="classify", max_concurrency=1))
            client.container.event_queue.register(TaskEvent(id="wait-slot", type="diagnostic.echo", concurrency_key="classify", max_concurrency=1))
            client.container.event_queue.drain_ready(limit=0)

            result = client.queue_status()

            self.assertEqual(result["waiting_dependency_ids"], ["wait-dep"])
            self.assertEqual(result["waiting_concurrency_ids"], ["wait-slot"])

    def test_queue_status_separates_blocked_dependency_and_business_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            client.container.event_queue.register(TaskEvent(id="dep-1", type="diagnostic.echo", state="failed"))
            client.container.event_queue.register(TaskEvent(id="blocked-dep", type="diagnostic.echo", state="blocked", depends_on=["dep-1"]))
            client.container.event_queue.register(TaskEvent(id="blocked-business", type="diagnostic.echo", state="blocked"))
            client.container.event_queue._results["blocked-business"] = {"blocked_reason": "captcha required", "blocked_details": {"kind": "business"}}  # type: ignore[attr-defined]

            result = client.queue_status()

            self.assertEqual(result["blocked_dependency_ids"], ["blocked-dep"])
            self.assertEqual(result["blocked_business_ids"], ["blocked-business"])

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

    def test_queue_retry_reruns_failed_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            client.container.event_queue.register(TaskEvent(id="task-1", type="missing.executor"))
            client.container.event_queue.drain_ready()
            self.assertEqual(client.container.event_queue.get("task-1").state, "failed")
            client.container.event_queue.register_executor("missing.executor", lambda _task: {"value": "ok"})

            result = client.queue_retry("task-1")

            self.assertTrue(result["ok"])
            self.assertEqual(result["task"]["state"], "succeeded")
            self.assertEqual(result["task"]["result"]["value"], "ok")

    def test_queue_retry_api_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp))
            with app.app_context():
                from modnews.app.context import local_client

                client_obj = local_client()
                client_obj.container.event_queue.register(TaskEvent(id="task-1", type="missing.executor"))
                client_obj.container.event_queue.drain_ready()
                client_obj.container.event_queue.register_executor("missing.executor", lambda _task: {"value": "ok"})
            http = app.test_client()

            response = http.post("/api/queue/task-1/retry")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["task"]["state"], "succeeded")

    def test_queue_show_includes_task_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            result = client.queue_echo("task-logs-1", {"message": "hello"})

            self.assertEqual(result["state"], "succeeded")
            self.assertGreaterEqual(len(result["logs"]), 3)
            self.assertEqual(result["logs"][0]["type"], "task.registered")
            self.assertIn("task.completed", {row["type"] for row in result["logs"]})

    def test_progress_events_inside_task_are_written_to_task_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            client.container.event_queue.register_executor(
                "diagnostic.progress",
                lambda _task: emit("llm_request_start", task="unit_test", request_id="req-1") and {"value": "ok"},
            )

            client.container.event_queue.submit(TaskEvent(id="progress-task-1", type="diagnostic.progress"))
            result = client.queue_show("progress-task-1")

            self.assertIn("progress.llm_request_start", {row["type"] for row in result["logs"]})


if __name__ == "__main__":
    unittest.main()
