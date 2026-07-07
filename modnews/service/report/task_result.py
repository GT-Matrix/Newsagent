from __future__ import annotations

from pathlib import Path
from typing import Any

from modnews.repository.runs import RunRepository
from modnews.service.pipeline.checkpoint import CheckpointManager


def build_report_task_stats(events: list[object]) -> dict[str, int]:
    return {
        "event_count": len(events),
        "selected_count": len([event for event in events if getattr(event, "should_include_report", False)]),
        "events_with_sources": len([event for event in events if getattr(event, "source_items", None)]),
    }


def persist_report_task_result(
    *,
    project_root: Path,
    run_id: str,
    task_id: str,
    input_path: Path,
    output_dir: Path,
    stats: dict[str, Any],
) -> dict[str, object]:
    checkpoint = CheckpointManager(project_root)
    checkpoint_payload = {
        "run_id": run_id,
        "step_id": "report/generate",
        "task_id": task_id,
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
    checkpoint_path = checkpoint.write(run_id, "report/generate", task_id, checkpoint_payload)
    RunRepository(project_root).append_checkpoint(run_id, checkpoint_path, create_payload={"source": "report_task"})
    return {
        "checkpoint_path": str(checkpoint_path),
        "stats": stats,
        "report_output_dir": str(output_dir),
    }
