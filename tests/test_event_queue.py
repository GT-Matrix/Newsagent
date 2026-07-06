from __future__ import annotations

from datetime import datetime, timedelta
import unittest
import tempfile
from pathlib import Path

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.core.task import TaskBlocked, TaskEvent
from modnews.cli.local_client import LocalClient


class EventQueueTest(unittest.TestCase):
    def test_snapshot_restore_requeues_running_task(self) -> None:
        queue = EventQueue()
        queue.register(TaskEvent(id="task-1", type="diagnostic.echo", state="running", started_at="2026-01-01T00:00:00+08:00"))
        payload = queue.snapshot()

        restored = EventQueue()
        restored.load_snapshot(payload)

        task = restored.get("task-1")
        self.assertEqual(task.state, "queued")
        self.assertEqual(task.status_reason, "restored from interrupted running state")
        self.assertEqual(restored.result("task-1")["restored_from"], "running")
        self.assertEqual(payload["version"], 1)
        self.assertIsNotNone(payload["saved_at"])

    def test_snapshot_restore_can_fail_running_task_by_policy(self) -> None:
        queue = EventQueue()
        queue.register(
            TaskEvent(
                id="task-1",
                type="diagnostic.echo",
                state="running",
                recovery_policy="fail_running",
                started_at="2026-01-01T00:00:00+08:00",
            )
        )

        restored = EventQueue()
        restored.load_snapshot(queue.snapshot())

        task = restored.get("task-1")
        self.assertEqual(task.state, "failed")
        self.assertEqual(restored.result("task-1")["restored_from"], "running")

    def test_ready_prefers_lower_priority_value(self) -> None:
        queue = EventQueue()
        queue.register(TaskEvent(id="slow", type="diagnostic.echo", priority=100))
        queue.register(TaskEvent(id="fast", type="diagnostic.echo", priority=10))

        self.assertEqual(queue._next_ready().id, "fast")  # type: ignore[union-attr]

    def test_local_client_restores_persisted_queue_and_resume_can_continue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.runs().create("run-1", {})
            client.container.event_queue.register(
                TaskEvent(
                    id="task-1",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    payload={"project_root": tmp},
                )
            )

            restarted = LocalClient(project_root)
            result = restarted.run_resume("run-1")

            self.assertEqual(result["tasks"][0]["state"], "succeeded")
            self.assertEqual(restarted.container.event_queue.result("task-1")["payload"]["project_root"], tmp)

    def test_unfinished_dependency_is_waiting_not_blocked(self) -> None:
        queue = EventQueue()
        queue.register(TaskEvent(id="first", type="diagnostic.never", state="running"))
        queue.register(TaskEvent(id="second", type="diagnostic.never", depends_on=["first"]))

        queue.drain_ready()

        second = queue.get("second")
        self.assertEqual(second.state, "waiting")
        self.assertEqual(queue.result("second")["waiting_reason"], "waiting for dependency first")
        self.assertIsNone(queue.blocked_reason(second))
        self.assertEqual(queue.waiting_reason(second), "waiting for dependency first")

    def test_terminal_dependency_blocks_dependent_task(self) -> None:
        queue = EventQueue()
        router = EventRouter()
        seen: list[dict[str, object]] = []
        router.on("task.blocked", lambda event: seen.append(event) or None)
        queue.bind_router(router)
        queue.register(TaskEvent(id="first", type="diagnostic.missing"))
        queue.register(TaskEvent(id="second", type="diagnostic.missing", depends_on=["first"]))

        queue.drain_ready()

        second = queue.get("second")
        self.assertEqual(second.state, "blocked")
        self.assertEqual(queue.result("second")["blocked_reason"], "dependency first ended as failed")
        self.assertEqual(len(seen), 1)

    def test_business_blocked_dispatches_blocked_event(self) -> None:
        queue = EventQueue()
        router = EventRouter()
        seen: list[dict[str, object]] = []
        router.on("task.blocked", lambda event: seen.append(event) or None)
        queue.bind_router(router)
        queue.register_executor("diagnostic.blocked", lambda _task: (_ for _ in ()).throw(TaskBlocked("captcha required")))

        task = queue.submit(TaskEvent(id="blocked-1", type="diagnostic.blocked"))

        self.assertEqual(task.state, "blocked")
        self.assertEqual(queue.blocked_reason(task), "captcha required")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["result"]["blocked_reason"], "captcha required")  # type: ignore[index]

    def test_failed_task_retries_until_max_attempts(self) -> None:
        queue = EventQueue()
        attempts = {"count": 0}

        def flaky(_task: TaskEvent) -> dict[str, object]:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("temporary failure")
            return {"value": "ok"}

        queue.register_executor("diagnostic.flaky", flaky)

        task = queue.submit(TaskEvent(id="flaky-1", type="diagnostic.flaky", max_attempts=2))

        self.assertEqual(task.state, "succeeded")
        self.assertEqual(task.attempt, 2)
        self.assertEqual(queue.result("flaky-1")["value"], "ok")

    def test_retry_schedule_waits_until_backoff_window(self) -> None:
        queue = EventQueue()

        def flaky(_task: TaskEvent) -> dict[str, object]:
            raise RuntimeError("temporary failure")

        queue.register_executor("diagnostic.flaky", flaky)

        task = queue.submit(TaskEvent(id="flaky-1", type="diagnostic.flaky", max_attempts=2, retry_backoff_seconds=30))

        self.assertEqual(task.state, "waiting")
        self.assertEqual(queue.result("flaky-1")["retry_delay_seconds"], 30)
        self.assertIsNotNone(task.next_attempt_at)
        self.assertEqual(queue.waiting_reason(task), f"waiting until retry window {task.next_attempt_at}")
        self.assertIsNone(queue._next_ready())  # type: ignore[union-attr]

    def test_manual_retry_clears_scheduled_retry_window(self) -> None:
        queue = EventQueue()
        future_retry = (datetime.now().astimezone() + timedelta(minutes=5)).isoformat(timespec="seconds")
        queue.register(
            TaskEvent(
                id="task-1",
                type="diagnostic.echo",
                state="blocked",
                attempt=1,
                next_attempt_at=future_retry,
            )
        )

        retried = queue.retry("task-1")

        self.assertEqual(retried.state, "queued")
        self.assertIsNone(retried.next_attempt_at)
        self.assertIsNone(retried.status_reason)

    def test_snapshot_preserves_retry_window_metadata(self) -> None:
        queue = EventQueue()
        next_attempt_at = (datetime.now().astimezone() + timedelta(seconds=45)).isoformat(timespec="seconds")
        queue.register(
            TaskEvent(
                id="task-1",
                type="diagnostic.echo",
                state="queued",
                retry_backoff_seconds=45,
                next_attempt_at=next_attempt_at,
                status_reason="retry scheduled after attempt 1",
            )
        )

        restored = EventQueue()
        restored.load_snapshot(queue.snapshot())

        task = restored.get("task-1")
        self.assertEqual(task.retry_backoff_seconds, 45)
        self.assertEqual(task.next_attempt_at, next_attempt_at)
        self.assertEqual(restored.waiting_reason(task), f"waiting until retry window {next_attempt_at}")

    def test_skipped_dependency_allows_dependent_task_to_run(self) -> None:
        queue = EventQueue()
        queue.register_executor("diagnostic.echo", lambda _task: {"value": "ok"})
        queue.register(TaskEvent(id="first", type="diagnostic.never", state="blocked"))
        queue.register(TaskEvent(id="second", type="diagnostic.echo", depends_on=["first"]))

        queue.skip("first", reason="safe to skip")

        self.assertEqual(queue.get("first").state, "skipped")
        self.assertEqual(queue.result("first")["skip_reason"], "safe to skip")
        self.assertEqual(queue.get("second").state, "succeeded")
        self.assertEqual(queue.result("second")["value"], "ok")

    def test_skip_releases_cascaded_blocked_dependencies(self) -> None:
        queue = EventQueue()
        queue.register_executor("diagnostic.echo", lambda _task: {"value": "ok"})
        queue.register(TaskEvent(id="first", type="diagnostic.never", state="blocked"))
        queue.register(TaskEvent(id="second", type="diagnostic.never", state="blocked", depends_on=["first"]))
        queue.register(TaskEvent(id="third", type="diagnostic.echo", state="blocked", depends_on=["second"]))

        queue.skip("first", reason="safe to skip")
        queue.skip("second", reason="safe to skip dependent")

        self.assertEqual(queue.get("third").state, "succeeded")


if __name__ == "__main__":
    unittest.main()
