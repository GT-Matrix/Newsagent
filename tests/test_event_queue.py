from __future__ import annotations

import unittest

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.core.task import TaskBlocked, TaskEvent


class EventQueueTest(unittest.TestCase):
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
