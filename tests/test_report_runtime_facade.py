from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.cli.local_client import LocalClient
from modnews.service.report.runtime_facade import ReportRuntimeFacade


class ReportRuntimeFacadeTest(unittest.TestCase):
    def test_runtime_facade_runs_report_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            input_file = project_root / "events.json"
            input_file.write_text("[]", encoding="utf-8")

            result = ReportRuntimeFacade(
                project_root=project_root,
                queue=client.container.event_queue,
                queue_show=client.queue_show,
                pipeline_descriptors=client.container.pipeline_manager.describe_steps(),
            ).run({"input": str(input_file), "run_id": "run-1"})

            self.assertIn("ok", result)
            self.assertIn("tasks", result)
            self.assertEqual(result["task"]["step_id"], "report/generate")


if __name__ == "__main__":
    unittest.main()
