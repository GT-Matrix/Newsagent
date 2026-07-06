from __future__ import annotations

from datetime import datetime, timedelta
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
            self.assertEqual(result[0]["pipeline_steps_summary"]["by_status"]["blocked"], 1)
            self.assertEqual(result[0]["pipeline_steps_summary"]["by_status"]["idle"], 3)
            self.assertEqual(result[0]["latest_checkpoint"]["task_id"], "task-1")
            self.assertEqual(result[0]["artifact_count"], 1)

    def test_queue_list_exposes_blocked_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.event_queue.register(TaskEvent(id="dep-1", type="diagnostic.echo", state="failed"))
            client.container.event_queue.register(
                TaskEvent(
                    id="task-1",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    step_id="pipeline/report",
                    state="blocked",
                    depends_on=["dep-1"],
                )
            )

            result = client.queue_list()
            task = next(item for item in result if item["id"] == "task-1")

            self.assertEqual(task["blocked_reason"], "dependency dep-1 ended as failed")
            self.assertEqual(task["blocked_details"], {"kind": "dependency", "dependency_id": "dep-1", "dependency_state": "failed"})

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
                    "output_refs": {
                        "report_markdown": str(project_root / "data" / "output" / "daily_report.md"),
                        "report_debug_markdown": str(project_root / "data" / "output" / "daily_report_debug.md"),
                        "report_events": str(project_root / "data" / "output" / "enriched_events.json"),
                        "report_trend_summary": str(project_root / "data" / "output" / "trend_summary.json"),
                    },
                },
            )
            client.container.runs().append_checkpoint("run-1", checkpoint)

            result = client.queue_list()
            task = next(item for item in result if item["id"] == "task-1")

            self.assertEqual(task["checkpoint_count"], 1)
            self.assertEqual(task["dependent_count"], 1)
            self.assertEqual(task["child_count"], 0)
            self.assertEqual(task["task_group_size"], 0)
            self.assertIsNone(task["task_group_summary"])
            self.assertEqual(task["domain_view"]["kind"], "report")
            self.assertEqual(task["title"], "Generate report")
            self.assertEqual(task["log_kind"], "report")
            self.assertEqual(task["detail_kind"], "report_task")
            self.assertEqual(task["related_run_id"], "run-1")
            self.assertEqual(task["related_step_id"], "pipeline/report")
            self.assertIsNone(task["related_source_id"])
            self.assertEqual(task["retry_state"]["status"], "attempted")
            self.assertFalse(task["blocked_state"]["blocked"])
            self.assertEqual(task["summary"], "selected_count=1")
            self.assertEqual(task["latest_checkpoint"]["task_id"], "task-1")
            self.assertEqual(task["priority"], 20)
            self.assertEqual(task["recovery_policy"], "fail_running")
            self.assertEqual(task["domain_view"]["checkpoint_path"], str(checkpoint))
            self.assertEqual(task["domain_view"]["input_refs"], {})
            self.assertEqual(task["domain_view"]["output_refs"]["report_markdown"], str(project_root / "data" / "output" / "daily_report.md"))
            self.assertEqual(
                [item["target_key"] for item in task["domain_view"]["publish_targets"]],
                ["report_markdown", "report_debug_markdown", "report_events", "report_trend_summary"],
            )

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

    def test_queue_list_exposes_retry_window_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            next_attempt_at = (datetime.now().astimezone() + timedelta(minutes=2)).isoformat(timespec="seconds")
            client.container.event_queue.register(
                TaskEvent(
                    id="task-1",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    step_id="pipeline/report",
                    state="waiting",
                    retry_backoff_seconds=120,
                    next_attempt_at=next_attempt_at,
                    status_reason=f"waiting until retry window {next_attempt_at}",
                )
            )
            client.container.event_queue._results["task-1"] = {  # type: ignore[attr-defined]
                "retry_scheduled": True,
                "retry_delay_seconds": 120,
                "next_attempt_at": next_attempt_at,
            }

            result = client.queue_list()
            task = next(item for item in result if item["id"] == "task-1")

            self.assertEqual(task["waiting_reason"], f"waiting until retry window {next_attempt_at}")
            self.assertEqual(task["waiting_details"], {"kind": "retry_window", "next_attempt_at": next_attempt_at})
            self.assertTrue(task["retry_scheduled"])
            self.assertEqual(task["retry_delay_seconds"], 120)
            self.assertEqual(task["scheduled_next_attempt_at"], next_attempt_at)

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
                    step_id="ingest/rss",
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
            self.assertTrue(result["steps"])
            self.assertTrue(result["pipeline_steps"])
            self.assertEqual({step["step_id"] for step in result["steps"]}, {"ingest/rss", "pipeline/combine_ingest"})
            combine_step = next(step for step in result["steps"] if step["step_id"] == "pipeline/combine_ingest")
            self.assertEqual(combine_step["depends_on"], ["ingest/rss"])
            self.assertEqual(combine_step["status"], "queued")
            ingest_step = next(step for step in result["steps"] if step["step_id"] == "ingest/rss")
            self.assertEqual(ingest_step["status"], "succeeded")
            self.assertEqual(ingest_step["stats"]["item_count"], 1)
            self.assertEqual([step["step_id"] for step in result["steps"]], ["ingest/rss", "pipeline/combine_ingest"])
            pipeline_ingest = next(step for step in result["pipeline_steps"] if step["step_id"] == "pipeline_ingest")
            self.assertEqual(pipeline_ingest["status"], "succeeded")
            self.assertEqual(pipeline_ingest["concrete_step_ids"], ["ingest/rss"])
            pipeline_combine = next(step for step in result["pipeline_steps"] if step["step_id"] == "pipeline_combine_ingest")
            self.assertEqual(pipeline_combine["depends_on"], ["pipeline_ingest"])
            self.assertEqual(pipeline_combine["status"], "queued")
            self.assertEqual(pipeline_combine["concrete_step_ids"], ["pipeline/combine_ingest"])
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
            self.assertEqual(result["title"], "diagnostic.echo")
            self.assertEqual(result["log_kind"], "task")
            self.assertEqual(result["detail_kind"], "task")
            self.assertEqual(result["retry_state"]["max_attempts"], 1)
            self.assertFalse(result["blocked_state"]["blocked"])
            self.assertGreaterEqual(len(result["attempt_history"]), 0)
            self.assertEqual([item["id"] for item in result["dependents"]], ["task-2"])
            self.assertEqual(result["children"], [])
            self.assertEqual(result["task_group_members"], [])
            self.assertIsNone(result["task_group_summary"])
            self.assertEqual(result["checkpoints"][0]["task_id"], "task-1")
            self.assertEqual(result["checkpoints"][0]["output_artifacts"][0]["name"], "items")
            self.assertTrue(any(artifact_info["path"] == str(artifact.resolve()) for artifact_info in result["artifacts"]))

    def test_checkpoints_list_exposes_task_refs_and_resume_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            artifact = client.container.checkpoints().write_artifact("run-1", "pipeline/combine_ingest", "task-1", "items.json", [{"title": "A"}])
            checkpoint = client.container.checkpoints().write(
                "run-1",
                "pipeline/combine_ingest",
                "task-1",
                {
                    "status": "succeeded",
                    "output_refs": {"items": str(artifact)},
                },
            )

            result = client.checkpoints_list("run-1")

            item = next(row for row in result if row["path"] == str(checkpoint))
            self.assertEqual(
                item["task_refs"],
                {"run_id": "run-1", "step_id": "pipeline/combine_ingest", "task_id": "task-1"},
            )
            self.assertEqual(item["resume_hint"]["kind"], "classify")
            self.assertEqual(item["resume_hint"]["accepted_inputs"], ["checkpoint_dir", "checkpoint_json"])
            self.assertIn("--run-id run-1", item["resume_hint"]["cli_command"])
            self.assertIn("--input", item["resume_hint"]["cli_command"])

    def test_classify_checkpoint_resume_hint_points_to_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            artifact = client.container.checkpoints().write_artifact(
                "run-1",
                "classify/clustered_event_merge",
                "task-1",
                "classification_progress.json",
                {"items": [], "events": [], "discarded": [], "meta": {"stage": "done"}},
            )
            checkpoint = client.container.checkpoints().write(
                "run-1",
                "classify/clustered_event_merge",
                "task-1",
                {
                    "status": "succeeded",
                    "output_refs": {"classification_progress": str(artifact)},
                },
            )

            result = client.checkpoints_list("run-1")

            item = next(row for row in result if row["path"] == str(checkpoint))
            self.assertEqual(item["resume_hint"]["kind"], "report")
            self.assertIn("report generate", item["resume_hint"]["cli_command"])

    def test_checkpoints_list_exposes_callback_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            artifact = client.container.checkpoints().write_artifact("run-1", "ingest/site_lists/site-1", "task-1", "items.json", [{"title": "A"}])
            checkpoint = client.container.checkpoints().write(
                "run-1",
                "ingest/site_lists/site-1",
                "task-1",
                {
                    "status": "blocked",
                    "output_refs": {"items": str(artifact)},
                },
            )
            client.container.runs().create("run-1", {})
            client.container.runs().update(
                "run-1",
                step_callback_events=[
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
            )

            result = client.checkpoints_list("run-1")

            item = next(row for row in result if row["path"] == str(checkpoint))
            self.assertEqual(item["callback_summary"]["event_count"], 1)
            self.assertEqual(item["callback_summary"]["latest_handler"], "on_task_blocked")
            self.assertEqual(item["callback_summary"]["latest_event_task_type"], "web_source.run")
            self.assertEqual(item["callback_summary"]["decision_actions"], ["skip_blocked_task"])

    def test_queue_show_exposes_child_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.event_queue.register(
                TaskEvent(
                    id="parent-1",
                    type="classify.clustered_event_extraction",
                    pipeline_run_id="run-1",
                    step_id="classify/clustered_event_extraction",
                )
            )
            client.container.event_queue.register(
                TaskEvent(
                    id="child-1",
                    type="classify.embedding",
                    pipeline_run_id="run-1",
                    step_id="classify/clustered_event_extraction",
                    parent_task_id="parent-1",
                    task_group_id="group-1",
                )
            )

            result = client.queue_show("parent-1")

            self.assertEqual([item["id"] for item in result["children"]], ["child-1"])

    def test_queue_show_exposes_task_group_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.event_queue.register(
                TaskEvent(
                    id="child-1",
                    type="classify.embedding",
                    pipeline_run_id="run-1",
                    step_id="classify/clustered_event_extraction",
                    parent_task_id="parent-1",
                    task_group_id="group-1",
                )
            )
            client.container.event_queue.register(
                TaskEvent(
                    id="child-2",
                    type="classify.embedding",
                    pipeline_run_id="run-1",
                    step_id="classify/clustered_event_extraction",
                    parent_task_id="parent-1",
                    task_group_id="group-1",
                )
            )

            result = client.queue_show("child-1")
            listed = [item["id"] for item in result["task_group_members"]]

            self.assertEqual(listed, ["child-1", "child-2"])
            self.assertEqual(next(item for item in result["task_group_members"] if item["id"] == "child-1")["task_group_id"], "group-1")
            self.assertEqual(
                result["task_group_summary"],
                {
                    "task_group_id": "group-1",
                    "size": 2,
                    "by_state": {"queued": 2},
                    "active": 2,
                    "terminal": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "blocked": 0,
                    "member_ids": ["child-1", "child-2"],
                },
            )

    def test_queue_show_exposes_attempt_history_and_related_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)

            result = client.queue_echo("task-logs-1", {"message": "hello"})

            self.assertEqual(result["title"], "diagnostic.echo")
            self.assertEqual(result["summary"], "completed")
            self.assertEqual(result["log_kind"], "task")
            self.assertEqual(result["detail_kind"], "task")
            self.assertEqual(result["related_artifacts"], [])
            self.assertIsNone(result["related_checkpoint_path"])
            history_types = [item["type"] for item in result["attempt_history"]]
            self.assertIn("task.registered", history_types)
            self.assertIn("task.started", history_types)
            self.assertIn("task.completed", history_types)

    def test_queue_show_exposes_classify_domain_view_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            task = TaskEvent(
                id="classify-1",
                type="classify.clustered_event_merge",
                pipeline_run_id="run-1",
                step_id="classify/clustered_event_merge",
                payload={"project_root": tmp, "run_id": "run-1"},
            )
            client.container.event_queue.register(task)
            artifact = client.container.checkpoints().write_artifact(
                "run-1",
                "classify/clustered_event_merge",
                "classify-1",
                "classification_progress.json",
                {"items": [], "events": [], "discarded": [], "meta": {"stage": "done"}},
            )
            checkpoint = client.container.checkpoints().write(
                "run-1",
                "classify/clustered_event_merge",
                "classify-1",
                {
                    "status": "succeeded",
                    "input_refs": {"items": str(project_root / "output" / "combined_news.json")},
                    "output_refs": {"classification_progress": str(artifact)},
                    "stats": {"event_count": 3, "merged_event_count": 2},
                },
            )
            client.container.runs().create("run-1", {})
            client.container.runs().append_checkpoint("run-1", checkpoint)

            result = client.queue_show("classify-1")

            self.assertEqual(result["domain_view"]["kind"], "classify")
            self.assertEqual(result["domain_view"]["stage"], "clustered_event_merge")
            self.assertEqual(result["domain_view"]["checkpoint_path"], str(checkpoint))
            self.assertEqual(result["domain_view"]["input_refs"]["items"], str(project_root / "output" / "combined_news.json"))
            self.assertEqual(result["domain_view"]["output_refs"]["classification_progress"], str(artifact))
            self.assertEqual(result["domain_view"]["resume_hint"]["kind"], "report")
            self.assertEqual(result["domain_view"]["stats"]["event_count"], 3)
            self.assertEqual(
                [item["target_key"] for item in result["domain_view"]["publish_targets"]],
                ["checkpoint"],
            )
            self.assertEqual(result["domain_view"]["artifacts"][0]["name"], "classification_progress")

    def test_queue_show_exposes_pipeline_combine_domain_view_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            task = TaskEvent(
                id="combine-1",
                type="pipeline.combine_ingest",
                pipeline_run_id="run-1",
                step_id="pipeline/combine_ingest",
                payload={"project_root": tmp, "run_id": "run-1"},
            )
            client.container.event_queue.register(task)
            artifact = client.container.checkpoints().write_artifact("run-1", "pipeline/combine_ingest", "combine-1", "items.json", [{"title": "A"}])
            checkpoint = client.container.checkpoints().write(
                "run-1",
                "pipeline/combine_ingest",
                "combine-1",
                {
                    "status": "succeeded",
                    "input_refs": {"ingest/rss": str(project_root / "runtime" / "rss-items.json")},
                    "output_refs": {"items": str(artifact)},
                },
            )
            client.container.runs().create("run-1", {})
            client.container.runs().append_checkpoint("run-1", checkpoint)

            result = client.queue_show("combine-1")

            self.assertEqual(result["domain_view"]["kind"], "pipeline_combine_ingest")
            self.assertEqual(result["domain_view"]["checkpoint_path"], str(checkpoint))
            self.assertEqual(result["domain_view"]["output_refs"]["items"], str(artifact))
            self.assertEqual(result["domain_view"]["resume_hint"]["kind"], "classify")
            self.assertEqual(result["domain_view"]["publish_targets"][0]["target_key"], "combined_news")
            self.assertEqual(result["domain_view"]["artifacts"][0]["name"], "items")

    def test_queue_show_exposes_classify_embedding_batch_domain_view_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            task = TaskEvent(
                id="classify.embedding:group-1:1",
                type="classify.embedding",
                pipeline_run_id="run-1",
                step_id="classify/clustered_event_extraction",
                parent_task_id="classify-parent-1",
                task_group_id="group-1",
                payload={
                    "project_root": tmp,
                    "run_id": "run-1",
                    "parent_task_id": "classify-parent-1",
                    "parent_task_type": "classify.clustered_event_extraction",
                    "task_group_id": "group-1",
                    "labels": {"stage": "clustered"},
                    "batch": {
                        "task_type": "classify.embedding",
                        "task_name": "classify.embedding[1/2]",
                        "concurrency_key": "classify.embedding",
                        "max_concurrency": 2,
                        "queue_task_type": "classify.embedding",
                        "item_index": 0,
                        "item_count": 2,
                    },
                    "item_payload": {"key": "evt_1", "text": "hello"},
                },
            )
            client.container.event_queue.register(task)
            client.container.event_queue._results[task.id] = {  # type: ignore[attr-defined]
                "batch_result": {"key": "evt_1", "vector": [1.0, 2.0]},
            }

            result = client.queue_show(task.id)

            self.assertEqual(result["domain_view"]["kind"], "classify")
            self.assertEqual(result["domain_view"]["parent_task_id"], "classify-parent-1")
            self.assertEqual(result["domain_view"]["parent_task_type"], "classify.clustered_event_extraction")
            self.assertEqual(result["domain_view"]["task_group_id"], "group-1")
            self.assertEqual(result["domain_view"]["labels"], {"stage": "clustered"})
            self.assertEqual(result["domain_view"]["batch"]["task_name"], "classify.embedding[1/2]")
            self.assertEqual(result["domain_view"]["item_payload_kind"], "dict")
            self.assertEqual(result["domain_view"]["item_payload_size"], 2)
            self.assertEqual(result["domain_view"]["batch_result_keys"], ["key", "vector"])

    def test_queue_show_exposes_classify_relevance_batch_domain_view_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            task = TaskEvent(
                id="classify.batch_relevance:group-1:1",
                type="classify.batch_relevance",
                pipeline_run_id="run-1",
                step_id="classify/relevance",
                parent_task_id="classify-parent-2",
                task_group_id="group-1",
                payload={
                    "project_root": tmp,
                    "run_id": "run-1",
                    "parent_task_id": "classify-parent-2",
                    "parent_task_type": "classify.clustered_event_extraction",
                    "task_group_id": "group-1",
                    "labels": {"stage": "relevance"},
                    "batch": {
                        "task_type": "classify.batch_relevance",
                        "task_name": "classify.batch_relevance[1/2]",
                        "concurrency_key": "classify.llm",
                        "max_concurrency": 2,
                        "queue_task_type": "classify.batch_relevance",
                        "item_index": 0,
                        "item_count": 2,
                        "batch_index": 1,
                        "batch_count": 2,
                    },
                    "item_payload": [{"index": 0, "title": "hello"}],
                },
            )
            client.container.event_queue.register(task)
            client.container.event_queue._results[task.id] = {  # type: ignore[attr-defined]
                "batch_result": {"items": [{"index": 0, "status": "candidate"}]},
            }

            result = client.queue_show(task.id)

            self.assertEqual(result["domain_view"]["kind"], "classify")
            self.assertEqual(result["domain_view"]["labels"], {"stage": "relevance"})
            self.assertEqual(result["domain_view"]["batch"]["batch_index"], 1)
            self.assertEqual(result["domain_view"]["batch"]["batch_count"], 2)
            self.assertEqual(result["domain_view"]["item_payload_kind"], "list")
            self.assertEqual(result["domain_view"]["item_payload_size"], 1)
            self.assertEqual(result["domain_view"]["batch_result_keys"], ["items"])

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
