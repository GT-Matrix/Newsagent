from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modnews.core.task import TaskEvent
from modnews.core.config import apply_runtime_overrides, load_config


@dataclass(slots=True)
class IngestClassifyPipelineStep:
    id: str = "ingest_classify"

    def plan(self, state: dict[str, Any], completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        if completed_event is not None:
            return []
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        run_id = str(state.get("run_id") or request.get("run_id") or "local")
        project_root = str(request.get("project_root") or "")
        config_path = request.get("config")
        config = load_config(config_path)
        apply_runtime_overrides(
            config,
            only_ingest_steps=request.get("only_ingest_steps") or request.get("only"),
            disable_classification=bool(request.get("disable_classification")),
        )
        ingest_tasks: list[TaskEvent] = []
        for step in config.ingest_steps:
            if not step.enabled:
                continue
            ingest_tasks.append(
                TaskEvent(
                    id=f"ingest-{run_id}-{step.type}",
                    type="ingest.run_step",
                    pipeline_run_id=run_id,
                    step_id=f"ingest/{step.type}",
                    payload={
                        "project_root": project_root,
                        "run_id": run_id,
                        "config": config_path,
                        "step_id": step.type,
                        "options": step.options,
                    },
                    concurrency_key=f"ingest:{step.type}",
                    max_concurrency=1,
                )
            )
        combine_task = TaskEvent(
            id=f"pipeline-{run_id}-combine-ingest",
            type="pipeline.combine_ingest",
            pipeline_run_id=run_id,
            step_id="pipeline/combine_ingest",
            payload={"project_root": project_root, "run_id": run_id},
            depends_on=[task.id for task in ingest_tasks],
            concurrency_key=f"pipeline:{run_id}",
            max_concurrency=1,
        )
        tasks = [*ingest_tasks, combine_task]
        if config.classification.enabled:
            extraction_task = TaskEvent(
                id=f"classify-{run_id}-clustered-event-extraction",
                type="classify.clustered_event_extraction",
                pipeline_run_id=run_id,
                step_id="classify/clustered_event_extraction",
                payload={
                    "project_root": project_root,
                    "run_id": run_id,
                    "config": config_path,
                    "input_path": "__combined_ingest__",
                },
                depends_on=[combine_task.id],
                concurrency_key="classify",
                max_concurrency=1,
            )
            merge_task = TaskEvent(
                id=f"classify-{run_id}-clustered-event-merge",
                type="classify.clustered_event_merge",
                pipeline_run_id=run_id,
                step_id="classify/clustered_event_merge",
                payload={
                    "project_root": project_root,
                    "run_id": run_id,
                    "config": config_path,
                    "input_path": "__combined_ingest__",
                },
                depends_on=[extraction_task.id],
                concurrency_key="classify",
                max_concurrency=1,
            )
            tasks.extend([extraction_task, merge_task])
        return tasks
