from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.core.models import EventRecord, NewsItem
from modnews.service.classify.checkpoint import write_run_output_artifacts
from modnews.service.classify.io import resolve_input_path, resolve_resume_checkpoint_path, resolve_task_resume_checkpoint_path
from modnews.service.classify.runner import ClassifyRunResult, ClassifyStepResult
from modnews.service.classify.state_codec import decode_resume_state
from modnews.service.classify.state import ClassifyState
from modnews.service.classify.task_registry import get_registered_classify_task
from modnews.service.classify.task_checkpoint import write_classify_task_checkpoint
from modnews.service.classify.task_result import build_classify_task_snapshot
from modnews.service.classify.types import DiscardedRecord
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.repository.runs import RunRepository
from modnews.core.config import load_config
from modnews.core.task import TaskEvent


class ClassifyCheckpointArtifactsTest(unittest.TestCase):
    def test_writes_classify_artifacts_into_checkpoint_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            manager = CheckpointManager(project_root)
            item = NewsItem(platform="x", title="t", url="https://example.com", pubtime=None, scrape_date="2026-07-03")
            event = EventRecord(
                event_id="e1",
                event_label="label",
                member_count=1,
                platforms=["x"],
                latest_pubtime=None,
                representative_titles=["t"],
            )
            discarded = [DiscardedRecord(index=1, title="drop", platform="x", stage="test", reason="no")]

            refs = write_run_output_artifacts(
                manager,
                "run-1",
                "classify/test",
                "task-1",
                [item],
                [event],
                discarded,
                {"stage": "test"},
            )
            checkpoint_path = manager.write(
                "run-1",
                "classify/test",
                "task-1",
                {
                    "run_id": "run-1",
                    "step_id": "classify/test",
                    "task_id": "task-1",
                    "status": "succeeded",
                    "output_refs": refs,
                    "stats": {},
                    "error": None,
                },
            )

            self.assertEqual({Path(value).parent for value in refs.values()}, {checkpoint_path.parent})
            self.assertEqual(json.loads(Path(refs["news_with_events"]).read_text(encoding="utf-8"))[0]["title"], "t")
            self.assertEqual(json.loads(Path(refs["classification_progress"]).read_text(encoding="utf-8"))["meta"]["stage"], "test")

    def test_resume_checkpoint_prefers_run_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            manager = CheckpointManager(project_root)
            runs = RunRepository(project_root)
            runs.create("run-1", {})
            fixed_path = project_root / "output" / "classification_progress.json"
            fixed_path.parent.mkdir(parents=True)
            fixed_path.write_text(json.dumps({"meta": {"stage": "fixed"}}, ensure_ascii=False), encoding="utf-8")

            refs = manager.write_artifact(
                "run-1",
                "classify/test",
                "task-1",
                "classification_progress.json",
                {"meta": {"stage": "artifact"}},
            )
            checkpoint_path = manager.write(
                "run-1",
                "classify/test",
                "task-1",
                {
                    "run_id": "run-1",
                    "step_id": "classify/test",
                    "task_id": "task-1",
                    "status": "succeeded",
                    "output_refs": {"classification_progress": str(refs)},
                    "stats": {},
                    "error": None,
                },
            )
            runs.update("run-1", checkpoints=[str(checkpoint_path)])

            self.assertEqual(resolve_resume_checkpoint_path(project_root, "run-1", fixed_path), refs.resolve())

    def test_resume_checkpoint_falls_back_to_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            fixed_path = project_root / "output" / "classification_progress.json"
            fixed_path.parent.mkdir(parents=True)
            fixed_path.write_text(json.dumps({"meta": {"stage": "fixed"}}, ensure_ascii=False), encoding="utf-8")

            self.assertEqual(resolve_resume_checkpoint_path(project_root, "missing-run", fixed_path), fixed_path)

    def test_task_resume_checkpoint_does_not_fall_back_to_configured_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            fixed_path = project_root / "output" / "classification_progress.json"
            fixed_path.parent.mkdir(parents=True)
            fixed_path.write_text(json.dumps({"meta": {"stage": "fixed"}}, ensure_ascii=False), encoding="utf-8")

            self.assertIsNone(resolve_task_resume_checkpoint_path(project_root, "missing-run"))

    def test_resolve_input_path_accepts_checkpoint_and_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            checkpoint_dir = project_root / "checkpoints" / "pipeline" / "combine_ingest" / "one"
            checkpoint_dir.mkdir(parents=True)
            items_path = checkpoint_dir / "items.json"
            items_path.write_text(json.dumps([{"platform": "x", "title": "t", "url": "https://example.com", "scrape_date": "2026-07-03"}]), encoding="utf-8")
            checkpoint_path = checkpoint_dir / "checkpoint.json"
            checkpoint_path.write_text(
                json.dumps({"output_refs": {"items": str(items_path)}}, ensure_ascii=False),
                encoding="utf-8",
            )

            self.assertEqual(resolve_input_path(project_root, "run-x", checkpoint_dir, project_root / "fallback.json"), items_path.resolve())
            self.assertEqual(resolve_input_path(project_root, "run-x", checkpoint_path, project_root / "fallback.json"), items_path.resolve())

    def test_task_checkpoint_prefers_explicit_step_meta_and_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config_path = project_root / "config.json"
            config_path.write_text(json.dumps({}), encoding="utf-8")
            config = load_config(str(config_path), project_root=project_root).classification
            input_path = project_root / "input.json"
            input_path.write_text(
                json.dumps([{"platform": "x", "title": "t", "url": "https://example.com", "scrape_date": "2026-07-03"}], ensure_ascii=False),
                encoding="utf-8",
            )
            item = NewsItem(platform="x", title="t", url="https://example.com", pubtime=None, scrape_date="2026-07-03")
            run_result = ClassifyRunResult(
                state=ClassifyState(items=[item], prepared=[]),
                last_step_result=ClassifyStepResult(
                    state=ClassifyState(items=[item], prepared=[]),
                    next_stage="completed",
                    checkpoint_meta={"stage": "completed", "processed_candidates": 7, "total_candidates": 9},
                    stats={"item_count": 1, "event_count": 0, "discarded_count": 0, "processed_candidates": 7, "total_candidates": 9},
                ),
            )

            result = write_classify_task_checkpoint(
                project_root,
                "run-1",
                TaskEvent(id="task-1", type="classify.clustered_event_merge", payload={}),
                get_registered_classify_task("classify.clustered_event_merge"),
                input_path,
                run_result,
                config,
            )

            checkpoint_payload = json.loads(Path(result["checkpoint_path"]).read_text(encoding="utf-8"))
            progress_payload = json.loads(Path(checkpoint_payload["output_refs"]["classification_progress"]).read_text(encoding="utf-8"))
            self.assertEqual(result["auto_publish_checkpoint"], result["checkpoint_path"])
            self.assertEqual(checkpoint_payload["stats"]["processed_candidates"], 7)
            self.assertEqual(checkpoint_payload["stats"]["total_candidates"], 9)
            self.assertEqual(progress_payload["meta"]["processed_candidates"], 7)
            self.assertEqual(progress_payload["meta"]["total_candidates"], 9)

    def test_task_snapshot_prefers_explicit_step_meta_and_stats(self) -> None:
        item = NewsItem(platform="x", title="t", url="https://example.com", pubtime=None, scrape_date="2026-07-03")
        run_result = ClassifyRunResult(
            state=ClassifyState(items=[item], prepared=[]),
            last_step_result=ClassifyStepResult(
                state=ClassifyState(items=[item], prepared=[]),
                next_stage="completed",
                checkpoint_meta={"stage": "completed", "processed_candidates": 7, "total_candidates": 9},
                stats={"item_count": 1, "event_count": 0, "discarded_count": 0, "processed_candidates": 7, "total_candidates": 9},
            ),
        )

        snapshot = build_classify_task_snapshot(
            step_id="classify/clustered_event_merge",
            run_result=run_result,
        )

        self.assertEqual(snapshot.step_id, "classify/clustered_event_merge")
        self.assertEqual(snapshot.checkpoint_meta["processed_candidates"], 7)
        self.assertEqual(snapshot.stats["total_candidates"], 9)

    def test_resume_state_decode_isolated_from_checkpoint_io(self) -> None:
        item = NewsItem(platform="x", title="t", url="https://example.com", pubtime=None, scrape_date="2026-07-03")
        payload = {
            "meta": {"stage": "after_clustered_event_extraction", "processed_candidates": 3},
            "items": [item.to_dict()],
            "events": [
                {
                    "event_id": "e1",
                    "event_label": "label",
                    "member_count": 1,
                    "platforms": ["x"],
                    "latest_pubtime": None,
                    "representative_titles": ["t"],
                    "first_pubtime": None,
                    "confidence": 88,
                    "event_summary": "summary",
                    "event_type": "company",
                    "key_entities": ["x"],
                    "source_news_ids": [0],
                    "last_llm_updated_at": "2026-07-03",
                }
            ],
            "discarded": [{"index": 2, "title": "drop", "platform": "x", "stage": "test", "reason": "no"}],
        }

        result = decode_resume_state(payload, [item])

        self.assertEqual(result.stage, "after_clustered_event_extraction")
        self.assertEqual(result.processed_candidates, 3)
        self.assertEqual(result.events[0].record.event_id, "e1")
        self.assertEqual(result.discarded[0].reason, "no")


if __name__ == "__main__":
    unittest.main()
