from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modnews.cli.local_client import LocalClient
from modnews.core.task import TaskEvent


class PipelineReadModelTest(unittest.TestCase):
    def test_run_status_returns_step_graph_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.runs().create("run-1", {"source": "test"})
            client.container.event_queue.register_executor("diagnostic.echo", lambda _task: {"value": "ok"})
            client.container.event_queue.submit(
                TaskEvent(
                    id="ingest-1",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    step_id="ingest/rss",
                    payload={"project_root": tmp},
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
                "ingest/rss",
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
            self.assertTrue(result["run"]["steps"])
            self.assertEqual({step["step_id"] for step in result["steps"]}, {"ingest/rss", "pipeline/combine_ingest"})
            combine_step = next(step for step in result["steps"] if step["step_id"] == "pipeline/combine_ingest")
            self.assertEqual(combine_step["depends_on"], ["ingest/rss"])
            self.assertEqual(combine_step["status"], "queued")
            ingest_step = next(step for step in result["steps"] if step["step_id"] == "ingest/rss")
            self.assertEqual(ingest_step["status"], "succeeded")
            self.assertEqual(ingest_step["stats"]["item_count"], 1)
            self.assertEqual(result["run"]["steps"][0]["step_id"], "ingest/rss")
            self.assertEqual(result["checkpoints"][0]["output_artifacts"][0]["name"], "items")
            self.assertTrue(any(artifact_info["path"] == str(artifact.resolve()) for artifact_info in result["artifacts"]))

    def test_queue_show_returns_domain_checkpoints_and_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.event_queue.register_executor("diagnostic.echo", lambda _task: {"value": "ok"})
            client.container.event_queue.submit(
                TaskEvent(
                    id="task-1",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    step_id="ingest/rss",
                    payload={"project_root": tmp},
                )
            )
            client.container.event_queue.register(
                TaskEvent(
                    id="task-2",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    step_id="pipeline/combine_ingest",
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
            self.assertEqual(result["dependents"][0]["id"], "task-2")
            self.assertEqual(result["checkpoints"][0]["task_id"], "task-1")
            self.assertEqual(result["checkpoints"][0]["output_artifacts"][0]["name"], "items")
            self.assertTrue(any(log["type"] == "task.completed" for log in result["logs"]))
            self.assertTrue(any(artifact_info["path"] == str(artifact.resolve()) for artifact_info in result["artifacts"]))


if __name__ == "__main__":
    unittest.main()
