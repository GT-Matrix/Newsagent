from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modnews.cli.local_client import LocalClient
from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.repository.source_config import SourceConfigRepository
from modnews.service.extraction.web_contract import WebJob
from modnews.service.extraction.tasks import run_web_source_task


class WebSourcePipelineTasksTest(unittest.TestCase):
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
            self.assertEqual(result["tasks"][-1]["type"], "pipeline.combine_ingest")

    def test_web_source_task_writes_ingest_checkpoint_for_pipeline_combine(self) -> None:
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

            with patch("modnews.service.extraction.tasks.WebExtractionOrchestrator.run_source", return_value=job):
                result = run_web_source_task(task)

            checkpoint_path = Path(str(result["checkpoint_path"]))
            checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["step_id"], "ingest/site_lists/site-1")
            self.assertEqual(checkpoint["stats"]["item_count"], 1)
            self.assertIn("items", checkpoint["output_refs"])
            self.assertEqual(RunRepository(project_root).get("run-1")["checkpoints"], [str(checkpoint_path)])


if __name__ == "__main__":
    unittest.main()
