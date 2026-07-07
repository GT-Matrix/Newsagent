from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from modnews.bootstrap import configure_services
from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext
from modnews.core.models import EventRecord, NewsItem, StepResult
from modnews.core.task import TaskBlocked
from modnews.repository.checkpoints import CheckpointRepository
from modnews.service.classify.io import load_news_items
from modnews.service.classify.queue_runtime import submit_clustered_classify_run
from modnews.service.classify.run_result import build_classify_step_result_from_stats
from modnews.service.classify.state_codec import decode_event_records
from modnews.service.pipeline.query_facade import PipelineQueryFacade


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
    container = configure_services(project_root)
    queries = PipelineQueryFacade(
        project_root=project_root,
        queue=container.event_queue,
        pipeline_descriptors=container.pipeline_manager.describe_steps(),
    )
    result = submit_clustered_classify_run(
        project_root=project_root,
        queue=container.event_queue,
        queue_show=queries.task_detail,
        run_id=run_id,
        input_path=str(input_path),
        config=str(config_path),
        pipeline_descriptors=container.pipeline_manager.describe_steps(),
    )
    merge_task = next(
        (task for task in result["tasks"] if task.get("type") == "classify.clustered_event_merge"),
        None,
    )
    if not isinstance(merge_task, dict):
        raise RuntimeError("manual classify did not produce clustered merge task")

    if merge_task.get("state") == "blocked":
        blocked_reason = merge_task.get("result", {}).get("blocked_reason") if isinstance(merge_task.get("result"), dict) else None
        raise TaskBlocked(str(blocked_reason or "manual classify blocked"))
    if merge_task.get("state") != "succeeded":
        error = merge_task.get("result", {}).get("error") if isinstance(merge_task.get("result"), dict) else None
        raise RuntimeError(str(error or f"manual classify ended as {merge_task.get('state')}"))

    checkpoint_path = Path(str(merge_task["result"]["checkpoint_path"]))
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
