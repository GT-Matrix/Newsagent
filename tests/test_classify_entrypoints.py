from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from modnews.app.server import create_app
from modnews.cli.commands.classify import run_classify
from modnews.cli.local_client import LocalClient
from modnews.service.classify.queue_runtime import submit_clustered_classify_run


class ClassifyEntrypointTest(unittest.TestCase):
    def test_submit_clustered_classify_run_uses_registered_clustered_task_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            captured = []

            def execute(task):
                captured.append(task)
                return {"ok": True}

            client.container.event_queue.register_executor("classify.clustered_event_extraction", execute)
            client.container.event_queue.register_executor("classify.clustered_event_merge", execute)

            result = submit_clustered_classify_run(
                project_root=client.project_root,
                queue=client.container.event_queue,
                queue_show=client.queue_show,
                run_id="run-1",
                input_path="input.json",
                pipeline_descriptors=client.container.pipeline_manager.describe_steps(),
            )

            self.assertEqual([task.type for task in captured], ["classify.clustered_event_extraction", "classify.clustered_event_merge"])
            self.assertEqual(result["run_id"], "run-1")
            self.assertEqual(result["tasks"][0]["type"], "classify.clustered_event_extraction")
            self.assertEqual(result["tasks"][1]["type"], "classify.clustered_event_merge")

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
            self.assertTrue(result["run"]["pipeline_steps"])
            self.assertEqual(result["run"]["pipeline_steps"][0]["step_id"], "pipeline_ingest")

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
            self.assertTrue(response.get_json()["run"]["pipeline_steps"])

    def test_manual_classify_followup_is_recorded_by_pipeline_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            client.container.event_queue.register_executor("classify.clustered_event_extraction", lambda _task: {"ok": True})
            client.container.event_queue.register_executor("classify.clustered_event_merge", lambda _task: {"ok": True})
            client.container.event_queue.register_executor("report.generate", lambda _task: {"ok": True})

            result = run_classify(
                None,
                client,
                argparse.Namespace(input="input.json", run_id="run-1"),
            )

            callback_steps = {
                step["step_id"]: step
                for step in result["run"]["steps"]
                if step.get("callback_events")
            }
            self.assertIn("pipeline_classify", callback_steps)
            classify_callback = callback_steps["pipeline_classify"]["callback_events"][-1]
            self.assertEqual(classify_callback["event_task_type"], "classify.clustered_event_extraction")
            self.assertEqual(classify_callback["decisions"][-1]["trigger"], "classify_extraction_completed")
            self.assertEqual(classify_callback["decisions"][-1]["task_type"], "classify.clustered_event_merge")


if __name__ == "__main__":
    unittest.main()
