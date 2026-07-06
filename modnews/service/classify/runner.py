from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext

from .llm_client import LlmClient
from .retriever import EventVectorRetriever
from .state import ClassifyState


@dataclass(slots=True)
class ClassifyRuntime:
    ctx: PipelineContext
    config: ClassificationConfig
    client: LlmClient
    retriever: EventVectorRetriever
    write_fixed_outputs: bool = True


class ClassifyStep(Protocol):
    name: str
    output_stage: str

    def should_run(self, state: ClassifyState) -> bool:
        ...

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> "ClassifyStepResult":
        ...


class ClassifyStepObserver(Protocol):
    def on_skip(self, *, step_name: str, state: ClassifyState) -> None:
        ...

    def on_start(self, *, step_name: str, output_stage: str, state: ClassifyState) -> None:
        ...

    def on_done(self, *, step_name: str, state: ClassifyState) -> None:
        ...


@dataclass(slots=True)
class ClassifyStepResult:
    state: ClassifyState
    next_stage: str | None = None
    checkpoint_meta: dict[str, object] | None = None
    stats: dict[str, object] | None = None


@dataclass(slots=True)
class ClassifyRunResult:
    state: ClassifyState
    last_step_result: ClassifyStepResult | None = None


class ClassifyStepRunner:
    def __init__(self, steps: list[ClassifyStep], observer: ClassifyStepObserver | None = None) -> None:
        self.steps = steps
        self.observer = observer

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyRunResult:
        last_result: ClassifyStepResult | None = None
        for step in self.steps:
            if not step.should_run(state):
                if self.observer is not None:
                    self.observer.on_skip(step_name=step.name, state=state)
                continue
            if self.observer is not None:
                self.observer.on_start(step_name=step.name, output_stage=step.output_stage, state=state)
            result = step.run(state, runtime)
            state = result.state
            if result.next_stage is not None:
                state.stage = result.next_stage
            if self.observer is not None:
                self.observer.on_done(step_name=step.name, state=state)
            last_result = result
        return ClassifyRunResult(state=state, last_step_result=last_result)
