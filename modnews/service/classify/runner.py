from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext
from modnews.core.progress import emit

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


@dataclass(slots=True)
class ClassifyStepResult:
    state: ClassifyState
    next_stage: str | None = None


class ClassifyStepRunner:
    def __init__(self, steps: list[ClassifyStep]) -> None:
        self.steps = steps

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyState:
        for step in self.steps:
            if not step.should_run(state):
                emit("step_skip", step=step.name, stage=state.stage)
                continue
            emit("step_start", step=step.name, stage=state.stage, output_stage=step.output_stage)
            result = step.run(state, runtime)
            state = result.state
            if result.next_stage is not None:
                state.stage = result.next_stage
            emit("step_done", step=step.name, stage=state.stage)
        return state
