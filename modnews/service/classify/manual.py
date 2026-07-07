from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from modnews.bootstrap.event_handlers import register_completion_callbacks, register_task_executors
from modnews.bootstrap.pipeline_registry import register_pipeline_steps
from modnews.core.completion_callbacks import CompletionCallbackRegistry
from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext
from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.core.models import EventRecord, NewsItem, StepResult
from modnews.core.task import TaskBlocked
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.runs import RunRepository
from modnews.service.classify.io import load_news_items
from modnews.service.classify.planner import (
    build_clustered_event_extraction_task,
    build_clustered_event_merge_task,
)
from modnews.service.classify.run_result import build_classify_step_result_from_stats
from modnews.service.classify.state_codec import decode_event_records
from modnews.service.pipeline.manager import PipelineManager


def run_classification(
    ctx: PipelineContext,
    items: list[NewsItem],
    config: ClassificationConfig,
) -> tuple[list[NewsItem], list[EventRecord], StepResult]:
    if not config.enabled:
        return items, [], StepResult(step="classify", item_count=len(items), meta={"enabled": False})

    project_root = ctx.config.project_root
    run_id = f"manual-classify-{uuid4().hex}"
    input_path = _write_manual_input(project_root, run_id, items)
    config_path = _write_manual_config_override(project_root, run_id, config)
    queue = EventQueue()
    router = EventRouter()
    callbacks = CompletionCallbackRegistry()
    pipeline_manager = PipelineManager()
    pipeline_manager.bind(queue, router)
    queue.bind_router(router)
    register_pipeline_steps(pipeline_manager)
    register_completion_callbacks(callbacks, pipeline_manager)
    callbacks.bind(router)
    register_task_executors(queue)

    RunRepository(project_root).create(run_id, {"source": "manual_classify_task", "input_path": str(input_path)})
    extraction_task = build_clustered_event_extraction_task(
        project_root=project_root,
        run_id=run_id,
        input_path=str(input_path),
        config=str(config_path),
    )
    merge_task = build_clustered_event_merge_task(
        project_root=project_root,
        run_id=run_id,
        input_path=None,
        config=str(config_path),
        depends_on=[extraction_task.id],
    )
    queue.register(extraction_task)
    queue.register(merge_task)
    queue.drain_ready()

    merge_current = queue.get(merge_task.id)
    if merge_current.state == "blocked":
        raise TaskBlocked(str(queue.result(merge_task.id).get("blocked_reason") or "manual classify blocked"))
    if merge_current.state != "succeeded":
        raise RuntimeError(str(queue.result(merge_task.id).get("error") or f"manual classify ended as {merge_current.state}"))

    checkpoint_path = Path(str(queue.result(merge_task.id)["checkpoint_path"]))
    checkpoint_payload = CheckpointRepository(project_root).read(checkpoint_path)
    output_refs = checkpoint_payload.get("output_refs") if isinstance(checkpoint_payload.get("output_refs"), dict) else {}
    output_items = load_news_items(Path(str(output_refs["news_with_events"])).resolve())
    raw_events = json.loads(Path(str(output_refs["events"])).read_text(encoding="utf-8"))
    output_events = decode_event_records(raw_events if isinstance(raw_events, list) else [])
    step_result = build_classify_step_result_from_stats(
        config=config,
        item_count=len(output_items),
        stats=dict(checkpoint_payload.get("stats") or {}),
        step="classify",
    )
    return output_items, output_events, step_result


def _write_manual_input(project_root: Path, run_id: str, items: list[NewsItem]) -> Path:
    path = project_root / "var" / "process" / "manual" / run_id / "items.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_manual_config_override(project_root: Path, run_id: str, config: ClassificationConfig) -> Path:
    path = project_root / "var" / "process" / "manual" / run_id / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "classification": {
                    "enabled": config.enabled,
                    "batch_size": config.batch_size,
                    "batch_concurrency": config.batch_concurrency,
                    "event_candidate_count": config.event_candidate_count,
                    "merge_candidate_count": config.merge_candidate_count,
                    "time_window_hours": config.time_window_hours,
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
