from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.cli.local_client import LocalClient
from modnews.core.task import TaskEvent


class PipelineReadModelTest(unittest.TestCase):
    def test_run_list_returns_frontend_ready_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.runs().create("run-1", {"source": "test"})
            client.container.event_queue.register(
                TaskEvent(
                    id="task-1",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    step_id="ingest/rss",
                    state="blocked",
                )
            )
            artifact = client.container.checkpoints().write_artifact("run-1", "ingest/rss", "task-1", "items.json", [{"title": "A"}])
            checkpoint = client.container.checkpoints().write(
                "run-1",
                "ingest/rss",
                "task-1",
                {
                    "status": "blocked",
                    "output_refs": {"items": str(artifact)},
                },
            )
            client.container.runs().append_checkpoint("run-1", checkpoint)

            result = client.run_list()

            self.assertEqual(result[0]["run_id"], "run-1")
            self.assertEqual(result[0]["task_summary"]["blocked"], 1)
            self.assertEqual(result[0]["steps_summary"]["by_status"]["blocked"], 1)
            self.assertEqual(result[0]["latest_checkpoint"]["task_id"], "task-1")
            self.assertEqual(result[0]["artifact_count"], 1)

    def test_queue_list_returns_frontend_ready_task_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.event_queue.register_executor(
                "report.generate",
                lambda _task: {"checkpoint_path": "runtime/checkpoints/run-1/report/checkpoint.json", "stats": {"selected_count": 1}},
            )
            client.container.event_queue.submit(
                TaskEvent(
                    id="task-1",
                    type="report.generate",
                    pipeline_run_id="run-1",
                    step_id="pipeline/report",
                    priority=20,
                    recovery_policy="fail_running",
                    payload={"project_root": tmp},
                )
            )
            client.container.event_queue.register(
                TaskEvent(
                    id="task-2",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    step_id="pipeline/followup",
                    depends_on=["task-1"],
                )
            )
            checkpoint = client.container.checkpoints().write(
                "run-1",
                "pipeline/report",
                "task-1",
                {
                    "status": "succeeded",
                },
            )
            client.container.runs().append_checkpoint("run-1", checkpoint)

            result = client.queue_list()
            task = next(item for item in result if item["id"] == "task-1")

            self.assertEqual(task["checkpoint_count"], 1)
            self.assertEqual(task["dependent_count"], 1)
            self.assertEqual(task["domain_view"]["kind"], "report")
            self.assertEqual(task["latest_checkpoint"]["task_id"], "task-1")
            self.assertEqual(task["priority"], 20)
            self.assertEqual(task["recovery_policy"], "fail_running")

    def test_queue_list_exposes_restored_task_error_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.event_queue.load_snapshot(
                {
                    "version": 1,
                    "saved_at": "2026-07-06T10:00:00+08:00",
                    "tasks": [
                        TaskEvent(
                            id="task-1",
                            type="diagnostic.echo",
                            pipeline_run_id="run-1",
                            step_id="pipeline/report",
                            state="running",
                        ).to_dict()
                    ],
                    "results": {"task-1": {"error": "previous failure"}},
                }
            )

            result = client.queue_list()
            task = next(item for item in result if item["id"] == "task-1")

            self.assertEqual(task["state"], "queued")
            self.assertEqual(task["restored_from"], "running")
            self.assertEqual(task["error"], "previous failure")

    def test_run_status_returns_step_graph_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.runs().create("run-1", {"source": "test"})
            client.container.event_queue.register(
                TaskEvent(
                    id="ingest-1",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    step_id="test/ingest",
                    state="succeeded",
                    payload={"project_root": tmp, "run_id": "run-1"},
                )
            )
            client.container.event_queue.register(
                TaskEvent(
                    id="combine-1",
                    type="pipeline.combine_ingest",
                    pipeline_run_id="run-1",
                    step_id="pipeline/combine_ingest",
                    depends_on=["ingest-1"],
                    payload={"project_root": tmp},
                )
            )
            artifact = client.container.checkpoints().write_artifact("run-1", "ingest/rss", "ingest-1", "items.json", [{"title": "A"}])
            checkpoint = client.container.checkpoints().write(
                "run-1",
                "test/ingest",
                "ingest-1",
                {
                    "status": "succeeded",
                    "output_refs": {"items": str(artifact)},
                    "stats": {"item_count": 1},
                },
            )
            client.container.runs().append_checkpoint("run-1", checkpoint)

            result = client.run_status("run-1")

            self.assertEqual(result["run"]["run_id"], "run-1")
            self.assertTrue(result["steps"])
            self.assertEqual({step["step_id"] for step in result["steps"]}, {"test/ingest", "pipeline/combine_ingest"})
            combine_step = next(step for step in result["steps"] if step["step_id"] == "pipeline/combine_ingest")
            self.assertEqual(combine_step["depends_on"], ["test/ingest"])
            self.assertEqual(combine_step["status"], "queued")
            ingest_step = next(step for step in result["steps"] if step["step_id"] == "test/ingest")
            self.assertEqual(ingest_step["status"], "succeeded")
            self.assertEqual(ingest_step["stats"]["item_count"], 1)
            self.assertEqual(result["steps"][0]["step_id"], "pipeline/combine_ingest")
            self.assertEqual(result["checkpoints"][0]["output_artifacts"][0]["name"], "items")
            self.assertTrue(any(artifact_info["path"] == str(artifact.resolve()) for artifact_info in result["artifacts"]))

    def test_queue_show_returns_domain_checkpoints_and_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.event_queue.register(
                TaskEvent(
                    id="task-1",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    step_id="test/task",
                    state="succeeded",
                    payload={"project_root": tmp, "run_id": "run-1"},
                )
            )
            client.container.event_queue.register(
                TaskEvent(
                    id="task-2",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    step_id="test/followup",
                    depends_on=["task-1"],
                    payload={"project_root": tmp},
                )
            )
            artifact = client.container.checkpoints().write_artifact("run-1", "ingest/rss", "task-1", "items.json", [{"title": "A"}])
            checkpoint = client.container.checkpoints().write(
                "run-1",
                "ingest/rss",
                "task-1",
                {
                    "status": "succeeded",
                    "output_refs": {"items": str(artifact)},
                },
            )
            client.container.runs().append_checkpoint("run-1", checkpoint)

            result = client.queue_show("task-1")

            self.assertEqual(result["domain_view"]["kind"], "task")
            self.assertEqual([item["id"] for item in result["dependents"]], ["task-2"])
            self.assertEqual(result["checkpoints"][0]["task_id"], "task-1")
            self.assertEqual(result["checkpoints"][0]["output_artifacts"][0]["name"], "items")
            self.assertTrue(any(artifact_info["path"] == str(artifact.resolve()) for artifact_info in result["artifacts"]))

    def test_run_status_exposes_step_callback_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.runs().create("run-1", {})
            client.container.runs().update(
                "run-1",
                steps=[
                    {
                        "step_id": "pipeline_ingest",
                        "status": "partial",
                        "callback_events": [
                            {
                                "step_id": "pipeline_ingest",
                                "handler": "on_task_blocked",
                                "event_task_id": "task-1",
                                "event_task_type": "web_source.run",
                                "event_step_id": "ingest/site_lists/site-1",
                                "changed_tasks": [{"task_id": "task-1", "before_state": "blocked", "after_state": "skipped"}],
                                "decisions": [{"action": "skip_blocked_task", "task_id": "task-1"}],
                            }
                        ],
                    }
                ],
            )

            result = client.run_status("run-1")

            step = next(step for step in result["steps"] if step["step_id"] == "pipeline_ingest")
            self.assertEqual(step["callback_events"][-1]["handler"], "on_task_blocked")
            self.assertEqual(step["callback_events"][-1]["changed_tasks"][-1]["after_state"], "skipped")


if __name__ == "__main__":
    unittest.main()
