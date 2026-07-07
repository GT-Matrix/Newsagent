from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent
from modnews.service.pipeline.read_model import (
    build_run_detail,
    build_run_list_item,
    build_task_detail,
    build_task_list_item,
)
from modnews.service.pipeline.step import PipelineStepDescriptor


@dataclass(slots=True)
class PipelineQueryFacade:
    project_root: Path
    queue: EventQueue
    pipeline_descriptors: list[PipelineStepDescriptor]

    def run_list_item(self, run_record: dict[str, Any]) -> dict[str, Any]:
        return build_run_list_item(
            self.project_root,
            self.queue,
            run_record,
            pipeline_descriptors=self.pipeline_descriptors,
        )

    def run_detail(self, run_id: str) -> dict[str, Any]:
        return build_run_detail(
            self.project_root,
            self.queue,
            run_id,
            pipeline_descriptors=self.pipeline_descriptors,
        )

    def task_list_item(self, task: TaskEvent) -> dict[str, Any]:
        return build_task_list_item(self.project_root, self.queue, task)

    def task_detail(self, task_id: str) -> dict[str, Any]:
        return build_task_detail(self.project_root, self.queue, task_id)
