from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from modnews_pipeline.config import ClassificationConfig
from modnews_pipeline.context import PipelineContext
from modnews_pipeline.progress import emit

from .llm_client import LlmClient
from .retriever import EventVectorRetriever
from .state import ClassifyState


@dataclass(slots=True)
class ClassifyRuntime:
    ctx: PipelineContext
    config: ClassificationConfig
    client: LlmClient
    retriever: EventVectorRetriever


class ClassifyStep(Protocol):
    name: str
    output_stage: str

    def should_run(self, state: ClassifyState) -> bool:
        ...

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyState:
        ...


class ClassifyStepRunner:
    def __init__(self, steps: list[ClassifyStep]) -> None:
        self.steps = steps

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyState:
        for step in self.steps:
            before_stage = state.stage
            if not step.should_run(state):
                emit("step_skip", step=step.name, stage=state.stage)
                continue
            emit("step_start", step=step.name, stage=state.stage, output_stage=step.output_stage)
            state = step.run(state, runtime)
            if step.output_stage != before_stage:
                state.stage = step.output_stage
            emit("step_done", step=step.name, stage=state.stage)
        return state
