from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from modnews.app.server import create_app
from modnews.cli.commands.report import generate_report_command
from modnews.cli.local_client import LocalClient


class ReportEntrypointTest(unittest.TestCase):
    def test_cli_report_generate_uses_report_queue_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            captured = []

            def execute(task):
                captured.append(task)
                return {
                    "checkpoint_path": "/tmp/report/checkpoint.json",
                    "stats": {"event_count": 3, "selected_count": 2, "events_with_sources": 1},
                    "report_output_dir": "/tmp/report",
                }

            client.container.event_queue.register_executor("report.generate", execute)
            result = generate_report_command(
                None,
                client,
                argparse.Namespace(input=Path("input.json"), output_dir=Path("output"), date=None, config=None),
            )

            self.assertTrue(result["ok"])
            self.assertEqual([task.type for task in captured], ["report.generate"])
            self.assertEqual(result["event_count"], 3)
            self.assertEqual(result["task"]["type"], "report.generate")
            self.assertEqual(result["run"]["steps"][0]["step_id"], "report/generate")
            self.assertTrue(result["run"]["pipeline_steps"])
            self.assertEqual(result["run"]["pipeline_steps"][-1]["step_id"], "pipeline_report")

    def test_api_report_generate_uses_report_queue_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp))
            with app.app_context():
                from modnews.app.context import local_client

                client = local_client()
                captured = []

                def execute(task):
                    captured.append(task)
                    return {
                        "checkpoint_path": "/tmp/report/checkpoint.json",
                        "stats": {"event_count": 4, "selected_count": 3, "events_with_sources": 2},
                        "report_output_dir": "/tmp/report",
                    }

                client.container.event_queue.register_executor("report.generate", execute)
                response = app.test_client().post("/api/report/generate", json={"input": "input.json"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual([task.type for task in captured], ["report.generate"])
            self.assertEqual(response.get_json()["event_count"], 4)
            self.assertEqual(response.get_json()["task"]["type"], "report.generate")
            self.assertTrue(response.get_json()["run"]["steps"])
            self.assertTrue(response.get_json()["run"]["pipeline_steps"])


if __name__ == "__main__":
    unittest.main()
