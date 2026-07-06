from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.task import TaskEvent
from modnews.service.classify.runtime_build import (
    build_classify_llm_client_for_context,
    build_classify_retriever_for_context,
    resolve_classify_task_environment,
)


class ClassifyRuntimeBuildTest(unittest.TestCase):
    def test_resolve_classify_task_environment_uses_task_payload_and_run_context(self) -> None:
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

            env = resolve_classify_task_environment(task)

            self.assertEqual(env.project_root, project_root.resolve())
            self.assertEqual(env.run_id, "run-1")
            self.assertEqual(env.config.project_root, project_root.resolve())
            self.assertEqual(env.ctx.config.project_root, project_root.resolve())

    def test_context_helpers_build_llm_client_and_retriever_from_shared_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            config_path = project_root / "config.json"
            config_path.write_text(json.dumps({}), encoding="utf-8")
            pipeline_config = load_config(str(config_path), project_root=project_root)
            ctx = PipelineContext.create(pipeline_config)

            client = build_classify_llm_client_for_context(ctx, pipeline_config.classification)
            retriever = build_classify_retriever_for_context(ctx, pipeline_config.classification)

            self.assertIs(client.session, ctx.session)
            self.assertIs(retriever.session, ctx.session)
            self.assertEqual(client.config.model, pipeline_config.classification.llm.model)
            self.assertEqual(retriever.config.model, pipeline_config.classification.embedding.model)


if __name__ == "__main__":
    unittest.main()
