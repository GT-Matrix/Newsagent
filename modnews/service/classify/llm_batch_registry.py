from __future__ import annotations

from .batch_task_registry import (
    REGISTERED_LLM_BATCH_STAGES,
    REGISTERED_LLM_BATCH_STAGE_BY_TASK_TYPE,
    RegisteredLlmBatchStage,
    get_registered_llm_batch_stage,
)

COMPATIBILITY_SHIM = True

__all__ = [
    "COMPATIBILITY_SHIM",
    "REGISTERED_LLM_BATCH_STAGES",
    "REGISTERED_LLM_BATCH_STAGE_BY_TASK_TYPE",
    "RegisteredLlmBatchStage",
    "get_registered_llm_batch_stage",
]
