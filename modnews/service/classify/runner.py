from __future__ import annotations

from dataclasses import dataclass

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
