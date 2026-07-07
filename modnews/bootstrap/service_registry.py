from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from modnews.core.completion_callbacks import CompletionCallbackRegistry
from modnews.core.env import ensure_runtime_env
from modnews.core.event_queue import EventQueue
from modnews.core.events import EventRouter
from modnews.core.progress import BUS
from modnews.service.pipeline.manager import PipelineManager
from modnews.repository.checkpoints import CheckpointRepository
from modnews.repository.outputs import OutputRepository
from modnews.repository.queue_state import QueueStateRepository
from modnews.repository.runtime_config_repository import RuntimeConfigRepository
from modnews.repository.runs import RunRepository
from modnews.repository.task_logs import TaskLogRepository
from modnews.repository.web_jobs import WebJobRepository
from .event_handlers import register_completion_callbacks, register_task_executors
from .pipeline_registry import register_pipeline_steps


@dataclass(slots=True)
class ServiceContainer:
    project_root: Path = field(default_factory=lambda: Path.cwd())
    event_router: EventRouter = field(default_factory=EventRouter)
    event_queue: EventQueue = field(default_factory=EventQueue)
    completion_callbacks: CompletionCallbackRegistry = field(default_factory=CompletionCallbackRegistry)
    pipeline_manager: PipelineManager = field(default_factory=PipelineManager)

    def runtime_config(self) -> RuntimeConfigRepository:
        return RuntimeConfigRepository(self.project_root)

    def outputs(self) -> OutputRepository:
        return OutputRepository(self.project_root)

    def checkpoints(self) -> CheckpointRepository:
        return CheckpointRepository(self.project_root)

    def runs(self) -> RunRepository:
        return RunRepository(self.project_root)

    def queue_state(self) -> QueueStateRepository:
        return QueueStateRepository(self.project_root)

    def web_jobs(self) -> WebJobRepository:
        return WebJobRepository(self.project_root)

    def task_logs(self) -> TaskLogRepository:
        return TaskLogRepository(self.project_root)


def configure_services(project_root: Path | None = None) -> ServiceContainer:
    root = project_root.resolve() if project_root else Path.cwd().resolve()
    ensure_runtime_env(root)
    container = ServiceContainer(project_root=root)
    queue_state = QueueStateRepository(root)
    container.event_queue.bind_state_writer(queue_state.save)
    container.event_queue.load_snapshot(queue_state.load())
    container.pipeline_manager.bind(container.event_queue, container.event_router)
    container.event_queue.bind_router(container.event_router)
    task_logs = TaskLogRepository(root)
    container.event_queue.bind_logger(lambda task, event_type, payload: task_logs.append(task, event_type, **payload))
    BUS.bind_logger(lambda task, event: task_logs.append_progress(task, event))
    BUS.bind_router(container.event_router)
    register_pipeline_steps(container.pipeline_manager)
    register_completion_callbacks(container.completion_callbacks, container.pipeline_manager)
    container.completion_callbacks.bind(container.event_router)
    register_task_executors(container.event_queue)
    return container
