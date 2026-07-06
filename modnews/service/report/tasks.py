from __future__ import annotations

from pathlib import Path

from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.pipeline.checkpoint import CheckpointManager
from modnews.service.report import generate_report


def run_report_generate_task(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
    input_path = _resolve_report_input(task, project_root, run_id)
    output_dir = Path(str(task.payload.get("output_dir") or (project_root / "data" / "output"))).expanduser()
    if not output_dir.is_absolute():
        output_dir = (project_root / output_dir).resolve()
    config_path = task.payload.get("config")
    config = Path(str(config_path)).expanduser().resolve() if config_path else None
    events = generate_report(input_path, output_dir, report_date=task.payload.get("date"), config_path=config)
    checkpoint = CheckpointManager(project_root)
    stats = {
        "event_count": len(events),
        "selected_count": len([event for event in events if event.should_include_report]),
        "events_with_sources": len([event for event in events if event.source_items]),
    }
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": "report/generate",
        "task_id": task.id,
        "status": "succeeded",
        "input_refs": {"events": str(input_path)},
        "output_refs": {
            "report_markdown": str(output_dir / "daily_report.md"),
            "report_debug_markdown": str(output_dir / "daily_report_debug.md"),
            "report_events": str(output_dir / "enriched_events.json"),
            "report_trend_summary": str(output_dir / "trend_summary.json"),
        },
        "stats": stats,
        "error": None,
    }
    checkpoint_path = checkpoint.write(run_id, "report/generate", task.id, checkpoint_payload)
    RunRepository(project_root).append_checkpoint(run_id, checkpoint_path, create_payload={"source": "report_task"})
    return {
        "checkpoint_path": str(checkpoint_path),
        "stats": stats,
        "report_output_dir": str(output_dir),
    }


def _resolve_report_input(task: TaskEvent, project_root: Path, run_id: str) -> Path:
    input_value = task.payload.get("input_path")
    if input_value and str(input_value) != "__latest_classify_checkpoint__":
        path = Path(str(input_value)).expanduser()
        return path.resolve() if path.is_absolute() else (project_root / path).resolve()
    runs = RunRepository(project_root)
    record = runs.get(run_id)
    checkpoints = [Path(str(path)).resolve() for path in record.get("checkpoints", [])]
    classify_checkpoints = [path for path in checkpoints if "/classify/" in str(path)]
    if not classify_checkpoints:
        raise ValueError(f"no classify checkpoint found for run {run_id}")
    return classify_checkpoints[-1]
