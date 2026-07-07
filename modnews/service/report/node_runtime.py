from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from modnews.core.config import LlmConfig, load_config
from modnews.core.event_queue import EventQueue, current_queue
from modnews.core.task import TaskBlocked, TaskEvent
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.service.report.editor import generate_report_polish
from modnews.service.report.models import EnrichedEvent
from modnews.service.report.pipeline import build_report_draft, write_report_outputs
from modnews.service.report.stages.trend_writer import generate_trend_summary
from modnews.service.report.task_result import build_report_task_stats, persist_report_task_result
from modnews.service.report.task_runtime import build_report_task_runtime
from modnews.service.report.utils.time import parse_report_date

PREPARE_STAGE = "prepare"
POLISH_STAGE = "polish"
TREND_STAGE = "trend"
COMPLETED_STAGE = "completed"

POLISH_TASK_TYPE = "report.polish_event"
TREND_TASK_TYPE = "report.trend_summary"
DEFAULT_POLISH_CONCURRENCY = 4


class ReportDraftState:
    def __init__(self, report_date, enriched_events: list[EnrichedEvent], evidence_payload: list[dict[str, Any]]) -> None:
        self.report_date = report_date
        self.enriched_events = enriched_events
        self.evidence_payload = evidence_payload


def run_report_generate_node(task: TaskEvent) -> dict[str, object]:
    runtime = build_report_task_runtime(task)
    queue = _require_queue(current_queue())
    node_stage = _node_stage(task)
    if node_stage == POLISH_STAGE:
        return _complete_polish_stage(task, queue)
    if node_stage == TREND_STAGE:
        return _complete_trend_stage(task, queue)
    return _start_report_node(task, runtime, queue)


def run_report_polish_task(task: TaskEvent) -> dict[str, object]:
    llm_config = _load_llm_config_from_payload(task.payload)
    event_payload = task.payload.get("event")
    evidence_payload = task.payload.get("evidence")
    if not isinstance(event_payload, dict):
        raise ValueError("report.polish_event requires event payload")
    event = _event_from_dict(event_payload)
    evidence = dict(evidence_payload) if isinstance(evidence_payload, dict) else {}
    result = generate_report_polish(event, evidence, llm_config)
    return {
        "event_id": event.event_id,
        "polish": result or {},
    }


def run_report_trend_summary_task(task: TaskEvent) -> dict[str, object]:
    llm_config = _load_llm_config_from_payload(task.payload)
    events_payload = task.payload.get("events")
    evidence_payload = task.payload.get("evidence_payload")
    if not isinstance(events_payload, list):
        raise ValueError("report.trend_summary requires events payload")
    if not isinstance(evidence_payload, list):
        raise ValueError("report.trend_summary requires evidence payload")
    events = [_event_from_dict(row) for row in events_payload if isinstance(row, dict)]
    summary = generate_trend_summary(events, evidence_payload, llm_config)
    return {"trend_summary": summary}


def handle_report_child_task_callback(event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]]:
    if queue is None:
        return []
    task = event.get("task")
    if not isinstance(task, dict):
        return []
    parent_task_id = task.get("parent_task_id")
    if not parent_task_id:
        return []
    try:
        parent = queue.get(str(parent_task_id))
    except KeyError:
        return []
    if parent.type != "report.generate":
        return []
    stage = str(queue.result(parent.id).get("node_stage") or _node_stage(parent))
    if stage == POLISH_STAGE:
        return _handle_child_group_completion(parent, queue, "polish_group_id", POLISH_STAGE)
    if stage == TREND_STAGE:
        return _handle_child_group_completion(parent, queue, "trend_group_id", TREND_STAGE)
    return []


def _start_report_node(task: TaskEvent, runtime, queue: EventQueue) -> dict[str, object]:
    report_date = parse_report_date(task.payload.get("date"))
    draft = build_report_draft(runtime.input_path, report_date)
    draft_state_path = _write_draft_state(runtime.project_root, runtime.run_id, task.id, draft)
    llm_config = _resolve_report_llm_config(runtime.config_path)
    selected = [event for event in draft.enriched_events if event.should_include_report]
    if not _has_usable_llm_config(llm_config) or not selected:
        return _finalize_report_node(
            task=task,
            runtime=runtime,
            draft=draft,
            trend_summary=None,
            draft_state_path=draft_state_path,
        )

    submission = _register_polish_children(task, queue, runtime.config_path, selected, draft.evidence_payload)
    queue.patch_payload(
        task.id,
        {
            "node_stage": POLISH_STAGE,
            "report_date": report_date.isoformat(),
            "draft_state_path": str(draft_state_path),
            "polish_group_id": submission["group_id"],
            "polish_task_ids": submission["task_ids"],
        },
    )
    raise TaskBlocked(
        "waiting for report polish tasks",
        details={
            "kind": "child_task_group_active",
            "node_stage": POLISH_STAGE,
            "task_group_id": submission["group_id"],
        },
    )


