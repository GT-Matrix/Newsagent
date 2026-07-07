from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.cli.local_client import LocalClient
from modnews.service.pipeline.runtime_facade import PipelineRuntimeFacade


class PipelineRuntimeFacadeTest(unittest.TestCase):
    def test_runtime_facade_starts_background_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)

            result = PipelineRuntimeFacade(
                project_root,
                client.container.event_queue,
                client.container.pipeline_manager,
            ).start({"background": True, "disable_classification": True})

            self.assertTrue(result["ok"])
            self.assertIn("run", result)
            self.assertTrue(result["tasks"])

    def test_runtime_facade_cancels_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            runtime = PipelineRuntimeFacade(
                project_root,
                client.container.event_queue,
                client.container.pipeline_manager,
            )
            started = runtime.start({"background": True, "disable_classification": True, "run_id": "run-1"})

            result = runtime.cancel("run-1", "test cancel")

            self.assertTrue(started["ok"])
            self.assertEqual(result["run"]["state"], "cancelled")


if __name__ == "__main__":
    unittest.main()
