from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.bootstrap import configure_services
from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository


class ClassifyMergeNodeRuntimeTest(unittest.TestCase):
    def test_merge_node_advances_by_child_task_callbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            input_path = project_root / "classification_progress.json"
            input_path.write_text(
                json.dumps(
                    {
                        "meta": {"stage": "after_clustered_event_extraction", "processed_candidates": 2, "total_candidates": 2},
                        "items": [
                            {
                                "platform": "x",
                                "title": "Alpha raises round",
                                "url": "https://example.com/a",
                                "pubtime": None,
                                "scrape_date": "2026-07-07",
                                "event_id": "evt_20260707_0001",
                                "event_label": "Alpha funding",
                                "event_confidence": 0.92,
                                "is_ai_relevant": True,
                                "relevance_score": 90,
                                "canonical_summary": "Alpha funding summary",
                                "entities": ["Alpha"],
                                "event_type": "company",
                                "classification_decision": "assign",
                                "classification_reason": "clustered title extraction",
                            },
                            {
                                "platform": "x",
                                "title": "Alpha launches feature",
                                "url": "https://example.com/b",
                                "pubtime": None,
                                "scrape_date": "2026-07-07",
                                "event_id": "evt_20260707_0002",
                                "event_label": "Alpha launch",
                                "event_confidence": 0.88,
                                "is_ai_relevant": True,
                                "relevance_score": 90,
                                "canonical_summary": "Alpha launch summary",
                                "entities": ["Alpha"],
                                "event_type": "company",
                                "classification_decision": "assign",
                                "classification_reason": "clustered title extraction",
                            },
                        ],
                        "events": [
                            {
                                "event_id": "evt_20260707_0001",
                                "event_label": "Alpha funding",
                                "member_count": 1,
                                "platforms": ["x"],
                                "latest_pubtime": None,
                                "representative_titles": ["Alpha raises round"],
                                "first_pubtime": None,
                                "confidence": 0.92,
                                "event_summary": "Alpha funding summary",
                                "event_type": "company",
                                "key_entities": ["Alpha"],
                                "source_news_ids": [0],
                                "last_llm_updated_at": "2026-07-07T00:00:00+08:00",
                            },
                            {
                                "event_id": "evt_20260707_0002",
                                "event_label": "Alpha launch",
                                "member_count": 1,
                                "platforms": ["x"],
                                "latest_pubtime": None,
                                "representative_titles": ["Alpha launches feature"],
                                "first_pubtime": None,
                                "confidence": 0.88,
                                "event_summary": "Alpha launch summary",
                                "event_type": "company",
                                "key_entities": ["Alpha"],
                                "source_news_ids": [1],
                                "last_llm_updated_at": "2026-07-07T00:00:00+08:00",
                            },
                        ],
                        "discarded": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            container = configure_services(project_root)
            RunRepository(project_root).create("run-1", {})

            container.event_queue.register_executor(
                "classify.embedding",
                lambda task: {
                    "batch_result": {
                        "key": task.payload["item_payload"]["key"],
                        "vector": [1.0, 2.0],
                    }
                },
            )
            container.event_queue.register_executor(
                "classify.clustered_event_merge.batch",
                lambda _task: {
                    "batch_result": {
                        "merge_groups": [
                            {
                                "target_event_id": "evt_20260707_0001",
                                "source_event_ids": ["evt_20260707_0002"],
                                "event_label": "Alpha combined",
                                "event_summary": "Alpha combined summary",
                            }
                        ]
                    }
                },
            )

            task = TaskEvent(
                id="classify-run-1-clustered-event-merge",
                type="classify.clustered_event_merge",
                pipeline_run_id="run-1",
                step_id="classify/clustered_event_merge",
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

            self.assertEqual(progress_payload["meta"]["stage"], "completed")
            self.assertEqual(progress_payload["meta"]["merged_event_count"], 1)
            self.assertEqual(len(progress_payload["events"]), 1)
            self.assertEqual(progress_payload["events"][0]["event_label"], "Alpha combined")

    def test_merge_node_accepts_extraction_checkpoint_directory_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            checkpoint_dir = project_root / "checkpoints" / "classify" / "clustered_event_extraction" / "one"
            checkpoint_dir.mkdir(parents=True)
            progress_path = checkpoint_dir / "classification_progress.json"
            progress_path.write_text(
                json.dumps(
                    {
                        "meta": {"stage": "after_clustered_event_extraction", "processed_candidates": 2, "total_candidates": 2},
                        "items": [
                            {
                                "platform": "x",
                                "title": "Alpha raises round",
                                "url": "https://example.com/a",
                                "pubtime": None,
                                "scrape_date": "2026-07-07",
                                "event_id": "evt_20260707_0001",
                                "event_label": "Alpha funding",
                                "event_confidence": 0.92,
                                "is_ai_relevant": True,
                                "relevance_score": 90,
                                "canonical_summary": "Alpha funding summary",
                                "entities": ["Alpha"],
                                "event_type": "company",
                                "classification_decision": "assign",
                                "classification_reason": "clustered title extraction",
                            },
                            {
                                "platform": "x",
                                "title": "Alpha launches feature",
                                "url": "https://example.com/b",
                                "pubtime": None,
                                "scrape_date": "2026-07-07",
                                "event_id": "evt_20260707_0002",
                                "event_label": "Alpha launch",
                                "event_confidence": 0.88,
                                "is_ai_relevant": True,
                                "relevance_score": 90,
                                "canonical_summary": "Alpha launch summary",
                                "entities": ["Alpha"],
                                "event_type": "company",
                                "classification_decision": "assign",
                                "classification_reason": "clustered title extraction",
                            },
                        ],
                        "events": [
                            {
                                "event_id": "evt_20260707_0001",
                                "event_label": "Alpha funding",
                                "member_count": 1,
                                "platforms": ["x"],
                                "latest_pubtime": None,
                                "representative_titles": ["Alpha raises round"],
                                "first_pubtime": None,
                                "confidence": 0.92,
                                "event_summary": "Alpha funding summary",
                                "event_type": "company",
                                "key_entities": ["Alpha"],
                                "source_news_ids": [0],
                                "last_llm_updated_at": "2026-07-07T00:00:00+08:00",
                            },
                            {
                                "event_id": "evt_20260707_0002",
                                "event_label": "Alpha launch",
                                "member_count": 1,
                                "platforms": ["x"],
                                "latest_pubtime": None,
                                "representative_titles": ["Alpha launches feature"],
                                "first_pubtime": None,
                                "confidence": 0.88,
                                "event_summary": "Alpha launch summary",
                                "event_type": "company",
                                "key_entities": ["Alpha"],
                                "source_news_ids": [1],
                                "last_llm_updated_at": "2026-07-07T00:00:00+08:00",
                            },
                        ],
                        "discarded": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (checkpoint_dir / "checkpoint.json").write_text(
                json.dumps(
                    {
                        "step_id": "classify/clustered_event_extraction",
                        "output_refs": {
                            "classification_progress": str(progress_path),
                            "news_with_events": str(progress_path),
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            container = configure_services(project_root)
            RunRepository(project_root).create("run-1", {})

            container.event_queue.register_executor(
                "classify.embedding",
                lambda task: {
                    "batch_result": {
                        "key": task.payload["item_payload"]["key"],
                        "vector": [1.0, 2.0],
                    }
                },
            )
            container.event_queue.register_executor(
                "classify.clustered_event_merge.batch",
                lambda _task: {
                    "batch_result": {
                        "merge_groups": [
                            {
                                "target_event_id": "evt_20260707_0001",
                                "source_event_ids": ["evt_20260707_0002"],
                                "event_label": "Alpha combined",
                                "event_summary": "Alpha combined summary",
                            }
                        ]
                    }
                },
            )

            task = TaskEvent(
                id="classify-run-1-clustered-event-merge",
                type="classify.clustered_event_merge",
                pipeline_run_id="run-1",
                step_id="classify/clustered_event_merge",
                payload={
                    "project_root": str(project_root),
                    "run_id": "run-1",
                    "input_path": str(checkpoint_dir),
                    "write_fixed_outputs": False,
                },
            )

            container.event_queue.submit(task)

            result = container.event_queue.result(task.id)
            checkpoint_path = Path(str(result["checkpoint_path"]))
            checkpoint_payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            merged_progress = json.loads(
                Path(str(checkpoint_payload["output_refs"]["classification_progress"])).read_text(encoding="utf-8")
            )
            self.assertEqual(merged_progress["meta"]["stage"], "completed")
            self.assertEqual(merged_progress["meta"]["merged_event_count"], 1)


if __name__ == "__main__":
    unittest.main()
