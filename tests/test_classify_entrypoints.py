from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from modnews.app.server import create_app
from modnews.cli.commands.classify import run_classify
from modnews.cli.local_client import LocalClient


class ClassifyEntrypointTest(unittest.TestCase):
    def test_cli_classify_run_uses_clustered_stage_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            captured = []

            def execute(task):
                captured.append(task)
                return {"ok": True}

            client.container.event_queue.register_executor("classify.clustered_event_extraction", execute)
            client.container.event_queue.register_executor("classify.clustered_event_merge", execute)
            result = run_classify(
                None,
                client,
                argparse.Namespace(input="input.json", run_id="run-1"),
            )

            self.assertEqual([task.type for task in captured], ["classify.clustered_event_extraction", "classify.clustered_event_merge"])
            self.assertEqual(result["tasks"][0]["step_id"], "classify/clustered_event_extraction")
            self.assertEqual(result["tasks"][1]["step_id"], "classify/clustered_event_merge")
            self.assertEqual(result["run"]["steps"][0]["step_id"], "classify/clustered_event_extraction")

    def test_api_classify_run_uses_clustered_stage_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp))
            with app.app_context():
                from modnews.app.context import local_client

                client = local_client()
                captured = []

                def execute(task):
                    captured.append(task)
                    return {"ok": True}

                client.container.event_queue.register_executor("classify.clustered_event_extraction", execute)
                client.container.event_queue.register_executor("classify.clustered_event_merge", execute)
                response = app.test_client().post("/api/classify/run", json={"input_path": "input.json", "run_id": "run-1"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual([task.type for task in captured], ["classify.clustered_event_extraction", "classify.clustered_event_merge"])
            self.assertEqual(response.get_json()["tasks"][1]["type"], "classify.clustered_event_merge")
            self.assertTrue(response.get_json()["run"]["steps"])


if __name__ == "__main__":
    unittest.main()
