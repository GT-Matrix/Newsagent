from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modnews.app.server import create_app
from modnews.cli.commands.ingest import run_ingest
from modnews.cli.local_client import LocalClient
from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.repository.source_config import SourceConfigRepository
from modnews.service.extraction.repair_manager import RepairManager
from modnews.service.extraction.registry import registry_from_project
from modnews.service.extraction.web_source_runtime import WebSourceRuntimeFacade
from modnews.service.extraction.web_contract import WebJob
from modnews.service.ingest.queue_runtime import submit_ingest_step_run
from modnews.service.ingest.planner import plan_ingest_tasks
from modnews.service.ingest.steps.site_lists import SiteListsStep
from modnews.service.ingest.tasks import run_ingest_step_task


class WebSourcePipelineTasksTest(unittest.TestCase):
    def test_web_source_runtime_facade_submits_registered_queue_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            facade = WebSourceRuntimeFacade(
                project_root=project_root,
                queue=client.container.event_queue,
                queue_show=client.queue_show,
            )
            captured = []

            def execute(task):
                captured.append(task)
                return {"job": {"id": task.id, "source_id": task.payload["source_id"]}}

            client.container.event_queue.register_executor("web_source.run", execute)

            result = facade.run_source("site-1", {"limit": 3, "task_id": "manual-web-1"})

            self.assertTrue(result["ok"])
            self.assertEqual([task.type for task in captured], ["web_source.run"])
            self.assertEqual(captured[0].id, "manual-web-1")
            self.assertEqual(captured[0].payload["source_id"], "site-1")
            self.assertEqual(captured[0].payload["limit"], 3)
            self.assertEqual(result["task"]["id"], "manual-web-1")

    def test_submit_ingest_step_run_uses_planned_site_list_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            repo = SourceConfigRepository(project_root)
            repo.upsert_site(
                "site-1",
                {
                    "url": "https://example.com/1",
                    "name": "Site 1",
                    "extractor_id": "extractor-1",
                    "enabled": True,
                },
            )
            captured = []

            def execute(task):
                captured.append(task)
                return {"job": {"id": task.id, "source_id": task.payload["source_id"]}}

            client.container.event_queue.register_executor("web_source.run", execute)

            result = submit_ingest_step_run(
                project_root=project_root,
                queue=client.container.event_queue,
                queue_show=client.queue_show,
                step_id="site_lists",
                run_id="run-1",
                options={"sites": ["site-1"]},
                pipeline_descriptors=client.container.pipeline_manager.describe_steps(),
            )

            self.assertTrue(result["ok"])
            self.assertEqual([task.type for task in captured], ["web_source.run"])
            self.assertEqual(result["run_id"], "run-1")
            self.assertEqual(result["tasks"][0]["payload"]["source_id"], "site-1")

    def test_plan_ingest_tasks_delegates_site_lists_expansion_to_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            repo = SourceConfigRepository(project_root)
            repo.upsert_site(
                "site-1",
                {
                    "url": "https://example.com/1",
                    "name": "Site 1",
                    "extractor_id": "extractor-1",
                    "enabled": True,
                },
            )
            repo.upsert_site(
                "site-2",
                {
                    "url": "https://example.com/2",
                    "name": "Site 2",
                    "extractor_id": "extractor-2",
                    "enabled": True,
                },
            )

            tasks = plan_ingest_tasks(
                project_root=project_root,
                step_id="site_lists",
                run_id="run-1",
                options={"sites": ["site-2"], "limit_per_site": 7, "max_concurrency": 2},
            )

            self.assertEqual([task.type for task in tasks], ["web_source.run"])
            self.assertEqual(tasks[0].id, "web-source-run-1-site-2")
            self.assertEqual(tasks[0].payload["source_id"], "site-2")
            self.assertEqual(tasks[0].payload["limit"], 7)
            self.assertEqual(tasks[0].step_id, "ingest/site_lists/site-2")
            self.assertEqual(tasks[0].concurrency_key, "web_source")
            self.assertEqual(tasks[0].max_attempts, 1)

    def test_run_start_expands_site_lists_into_web_source_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            repo = SourceConfigRepository(project_root)
            repo.upsert_site(
                "site-1",
                {
                    "url": "https://example.com/1",
                    "name": "Site 1",
                    "extractor_id": "extractor-1",
                    "enabled": True,
                },
            )
            repo.upsert_site(
                "site-2",
                {
                    "url": "https://example.com/2",
                    "name": "Site 2",
                    "extractor_id": "extractor-2",
                    "enabled": True,
                },
            )

            result = client.run_start({"background": True, "disable_classification": True, "only": ["site_lists"]})

            task_types = [task["type"] for task in result["tasks"]]
            self.assertEqual(task_types.count("web_source.run"), 2)
            self.assertNotIn("ingest.run_step", task_types)
            self.assertNotIn("pipeline.combine_ingest", task_types)

    def test_web_source_task_writes_ingest_checkpoint_for_pipeline_combine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            repo = SourceConfigRepository(project_root)
            repo.upsert_site(
                "site-1",
                {
                    "url": "https://example.com/1",
                    "name": "Site 1",
                    "extractor_id": "extractor-1",
                    "enabled": True,
                },
            )
            output_dir = project_root / "var" / "web-source-test"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "items.json"
            output_path.write_text(
                json.dumps(
                    [
                        {
                            "platform": "site-1",
                            "title": "Example",
                            "url": "https://example.com/article",
                            "pubtime": None,
                            "scrape_date": "2026-07-03T00:00:00+08:00",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            task = TaskEvent(
                id="web-source-task-1",
                type="web_source.run",
                pipeline_run_id="run-1",
                step_id="ingest/site_lists/site-1",
                payload={"project_root": str(project_root), "run_id": "run-1", "source_id": "site-1", "limit": 10},
            )
            job = WebJob(
                id="job-1",
                source_id="site-1",
                source_name="Site 1",
                extractor_id="extractor-1",
                content_type="news",
                url="https://example.com/1",
                state="succeeded",
                created_at="2026-07-03T00:00:00+08:00",
                updated_at="2026-07-03T00:00:01+08:00",
                item_count=1,
                output_path=str(output_path),
            )
            RunRepository(project_root).create("run-1", {})

            with patch("modnews.service.extraction.web_source_node_runtime.WebExtractionOrchestrator.run_source", return_value=job):
                client.container.event_queue.submit(task)

            result = client.container.event_queue.result(task.id)

            checkpoint_path = Path(str(result["checkpoint_path"]))
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["step_id"], "ingest/site_lists/site-1")
            self.assertEqual(checkpoint["stats"]["item_count"], 1)
            self.assertIn("items", checkpoint["output_refs"])
            self.assertIn(str(checkpoint_path), RunRepository(project_root).get("run-1")["checkpoints"])

    def test_cli_ingest_site_lists_uses_web_source_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            repo = SourceConfigRepository(project_root)
            repo.upsert_site(
                "site-1",
                {
                    "url": "https://example.com/1",
                    "name": "Site 1",
                    "extractor_id": "extractor-1",
                    "enabled": True,
                },
            )
            repo.upsert_site(
                "site-2",
                {
                    "url": "https://example.com/2",
                    "name": "Site 2",
                    "extractor_id": "extractor-2",
                    "enabled": True,
                },
            )
            captured = []

            def execute(task):
                captured.append(task)
                return {"job": {"id": task.id}}

            client.container.event_queue.register_executor("web_source.run", execute)

            result = run_ingest(None, client, type("Args", (), {"step": "site_lists", "run_id": "run-1"})())

            self.assertTrue(result["ok"])
            self.assertEqual([task.type for task in captured], ["web_source.run", "web_source.run"])
            self.assertEqual([task["type"] for task in result["tasks"]], ["web_source.run", "web_source.run"])
            self.assertIn("ingest/site_lists/site-1", {step["step_id"] for step in result["run"]["steps"]})
            self.assertTrue(result["run"]["pipeline_steps"])
            self.assertEqual(result["run"]["pipeline_steps"][0]["step_id"], "pipeline_ingest")

    def test_cli_ingest_site_lists_supports_per_source_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            repo = SourceConfigRepository(project_root)
            repo.upsert_site(
                "site-1",
                {
                    "url": "https://example.com/1",
                    "name": "Site 1",
                    "extractor_id": "extractor-1",
                    "enabled": True,
                },
            )
            repo.upsert_site(
                "site-2",
                {
                    "url": "https://example.com/2",
                    "name": "Site 2",
                    "extractor_id": "extractor-2",
                    "enabled": True,
                },
            )
            captured = []

            def execute(task):
                captured.append(task)
                return {"job": {"id": task.id, "source_id": task.payload["source_id"]}}

            client.container.event_queue.register_executor("web_source.run", execute)

            result = run_ingest(
                None,
                client,
                type(
                    "Args",
                    (),
                    {
                        "step": "site_lists",
                        "run_id": "run-1",
                        "sites": ["site-2"],
                        "limit_per_site": 7,
                        "max_concurrency": 2,
                    },
                )(),
            )

            self.assertTrue(result["ok"])
            self.assertEqual([task.payload["source_id"] for task in captured], ["site-2"])
            self.assertEqual(result["tasks"][0]["payload"]["limit"], 7)
            self.assertIn("ingest/site_lists/site-2", {step["step_id"] for step in result["run"]["steps"]})

    def test_api_ingest_site_lists_uses_web_source_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            app = create_app(project_root)
            repo = SourceConfigRepository(project_root)
            repo.upsert_site(
                "site-1",
                {
                    "url": "https://example.com/1",
                    "name": "Site 1",
                    "extractor_id": "extractor-1",
                    "enabled": True,
                },
            )
            repo.upsert_site(
                "site-2",
                {
                    "url": "https://example.com/2",
                    "name": "Site 2",
                    "extractor_id": "extractor-2",
                    "enabled": True,
                },
            )
            with app.app_context():
                from modnews.app.context import local_client

                client = local_client()
                captured = []

                def execute(task):
                    captured.append(task)
                    return {"job": {"id": task.id}}

                client.container.event_queue.register_executor("web_source.run", execute)
                response = app.test_client().post("/api/ingest/run", json={"step_id": "site_lists", "run_id": "run-1"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual([task.type for task in captured], ["web_source.run", "web_source.run"])
            self.assertEqual([task["type"] for task in response.get_json()["tasks"]], ["web_source.run", "web_source.run"])
            self.assertTrue(response.get_json()["run"]["steps"])

    def test_direct_legacy_site_lists_ingest_task_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            task = TaskEvent(
                id="legacy-site-lists-1",
                type="ingest.run_step",
                pipeline_run_id="run-1",
                step_id="ingest/site_lists",
                payload={"project_root": str(project_root), "run_id": "run-1", "step_id": "site_lists"},
            )

            with self.assertRaisesRegex(ValueError, "site_lists must be planned as per-source web_source.run tasks"):
                run_ingest_step_task(task)

    def test_direct_site_lists_step_run_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            repo = SourceConfigRepository(project_root)
            repo.upsert_site(
                "site-1",
                {
                    "url": "https://example.com/1",
                    "name": "Site 1",
                    "extractor_id": "extractor-1",
                    "enabled": True,
                },
            )

            ctx = PipelineContext.create(load_config(project_root=project_root))

            with self.assertRaisesRegex(ValueError, "site_lists is task-only"):
                SiteListsStep().run(ctx)

    def test_web_source_node_retries_scrape_after_repair_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            repair_manager = RepairManager(project_root, registry_from_project(project_root))
            repair_item = repair_manager.create_task("site-1", reason="auto repair")
            repo = SourceConfigRepository(project_root)
            repo.upsert_site(
                "site-1",
                {
                    "url": "https://example.com/1",
                    "name": "Site 1",
                    "extractor_id": "extractor-1",
                    "enabled": True,
                },
            )
            output_dir = project_root / "var" / "web-source-test"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "items.json"
            output_path.write_text(
                json.dumps(
                    [
                        {
                            "platform": "site-1",
                            "title": "Example repaired",
                            "url": "https://example.com/article",
                            "pubtime": None,
                            "scrape_date": "2026-07-03T00:00:00+08:00",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            RunRepository(project_root).create("run-1", {})

            attempts = {"count": 0}

            def scrape_executor(task: TaskEvent) -> dict[str, object]:
                attempts["count"] += 1
                if attempts["count"] == 1:
                    return {
                        "job": {
                            "id": "job-1",
                            "source_id": "site-1",
                            "source_name": "Site 1",
                            "extractor_id": "extractor-1",
                            "content_type": "news",
                            "url": "https://example.com/1",
                            "state": "repairing",
                            "created_at": "2026-07-03T00:00:00+08:00",
                            "updated_at": "2026-07-03T00:00:01+08:00",
                            "attempts": 1,
                            "max_attempts": 3,
                            "item_count": 0,
                            "repair_task_id": repair_item.id,
                        },
                        "source_id": "site-1",
                    }
                return {
                    "job": {
                        "id": "job-2",
                        "source_id": "site-1",
                        "source_name": "Site 1",
                        "extractor_id": "extractor-1",
                        "content_type": "news",
                        "url": "https://example.com/1",
                        "state": "succeeded",
                        "created_at": "2026-07-03T00:00:02+08:00",
                        "updated_at": "2026-07-03T00:00:03+08:00",
                        "attempts": 1,
                        "max_attempts": 3,
                        "item_count": 1,
                        "output_path": str(output_path),
                    },
                    "source_id": "site-1",
                }

            client.container.event_queue.register_executor("web_source.scrape", scrape_executor)
            client.container.event_queue.register_executor(
                "extractor.repair.codex",
                lambda task: {
                    "repair_task": {
                        "id": task.payload["repair_task_id"],
                        "status": "succeeded",
                    }
                },
            )

            task = TaskEvent(
                id="web-source-task-1",
                type="web_source.run",
                pipeline_run_id="run-1",
                step_id="ingest/site_lists/site-1",
                payload={"project_root": str(project_root), "run_id": "run-1", "source_id": "site-1", "limit": 10},
            )

            client.container.event_queue.submit(task)

            self.assertEqual(client.container.event_queue.get(task.id).state, "succeeded")
            self.assertEqual(attempts["count"], 2)
            result = client.container.event_queue.result(task.id)
            checkpoint_path = Path(str(result["checkpoint_path"]))
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["step_id"], "ingest/site_lists/site-1")
            self.assertEqual(checkpoint["stats"]["item_count"], 1)
            repair_tasks = [item for item in client.container.event_queue.list() if item.type == "extractor.repair.codex"]
            self.assertEqual(len(repair_tasks), 1)
            self.assertEqual(repair_tasks[0].payload["repair_task_id"], repair_item.id)

    def test_blocked_web_source_task_auto_skips_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            client = LocalClient(project_root)
            client.container.event_queue.register_executor("diagnostic.echo", lambda _task: {"value": "ok"})
            client.container.event_queue.register_executor(
                "web_source.scrape",
                lambda _task: {
                    "job": {
                        "id": "job-1",
                        "source_id": "site-1",
                        "source_name": "Site 1",
                        "extractor_id": "extractor-1",
                        "content_type": "news",
                        "url": "https://example.com/1",
                        "state": "skipped_unrepairable",
                        "created_at": "2026-07-03T00:00:00+08:00",
                        "updated_at": "2026-07-03T00:00:01+08:00",
                        "attempts": 1,
                        "max_attempts": 3,
                        "item_count": 0,
                        "error_type": "blocked",
                        "error": "captcha required",
                    },
                    "source_id": "site-1",
                },
            )
            client.container.event_queue.register(
                TaskEvent(
                    id="web-source-task-1",
                    type="web_source.run",
                    pipeline_run_id="run-1",
                    step_id="ingest/site_lists/site-1",
                    payload={"project_root": str(project_root), "source_id": "site-1"},
                )
            )
            client.container.event_queue.register(
                TaskEvent(
                    id="combine",
                    type="diagnostic.echo",
                    pipeline_run_id="run-1",
                    depends_on=["web-source-task-1"],
                )
            )

            client.container.event_queue.drain_ready()

            self.assertEqual(client.container.event_queue.get("web-source-task-1").state, "skipped")
            self.assertEqual(
                [action["action"] for action in client.container.event_queue.result("web-source-task-1")["repair_queue_actions"]],
                ["skip_blocked_task"],
            )
            self.assertEqual(client.container.event_queue.get("combine").state, "succeeded")


if __name__ == "__main__":
    unittest.main()
