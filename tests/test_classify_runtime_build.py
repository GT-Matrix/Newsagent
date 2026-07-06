from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.service.classify.runtime_build import resolve_classify_task_environment


class ClassifyRuntimeBuildTest(unittest.TestCase):
    def test_resolve_classify_task_environment_uses_task_payload_and_run_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config_path = project_root / "config.json"
            config_path.write_text(json.dumps({}), encoding="utf-8")
            task = TaskEvent(
                id="task-1",
                type="classify.clustered_event_extraction",
                pipeline_run_id="run-1",
                payload={
                    "project_root": str(project_root),
                    "run_id": "ignored-run-id",
                    "config": str(config_path),
                },
            )

            env = resolve_classify_task_environment(task)

            self.assertEqual(env.project_root, project_root.resolve())
            self.assertEqual(env.run_id, "run-1")
            self.assertEqual(env.config.project_root, project_root.resolve())
            self.assertEqual(env.ctx.config.project_root, project_root.resolve())


if __name__ == "__main__":
    unittest.main()
