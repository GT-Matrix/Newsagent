from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.internal.service.pipeline.manager import PipelineManager
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.outputs import OutputRepository
from modnews.repository.runtime_config import RuntimeConfigRepository
from modnews.repository.web_jobs import WebJobRepository
from .event_handlers import register_event_handlers, register_task_executors


@dataclass(slots=True)
class ServiceContainer:
    project_root: Path = field(default_factory=lambda: Path.cwd())
    event_router: EventRouter = field(default_factory=EventRouter)
    event_queue: EventQueue = field(default_factory=EventQueue)
    pipeline_manager: PipelineManager = field(default_factory=PipelineManager)

    def runtime_config(self) -> RuntimeConfigRepository:
        return RuntimeConfigRepository(self.project_root)

    def outputs(self) -> OutputRepository:
        return OutputRepository(self.project_root)

    def checkpoints(self) -> CheckpointRepository:
        return CheckpointRepository(self.project_root)

    def web_jobs(self) -> WebJobRepository:
        return WebJobRepository(self.project_root)


def configure_services(project_root: Path | None = None) -> ServiceContainer:
    root = project_root.resolve() if project_root else Path.cwd().resolve()
    container = ServiceContainer(project_root=root)
    container.pipeline_manager.bind(container.event_queue, container.event_router)
    register_event_handlers(container.event_router)
    register_task_executors(container.event_queue)
    return container
