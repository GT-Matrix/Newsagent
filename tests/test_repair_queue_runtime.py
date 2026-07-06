from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.extraction.repair_queue_runtime import (
    ensure_repair_queue_task,
    handle_blocked_web_source_event,
)


class RepairQueueRuntimeTest(unittest.TestCase):
    def test_ensure_repair_queue_task_reuses_active_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            queue = EventQueue()
            queue.register_executor("extractor.repair.codex", lambda task: {"repair_task_id": task.payload["repair_task_id"]})

            first = ensure_repair_queue_task(
                queue,
                project_root=project_root,
                repair_task_id="repair-1",
                source_id="site-1",
                run_id="run-1",
            )
            second = ensure_repair_queue_task(
                queue,
                project_root=project_root,
                repair_task_id="repair-1",
                source_id="site-1",
                run_id="run-1",
            )

            self.assertTrue(first["created"])
            self.assertEqual(first["queue_task_state"], "succeeded")
            self.assertFalse(second["created"])
            self.assertEqual(second["action"], "reuse_repair_queue_task")
            self.assertEqual(second["queue_task_id"], first["queue_task_id"])
            self.assertEqual(len([task for task in queue.list() if task.type == "extractor.repair.codex"]), 1)

    def test_handle_blocked_web_source_event_queues_repair_and_skips_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            queue = EventQueue()
            queue.register_executor("extractor.repair.codex", lambda task: {"repair_task_id": task.payload["repair_task_id"]})
            blocked = TaskEvent(
                id="web-source-task-1",
                type="web_source.run",
                pipeline_run_id="run-1",
                step_id="ingest/site_lists/site-1",
                state="blocked",
                payload={"project_root": str(project_root), "source_id": "site-1"},
            )
            queue.register(blocked)

            patch = handle_blocked_web_source_event(
                queue,
                {
                    "task": blocked.to_dict(),
                    "result": {
                        "blocked_reason": "repair required",
                        "repair_task_id": "repair-1",
                        "job": {"id": "job-1", "source_id": "site-1"},
                    },
                },
            )

            self.assertIsNotNone(patch)
            assert patch is not None
            self.assertEqual(queue.get("web-source-task-1").state, "skipped")
            self.assertEqual(len([task for task in queue.list() if task.type == "extractor.repair.codex"]), 1)
            self.assertEqual(
                [action["action"] for action in patch["repair_queue_actions"]],
                ["submit_repair_queue_task", "skip_blocked_task"],
            )


if __name__ == "__main__":
    unittest.main()
