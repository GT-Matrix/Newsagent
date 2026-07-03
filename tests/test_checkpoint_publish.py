from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.bootstrap.event_handlers import register_completion_callbacks
from modnews.core.completion_callbacks import CompletionCallbackRegistry
from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.core.task import TaskEvent
from modnews.repository.outputs import OutputRepository
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.service.pipeline.manager import PipelineManager


class CheckpointPublishTest(unittest.TestCase):
    def test_output_repository_publishes_checkpoint_artifacts_under_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            checkpoint = self._write_checkpoint(project_root)

            result = OutputRepository(project_root).publish_from_checkpoint(checkpoint)

            self.assertEqual({row["key"] for row in result["published"]}, {"news_with_events", "events", "discarded_news"})
            self.assertEqual(json.loads((project_root / "output" / "events.json").read_text(encoding="utf-8"))[0]["event_id"], "e1")

    def test_completion_callback_auto_publishes_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            checkpoint = self._write_checkpoint(project_root)
            queue = EventQueue()
            router = EventRouter()
            registry = CompletionCallbackRegistry()
            manager = PipelineManager()
            manager.bind(queue, router)
            queue.bind_router(router)
            register_completion_callbacks(registry, manager)
            registry.bind(router)

            queue.register_executor(
                "test.publish",
                lambda _task: {"auto_publish_checkpoint": checkpoint["path"]},
            )
            task = TaskEvent(
                id="task-1",
                type="test.publish",
                payload={"project_root": str(project_root)},
            )
            queue.submit(task)

            result = queue.result("task-1")
            self.assertEqual(task.state, "succeeded")
            self.assertIn("publish", result)
            self.assertEqual(json.loads((project_root / "output" / "news_with_events.json").read_text(encoding="utf-8"))[0]["title"], "t")

    def _write_checkpoint(self, project_root: Path) -> dict[str, object]:
        manager = CheckpointManager(project_root)
        news_ref = manager.write_artifact("run-1", "classify/test", "task-1", "news_with_events.json", [{"title": "t"}])
        events_ref = manager.write_artifact("run-1", "classify/test", "task-1", "events.json", [{"event_id": "e1"}])
        discarded_ref = manager.write_artifact("run-1", "classify/test", "task-1", "discarded_news.json", [])
        checkpoint_path = manager.write(
            "run-1",
            "classify/test",
            "task-1",
            {
                "run_id": "run-1",
                "step_id": "classify/test",
                "task_id": "task-1",
                "status": "succeeded",
                "output_refs": {
                    "news_with_events": str(news_ref),
                    "events": str(events_ref),
                    "discarded_news": str(discarded_ref),
                },
                "stats": {},
                "error": None,
            },
        )
        return {**json.loads(checkpoint_path.read_text(encoding="utf-8")), "path": str(checkpoint_path)}


if __name__ == "__main__":
    unittest.main()
