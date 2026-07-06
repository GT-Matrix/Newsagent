from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.bootstrap import configure_services
from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.event_runtime import PipelineEventRuntime
from modnews.service.pipeline.manager import PipelineManager
from modnews.service.pipeline.step import PipelineStepBase


class PipelineEventRuntimeTest(unittest.TestCase):
    def test_completed_event_dispatches_followups_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            container = configure_services(project_root)
            queue = container.event_queue
            RunRepository(project_root).create("run-1", {})
            queue.register(
                TaskEvent(
                    id="merge-1",
                    type="classify.clustered_event_merge",
                    pipeline_run_id="run-1",
                    step_id="classify/clustered_event_merge",
                    state="succeeded",
                    payload={"project_root": tmp, "run_id": "run-1"},
                )
            )

            PipelineEventRuntime(container.pipeline_manager.step_registry, queue).handle(
                {"task": queue.get("merge-1").to_dict(), "result": {}},
                event_type="task.completed",
            )

            self.assertTrue(any(task.type == "report.generate" for task in queue.list()))

    def test_blocked_event_persists_callback_history(self) -> None:
        class SkipBlockedStep(PipelineStepBase):
            id = "skip_blocked"

            def plan(self, state, completed_event=None):
                return []

            def on_task_blocked(self, event, queue):
                task = event.get("task")
                if isinstance(task, dict):
                    queue.skip(str(task["id"]), reason="optional source blocked")
                    return [{"action": "skip_blocked_task", "task_id": task["id"]}]
                return []

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            queue = EventQueue()
            manager = PipelineManager()
            manager.bind(queue, None)  # type: ignore[arg-type]
            manager.register_step(SkipBlockedStep())
            RunRepository(project_root).create("run-1", {})
            queue.register(
                TaskEvent(
                    id="blocked",
                    type="diagnostic.missing",
                    pipeline_run_id="run-1",
                    payload={"project_root": tmp},
                )
            )

            PipelineEventRuntime(manager.step_registry, queue).handle(
                {"task": queue.get("blocked").to_dict(), "result": queue.result("blocked")},
                event_type="task.blocked",
            )

            run = RunRepository(project_root).get("run-1")
            callback_step = next(step for step in run["steps"] if step["step_id"] == "skip_blocked")
            self.assertEqual(callback_step["callback_events"][-1]["handler"], "on_task_blocked")


if __name__ == "__main__":
    unittest.main()
