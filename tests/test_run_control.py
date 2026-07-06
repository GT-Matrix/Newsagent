from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.app.server import create_app
from modnews.cli.local_client import LocalClient
from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.followups import FOLLOWUP_BUILDERS
from modnews.service.pipeline.manager import PipelineManager
from modnews.service.pipeline.step import PipelineStepBase


class RunControlTest(unittest.TestCase):
    def test_run_start_registers_task_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            result = client.run_start({"background": True, "disable_classification": True})

            self.assertTrue(result["ok"])
            self.assertIn("tasks", result)
            self.assertNotIn("task", result)
            task_types = [task["type"] for task in result["tasks"]]
            self.assertIn("ingest.run_step", task_types)
            self.assertNotIn("pipeline.combine_ingest", task_types)
            self.assertNotIn("classify.clustered_event_extraction", task_types)
            self.assertNotIn("report.generate", task_types)
            self.assertTrue(result["run"]["steps"])
            self.assertTrue(all(not step["step_id"].startswith("pipeline/") for step in result["run"]["steps"]))

    def test_pipeline_callbacks_register_followup_tasks_incrementally(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            RunRepository(project_root).create("run-1", {})

            client.container.event_queue.register(
                TaskEvent(
                    id="ingest-rss",
                    type="ingest.run_step",
                    pipeline_run_id="run-1",
                    step_id="ingest/rss",
                    state="succeeded",
                    payload={"project_root": tmp, "run_id": "run-1"},
                )
            )
            client.container.event_queue.register(
                TaskEvent(
                    id="ingest-newsnow",
                    type="ingest.run_step",
                    pipeline_run_id="run-1",
                    step_id="ingest/newsnow",
                    state="succeeded",
                    payload={"project_root": tmp, "run_id": "run-1"},
                )
            )

            client.container.pipeline_manager.on_task_completed(
                {"task": client.container.event_queue.get("ingest-rss").to_dict(), "result": {}}
            )
            client.container.pipeline_manager.on_task_completed(
                {"task": client.container.event_queue.get("ingest-rss").to_dict(), "result": {}}
            )

            combine = client.container.event_queue.get("pipeline-run-1-combine-ingest")
            self.assertEqual(combine.depends_on, ["ingest-newsnow", "ingest-rss"])
            self.assertEqual(len([task for task in client.container.event_queue.list() if task.type == "pipeline.combine_ingest"]), 1)

            combine.state = "succeeded"
            client.container.pipeline_manager.on_task_completed({"task": combine.to_dict(), "result": {}})

            extraction = client.container.event_queue.get("classify-run-1-clustered-event-extraction")
            self.assertEqual(extraction.depends_on, ["pipeline-run-1-combine-ingest"])

            extraction.state = "succeeded"
            client.container.pipeline_manager.on_task_completed({"task": extraction.to_dict(), "result": {}})

            merge = client.container.event_queue.get("classify-run-1-clustered-event-merge")
            self.assertEqual(merge.depends_on, ["classify-run-1-clustered-event-extraction"])

            merge.state = "succeeded"
            client.container.pipeline_manager.on_task_completed({"task": merge.to_dict(), "result": {}})

            report = client.container.event_queue.get("report-run-1-generate")
            self.assertEqual(report.depends_on, ["classify-run-1-clustered-event-merge"])

    def test_pipeline_followup_builders_are_registered_by_identifier(self) -> None:
        self.assertEqual(
            sorted(FOLLOWUP_BUILDERS),
            [
                "classify_extraction_after_combine",
                "classify_merge_after_extraction",
                "combine_ingest_for_run",
                "report_after_classify_merge",
            ],
        )

    def test_run_cancel_marks_queued_tasks_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            client.container.event_queue.register(
                TaskEvent(id="task-1", type="diagnostic.echo", pipeline_run_id="run-1", payload={"project_root": tmp})
            )
            client.container.runs().create("run-1", {})

            result = client.run_cancel("run-1", "test cancel")

            self.assertEqual(result["run"]["state"], "cancelled")
            self.assertEqual(result["cancelled_tasks"][0]["state"], "cancelled")
            self.assertEqual(client.container.event_queue.result("task-1")["cancel_reason"], "test cancel")
            self.assertEqual(result["run"]["steps"][0]["status"], "partial")

    def test_run_resume_drains_queued_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))
            client.container.event_queue.register(
                TaskEvent(id="task-1", type="diagnostic.echo", pipeline_run_id="run-1", payload={"project_root": tmp})
            )
            client.container.runs().create("run-1", {})

            result = client.run_resume("run-1")

            self.assertEqual(result["tasks"][0]["state"], "succeeded")
            self.assertEqual(client.container.event_queue.result("task-1")["payload"]["project_root"], tmp)

    def test_run_control_api_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp))
            with app.app_context():
                from modnews.app.context import local_client

                client_obj = local_client()
                client_obj.container.event_queue.register(TaskEvent(id="task-1", type="diagnostic.echo", pipeline_run_id="run-1"))
                client_obj.container.runs().create("run-1", {})
            http = app.test_client()

            response = http.post("/api/runs/run-1/cancel", json={"reason": "api cancel"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["run"]["state"], "cancelled")

    def test_pipeline_step_metadata_is_exposed_via_state_and_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = LocalClient(Path(tmp))

            state = client.state()
            self.assertIn("pipeline", state)
            self.assertEqual(
                [item["step_id"] for item in state["pipeline"]["steps"]],
                ["pipeline_ingest", "pipeline_combine_ingest", "pipeline_classify", "pipeline_report"],
            )
            classify = next(item for item in state["pipeline"]["steps"] if item["step_id"] == "pipeline_classify")
            self.assertEqual(classify["callback_handlers"], ["completed"])
            self.assertEqual(classify["followups"][0]["builder_id"], "classify_extraction_after_combine")

            app = create_app(Path(tmp))
            http = app.test_client()
            response = http.get("/api/pipeline/steps")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["items"][0]["title"], "Ingest Planner")
            self.assertEqual(payload["items"][-1]["group"], "report")

    def test_blocked_step_callback_can_safely_skip_task(self) -> None:
        class SkipBlockedStep(PipelineStepBase):
            id = "skip_blocked"

            def plan(self, state, completed_event=None):
                return []

            def on_task_blocked(self, event, queue):
                task = event.get("task")
                if isinstance(task, dict):
                    queue.skip(str(task["id"]), reason="optional source blocked")
                    return [{"action": "skip_blocked_task", "task_id": task["id"], "reason": "optional source blocked"}]
                return []

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            queue = EventQueue()
            manager = PipelineManager()
            manager.bind(queue, None)  # type: ignore[arg-type]
            manager.register_step(SkipBlockedStep())
            queue.register_executor("diagnostic.echo", lambda _task: {"value": "ok"})
            RunRepository(project_root).create("run-1", {})
            queue.register(
                TaskEvent(
                    id="blocked",
                    type="diagnostic.missing",
                    pipeline_run_id="run-1",
                    payload={"project_root": tmp},
                )
            )
            queue.register(
                TaskEvent(
                    id="dependent",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    depends_on=["blocked"],
                    payload={"project_root": tmp},
                )
            )

            queue.drain_ready()
            manager.on_task_blocked({"task": queue.get("blocked").to_dict(), "result": queue.result("blocked")})

            self.assertEqual(queue.get("blocked").state, "skipped")
            self.assertEqual(queue.get("dependent").state, "succeeded")
            run = RunRepository(project_root).get("run-1")
            callback_step = next(step for step in run["steps"] if step["step_id"] == "skip_blocked")
            self.assertEqual(callback_step["callback_events"][-1]["handler"], "on_task_blocked")
            self.assertEqual(callback_step["callback_events"][-1]["decisions"][-1]["action"], "skip_blocked_task")


if __name__ == "__main__":
    unittest.main()
