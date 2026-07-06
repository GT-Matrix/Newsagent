from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from .batch_stage import LlmBatchStage
from .clustered_extract import CLUSTERED_EXTRACTION_STAGE
from .clustered_merge import CLUSTERED_MERGE_STAGE

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RegisteredLlmBatchStage:
    task_type: str
    stage: LlmBatchStage[T]
    payload_loader: Callable[[object], T]


REGISTERED_LLM_BATCH_STAGES: tuple[RegisteredLlmBatchStage, ...] = (
    RegisteredLlmBatchStage(
        task_type="classify.clustered_event_extraction.batch",
        stage=CLUSTERED_EXTRACTION_STAGE,
        payload_loader=lambda payload: payload if isinstance(payload, list) else [],
    ),
    RegisteredLlmBatchStage(
        task_type="classify.clustered_event_merge.batch",
        stage=CLUSTERED_MERGE_STAGE,
        payload_loader=lambda payload: payload if isinstance(payload, list) else [],
    ),
)

REGISTERED_LLM_BATCH_STAGE_BY_TASK_TYPE: dict[str, RegisteredLlmBatchStage] = {
    spec.task_type: spec
    for spec in REGISTERED_LLM_BATCH_STAGES
}


def get_registered_llm_batch_stage(task_type: str) -> RegisteredLlmBatchStage:
    return REGISTERED_LLM_BATCH_STAGE_BY_TASK_TYPE[task_type]