def _complete_polish_stage(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    runtime = build_report_task_runtime(task)
    draft = _read_draft_state(Path(str(task.payload["draft_state_path"])))
    _apply_polish_results(draft.enriched_events, queue, task.payload.get("polish_task_ids") or [])
    draft_state_path = _write_draft_state(runtime.project_root, runtime.run_id, task.id, draft)
    llm_config = _resolve_report_llm_config(runtime.config_path)
    if not _has_usable_llm_config(llm_config):
        return _finalize_report_node(
            task=task,
            runtime=runtime,
            draft=draft,
            trend_summary=None,
            draft_state_path=draft_state_path,
        )

    selected = [event for event in draft.enriched_events if event.should_include_report and event.report_section != "watchlist"]
    if not selected:
        return _finalize_report_node(
            task=task,
            runtime=runtime,
            draft=draft,
            trend_summary=None,
            draft_state_path=draft_state_path,
        )

    submission = _register_trend_child(task, queue, runtime.config_path, draft.enriched_events, draft.evidence_payload)
    queue.patch_payload(
        task.id,
        {
            "node_stage": TREND_STAGE,
            "draft_state_path": str(draft_state_path),
            "trend_group_id": submission["group_id"],
            "trend_task_ids": submission["task_ids"],
        },
    )
    raise TaskBlocked(
        "waiting for trend summary task",
        details={
            "kind": "child_task_group_active",
            "node_stage": TREND_STAGE,
            "task_group_id": submission["group_id"],
        },
    )


def _complete_trend_stage(task: TaskEvent, queue: EventQueue) -> dict[str, object]:
    runtime = build_report_task_runtime(task)
    draft = _read_draft_state(Path(str(task.payload["draft_state_path"])))
    trend_summary = _collect_trend_summary(queue, task.payload.get("trend_task_ids") or [])
    return _finalize_report_node(
        task=task,
        runtime=runtime,
        draft=draft,
        trend_summary=trend_summary,
        draft_state_path=Path(str(task.payload["draft_state_path"])),
    )


def _finalize_report_node(
    *,
    task: TaskEvent,
    runtime,
    draft,
    trend_summary: str | None,
    draft_state_path: Path,
) -> dict[str, object]:
    write_report_outputs(
        runtime.output_dir,
        draft.enriched_events,
        draft.evidence_payload,
        draft.report_date,
        trend_summary,
    )
    result = persist_report_task_result(
        project_root=runtime.project_root,
        run_id=runtime.run_id,
        task_id=task.id,
        input_path=runtime.input_path,
        output_dir=runtime.output_dir,
        stats=build_report_task_stats(draft.enriched_events),
    )
    result["node_stage"] = COMPLETED_STAGE
    result["draft_state_path"] = str(draft_state_path)
    return result


def _register_polish_children(
    task: TaskEvent,
    queue: EventQueue,
    config_path: Path | None,
    selected: list[EnrichedEvent],
    evidence_payload: list[dict[str, object]],
) -> dict[str, object]:
    evidence_by_id = {str(row.get("event_id")): row for row in evidence_payload}
    group_id = f"{task.id}:polish"
    task_ids: list[str] = []
    for index, event in enumerate(selected, start=1):
        child = TaskEvent(
            id=f"{task.id}:polish:{index}",
            type=POLISH_TASK_TYPE,
            pipeline_run_id=task.pipeline_run_id,
            step_id="report/generate/polish",
            parent_task_id=task.id,
            task_group_id=group_id,
            payload={
                "project_root": task.payload.get("project_root"),
                "run_id": task.payload.get("run_id"),
                "config": str(config_path) if config_path else None,
                "event": asdict(event),
                "evidence": evidence_by_id.get(event.event_id, {}),
                "item_index": index,
                "item_count": len(selected),
            },
            concurrency_key="report.polish",
            max_concurrency=int(task.payload.get("report_polish_max_concurrency") or DEFAULT_POLISH_CONCURRENCY),
            priority=task.priority,
        )
        queue.register(child)
        task_ids.append(child.id)
    return {"group_id": group_id, "task_ids": task_ids}


def _register_trend_child(
    task: TaskEvent,
    queue: EventQueue,
    config_path: Path | None,
    events: list[EnrichedEvent],
    evidence_payload: list[dict[str, object]],
) -> dict[str, object]:
    group_id = f"{task.id}:trend"
    child = TaskEvent(
        id=f"{task.id}:trend:1",
        type=TREND_TASK_TYPE,
        pipeline_run_id=task.pipeline_run_id,
        step_id="report/generate/trend",
        parent_task_id=task.id,
        task_group_id=group_id,
        payload={
            "project_root": task.payload.get("project_root"),
            "run_id": task.payload.get("run_id"),
            "config": str(config_path) if config_path else None,
            "events": [asdict(event) for event in events],
            "evidence_payload": evidence_payload,
        },
        concurrency_key="report.trend",
        max_concurrency=1,
        priority=task.priority,
    )
    queue.register(child)
    return {"group_id": group_id, "task_ids": [child.id]}


def _apply_polish_results(events: list[EnrichedEvent], queue: EventQueue, task_ids: list[object]) -> None:
    event_by_id = {event.event_id: event for event in events}
    for task_id in [str(item) for item in task_ids]:
        try:
            child = queue.get(task_id)
        except KeyError:
            continue
        if child.state != "succeeded":
            _append_child_warning(event_by_id, child, queue.result(task_id))
            continue
        result = queue.result(task_id)
        event_id = str(result.get("event_id") or "")
        event = event_by_id.get(event_id)
        if event is None:
            continue
        polish = result.get("polish")
        if isinstance(polish, dict):
            title = _clean_text(polish.get("title"))
            brief = _clean_text(polish.get("brief"))
            why = _clean_text(polish.get("why_important"))
            if title:
                event.title = title
            if brief:
                event.one_sentence = brief
            if why:
                event.why_important = why
            event.evidence_summary["llm_polished"] = True


def _append_child_warning(event_by_id: dict[str, EnrichedEvent], child: TaskEvent, result: dict[str, Any]) -> None:
    payload = child.payload.get("event")
    if not isinstance(payload, dict):
        return
    event_id = str(payload.get("event_id") or "")
    event = event_by_id.get(event_id)
    if event is None:
        return
    if child.state == "blocked":
        reason = str(result.get("blocked_reason") or child.status_reason or "blocked")
        event.warnings.append(f"report_polish_blocked:{reason}")
        event.evidence_summary["llm_polished"] = False
        event.evidence_summary["polish_error"] = reason
        return
    if child.state == "failed":
        reason = str(result.get("error") or child.status_reason or "failed")
        event.warnings.append(f"report_polish_failed:{reason}")
        event.evidence_summary["llm_polished"] = False
        event.evidence_summary["polish_error"] = reason


def _collect_trend_summary(queue: EventQueue, task_ids: list[object]) -> str | None:
    for task_id in [str(item) for item in task_ids]:
        try:
            child = queue.get(task_id)
        except KeyError:
            continue
        if child.state != "succeeded":
            continue
        result = queue.result(task_id)
        value = result.get("trend_summary")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _handle_child_group_completion(
    parent: TaskEvent,
    queue: EventQueue,
    group_key: str,
    stage: str,
) -> list[dict[str, Any]]:
    summary = queue.group_summary(str(parent.payload.get(group_key) or ""))
    if summary["active"] > 0:
        return []
    queue.retry(parent.id)
    queue.drain_ready()
    return [{"action": "retry_parent_task", "task_id": parent.id, "stage": stage}]


def _write_draft_state(project_root: Path, run_id: str, task_id: str, draft) -> Path:
    manager = CheckpointManager(project_root)
    payload = {
        "report_date": draft.report_date.isoformat(),
        "enriched_events": [asdict(event) for event in draft.enriched_events],
        "evidence_payload": draft.evidence_payload,
    }
    return manager.write_artifact(run_id, "report/generate", task_id, "draft_state.json", payload)


def _read_draft_state(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReportDraftState(
        report_date=parse_report_date(payload.get("report_date")),
        enriched_events=[_event_from_dict(row) for row in payload.get("enriched_events", []) if isinstance(row, dict)],
        evidence_payload=[row for row in payload.get("evidence_payload", []) if isinstance(row, dict)],
    )


def _event_from_dict(payload: dict[str, Any]) -> EnrichedEvent:
    return EnrichedEvent(**payload)


def _resolve_report_llm_config(config_path: Path | None) -> LlmConfig | None:
    if config_path is None:
        return None
    return load_config(str(config_path)).classification.llm


def _load_llm_config_from_payload(payload: dict[str, Any]) -> LlmConfig | None:
    config_value = payload.get("config")
    if not config_value:
        return None
    return load_config(str(config_value)).classification.llm


def _has_usable_llm_config(llm_config: LlmConfig | None) -> bool:
    return bool(llm_config and llm_config.base_url and llm_config.api_key)


def _node_stage(task: TaskEvent) -> str:
    return str(task.payload.get("node_stage") or task.payload.get("stage") or PREPARE_STAGE)


def _require_queue(value: object) -> EventQueue:
    if isinstance(value, EventQueue):
        return value
    raise RuntimeError("report node requires active event queue")


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())
