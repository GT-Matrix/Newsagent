from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem
from modnews.core.task import TaskEvent
from modnews.service.classify.runtime_facade import ClassifyRuntimeFacade


class ClassifyRuntimeFacadeTest(unittest.TestCase):
    def test_resolve_task_environment_uses_task_payload_and_run_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config_path = project_root / "config.json"
            config_path.write_text(json.dumps({}), encoding="utf-8")
            task = TaskEvent(
                id="task-1",
                type="classify.clustered_event_extraction",
                pipeline_run_id="run-1",
                payload={
                    "project_root": str(project_root),
                    "run_id": "ignored-run-id",
                    "config": str(config_path),
                },
            )

            env = ClassifyRuntimeFacade().resolve_task_environment(task)

            self.assertEqual(env.project_root, project_root.resolve())
            self.assertEqual(env.run_id, "run-1")
            self.assertEqual(env.config.project_root, project_root.resolve())
            self.assertEqual(env.ctx.config.project_root, project_root.resolve())

    def test_build_runtime_for_context_reuses_shared_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config_path = project_root / "config.json"
            config_path.write_text(json.dumps({}), encoding="utf-8")
            pipeline_config = load_config(str(config_path), project_root=project_root)
            ctx = PipelineContext.create(pipeline_config)

            runtime = ClassifyRuntimeFacade().build_runtime_for_context(ctx, pipeline_config.classification)

            self.assertIs(runtime.client.session, ctx.session)
            self.assertIs(runtime.retriever.session, ctx.session)

    def test_build_state_for_run_prefers_run_checkpoint_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            item = NewsItem(platform="x", title="t", url="https://example.com", pubtime=None, scrape_date="2026-07-03")

            state = ClassifyRuntimeFacade().build_state_from_items([item], resume_checkpoint_path=None)

            self.assertEqual(len(state.items), 1)
            self.assertEqual(state.prepared[0].item.title, "t")


if __name__ == "__main__":
    unittest.main()
