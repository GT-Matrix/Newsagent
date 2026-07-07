from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.bootstrap import configure_services
from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository


class ClassifyExtractionNodeRuntimeTest(unittest.TestCase):
    def test_extraction_node_advances_by_child_task_callbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            input_path = project_root / "input.json"
            input_path.write_text(
                json.dumps(
                    [
                        {
                            "platform": "x",
                            "title": "Alpha raises round",
                            "url": "https://example.com/a",
                            "pubtime": None,
                            "scrape_date": "2026-07-07",
                        },
                        {
                            "platform": "x",
                            "title": "Alpha launches feature",
                            "url": "https://example.com/b",
                            "pubtime": None,
                            "scrape_date": "2026-07-07",
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            container = configure_services(project_root)
            runs = RunRepository(project_root)
            runs.create("run-1", {})

            container.event_queue.register_executor(
                "classify.embedding",
                lambda task: {
                    "batch_result": {
                        "key": task.payload["item_payload"]["key"],
                        "vector": [1.0, float(task.payload["item_payload"]["key"])],
                    }
                },
            )
            container.event_queue.register_executor(
                "classify.clustered_event_extraction.batch",
                lambda _task: {
                    "batch_result": {
                        "events": [
                            {
                                "event_label": "Alpha",
                                "event_summary": "Alpha summary",
                                "event_type": "company",
                                "key_entities": ["Alpha"],
                                "confidence": 92,
                                "source_news_ids": [0, 1],
                                "member_reasons": {"0": "same company", "1": "same company"},
                            }
                        ],
                        "discards": [],
                        "suspects": [],
                    }
                },
            )

            task = TaskEvent(
                id="classify-run-1-clustered-event-extraction",
                type="classify.clustered_event_extraction",
                pipeline_run_id="run-1",
                step_id="classify/clustered_event_extraction",
                payload={
                    "project_root": str(project_root),
                    "run_id": "run-1",
                    "input_path": str(input_path),
                    "write_fixed_outputs": False,
                },
            )

            container.event_queue.submit(task)

            parent = container.event_queue.get(task.id)
            self.assertEqual(parent.state, "succeeded")
            result = container.event_queue.result(task.id)
            self.assertEqual(result["node_stage"], "completed")

            checkpoint_path = Path(str(result["checkpoint_path"]))
            checkpoint_payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            progress_path = Path(str(checkpoint_payload["output_refs"]["classification_progress"]))
            progress_payload = json.loads(progress_path.read_text(encoding="utf-8"))

            self.assertEqual(progress_payload["meta"]["stage"], "after_clustered_event_extraction")
            self.assertEqual(len(progress_payload["events"]), 1)
            self.assertEqual(progress_payload["events"][0]["event_label"], "Alpha")


if __name__ == "__main__":
    unittest.main()
