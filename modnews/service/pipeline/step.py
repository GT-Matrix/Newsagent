from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from modnews.core.event_queue import EventQueue
from modnews.core.task import TaskEvent


@dataclass(slots=True)
class PipelinePlanContext:
    run_id: str
    request: dict[str, Any]
    tasks: list[TaskEvent] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PipelineFollowupDescriptor:
    trigger: str
    builder_id: str
    task_type: str | None = None
    step_prefix: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineStepDescriptor:
    step_id: str
    title: str
    group: str
    kind: str
    description: str | None = None
    depends_on: tuple[str, ...] = ()
    callback_handlers: tuple[str, ...] = ()
    followups: tuple[PipelineFollowupDescriptor, ...] = ()
    concrete_step_ids: tuple[str, ...] = ()
    concrete_step_prefixes: tuple[str, ...] = ()


class PipelineStep(Protocol):
    id: str

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        ...

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        ...

    def on_task_failed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        ...

    def on_task_blocked(self, event: dict[str, Any], queue: EventQueue) -> list[dict[str, Any]] | None:
        ...

    def describe(self) -> PipelineStepDescriptor:
        ...


class PipelineStepBase:
    id: str
    title: str = ""
    group: str = "pipeline"
    kind: str = "root"
    description: str | None = None
    depends_on: tuple[str, ...] = ()
    callback_handlers: tuple[str, ...] = ()
    followup_descriptors: tuple[PipelineFollowupDescriptor, ...] = ()
    concrete_step_ids: tuple[str, ...] = ()
    concrete_step_prefixes: tuple[str, ...] = ()

    def plan(self, context: PipelinePlanContext, completed_event: dict[str, Any] | None = None) -> list[TaskEvent]:
        raise NotImplementedError

    def on_task_completed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return None

    def on_task_failed(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return None

    def on_task_blocked(self, event: dict[str, Any], queue: EventQueue | None) -> list[dict[str, Any]] | None:
        return None

    def describe(self) -> PipelineStepDescriptor:
        return PipelineStepDescriptor(
            step_id=self.id,
            title=self.title or self.id,
            group=self.group,
            kind=self.kind,
            description=self.description,
            depends_on=self.depends_on,
            callback_handlers=self.callback_handlers,
            followups=self.followup_descriptors,
            concrete_step_ids=self.concrete_step_ids,
            concrete_step_prefixes=self.concrete_step_prefixes,
        )
