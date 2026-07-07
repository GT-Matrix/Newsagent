from __future__ import annotations

from abc import ABC, abstractmethod
import argparse
from pathlib import Path
from typing import Any

from modnews.core.context import PipelineContext
from modnews.core.models import NewsItem, StepResult
from modnews.core.task import TaskEvent
from modnews.service.ingest.task_registry import (
    build_registered_ingest_step_task,
    get_registered_ingest_task,
)


class IngestStep(ABC):
    step_name: str

    def __init__(self, **options):
        self.options = options

    @classmethod
    def options_from_api_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        value = payload.get("options")
        return dict(value) if isinstance(value, dict) else {}

    @classmethod
    def options_from_cli_args(cls, args: argparse.Namespace) -> dict[str, Any]:
        return {}

    @abstractmethod
    def run(self, ctx: PipelineContext) -> tuple[list[NewsItem], StepResult]:
        raise NotImplementedError

    @classmethod
    def plan_tasks(
        cls,
        *,
        project_root: Path,
        run_id: str,
        config_path: object = None,
        options: dict[str, Any] | None = None,
    ) -> list[TaskEvent]:
        task_options = options if isinstance(options, dict) else {}
        return [
            build_registered_ingest_step_task(
                get_registered_ingest_task("ingest.run_step"),
                project_root=project_root,
                run_id=run_id,
                step_name=cls.step_name,
                config_path=config_path,
                options=task_options,
            )
        ]
