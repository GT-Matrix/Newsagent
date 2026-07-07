from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modnews.core.config import PipelineConfig, load_config
from modnews.core.task import TaskEvent
from modnews.repository.runs import RunRepository
from modnews.service.report.io.event_loader import resolve_report_input_path


@dataclass(frozen=True, slots=True)
class ReportTaskRuntime:
    project_root: Path
    run_id: str
    input_path: Path
    output_dir: Path
    config: PipelineConfig
    config_path: Path | None


def build_report_task_runtime(task: TaskEvent) -> ReportTaskRuntime:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    run_id = task.pipeline_run_id or str(task.payload.get("run_id") or "manual")
    config_path = resolve_report_config_path(task, project_root)
    return ReportTaskRuntime(
        project_root=project_root,
        run_id=run_id,
        input_path=resolve_report_input(task, project_root, run_id),
        output_dir=resolve_report_output_dir(task, project_root),
        config=load_config(task.payload.get("config"), project_root=project_root),
        config_path=config_path,
    )


def resolve_report_input(task: TaskEvent, project_root: Path, run_id: str) -> Path:
    input_value = task.payload.get("input_path")
    if input_value and str(input_value) != "__latest_classify_checkpoint__":
        path = Path(str(input_value)).expanduser()
        resolved = path.resolve() if path.is_absolute() else (project_root / path).resolve()
        return resolve_report_input_path(resolved)
    runs = RunRepository(project_root)
    record = runs.get(run_id)
    checkpoints = [Path(str(path)).resolve() for path in record.get("checkpoints", [])]
    classify_checkpoints = [path for path in checkpoints if "/classify/" in str(path)]
    if not classify_checkpoints:
        raise ValueError(f"no classify checkpoint found for run {run_id}")
    return resolve_report_input_path(classify_checkpoints[-1])


def resolve_report_output_dir(task: TaskEvent, project_root: Path) -> Path:
    output_dir = Path(str(task.payload.get("output_dir") or (project_root / "data" / "output"))).expanduser()
    if not output_dir.is_absolute():
        output_dir = (project_root / output_dir).resolve()
    return output_dir


def resolve_report_config_path(task: TaskEvent, project_root: Path) -> Path | None:
    config_path = task.payload.get("config")
    if not config_path:
        return None
    path = Path(str(config_path)).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()
