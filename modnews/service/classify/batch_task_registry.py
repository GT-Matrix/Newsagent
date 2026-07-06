from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.task import TaskEvent

from .batch_profile import (
    BatchTaskProfile,
    CLUSTERED_EMBEDDING_BATCH,
    CLUSTERED_EVENT_EXTRACTION_BATCH,
    CLUSTERED_EVENT_MERGE_BATCH,
)
from .batch_stage import LlmBatchStage, run_llm_batch_task
from .clustered_extract import CLUSTERED_EXTRACTION_STAGE
from .clustered_merge import CLUSTERED_MERGE_STAGE
from .llm_client import LlmClient
from .retriever import EventVectorRetriever

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RegisteredLlmBatchStage:
    stage: LlmBatchStage[T]
    payload_loader: Callable[[object], T]

    @property
    def task_type(self) -> str:
        return self.stage.profile.task_type


@dataclass(frozen=True, slots=True)
class RegisteredBatchTask:
    profile: BatchTaskProfile
    executor: Callable[[TaskEvent], dict[str, object]]
    llm_stage: RegisteredLlmBatchStage | None = None

    @property
    def task_type(self) -> str:
        return self.profile.task_type


def run_embedding_batch_item(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    config = load_config(task.payload.get("config"), project_root=project_root)
    ctx = PipelineContext.create(config)
    retriever = EventVectorRetriever(config.classification.embedding, ctx.session)
    item_payload = task.payload.get("item_payload") if isinstance(task.payload.get("item_payload"), dict) else {}
    key = item_payload.get("key")
    text = str(item_payload.get("text") or "")
    return {
        "batch_result": {
            "key": key,
            "vector": retriever.embed_text_for_clustering(text),
        }
    }


def run_clustered_event_extraction_batch_item(task: TaskEvent) -> dict[str, object]:
    return run_registered_llm_batch_item(task)


def run_clustered_event_merge_batch_item(task: TaskEvent) -> dict[str, object]:
    return run_registered_llm_batch_item(task)


def run_registered_llm_batch_item(task: TaskEvent) -> dict[str, object]:
    spec = get_registered_llm_batch_stage(task.type)
    return _run_llm_batch_stage_task(
        task,
        stage=spec.stage,
        payload_loader=spec.payload_loader,
    )


def _run_llm_batch_stage_task(
    task: TaskEvent,
    *,
    stage: LlmBatchStage[T],
    payload_loader: Callable[[object], T],
) -> dict[str, object]:
    client = _build_llm_client(task)
    response = run_llm_batch_task(
        client=client,
        stage=stage,
        task=task,
        payload=payload_loader(task.payload.get("item_payload")),
    )
    return {"batch_result": response}


def _build_llm_client(task: TaskEvent) -> LlmClient:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    config = load_config(task.payload.get("config"), project_root=project_root)
    ctx = PipelineContext.create(config)
    return LlmClient(config.classification.llm, ctx.session)


REGISTERED_BATCH_TASKS: tuple[RegisteredBatchTask, ...] = (
    RegisteredBatchTask(
        profile=CLUSTERED_EMBEDDING_BATCH,
        executor=run_embedding_batch_item,
    ),
    RegisteredBatchTask(
        profile=CLUSTERED_EVENT_EXTRACTION_BATCH,
        executor=run_clustered_event_extraction_batch_item,
        llm_stage=RegisteredLlmBatchStage(
            stage=CLUSTERED_EXTRACTION_STAGE,
            payload_loader=lambda payload: payload if isinstance(payload, list) else [],
        ),
    ),
    RegisteredBatchTask(
        profile=CLUSTERED_EVENT_MERGE_BATCH,
        executor=run_clustered_event_merge_batch_item,
        llm_stage=RegisteredLlmBatchStage(
            stage=CLUSTERED_MERGE_STAGE,
            payload_loader=lambda payload: payload if isinstance(payload, list) else [],
        ),
    ),
)

REGISTERED_BATCH_TASK_BY_TYPE: dict[str, RegisteredBatchTask] = {
    spec.task_type: spec
    for spec in REGISTERED_BATCH_TASKS
}

REGISTERED_LLM_BATCH_STAGES: tuple[RegisteredLlmBatchStage, ...] = tuple(
    spec.llm_stage
    for spec in REGISTERED_BATCH_TASKS
    if spec.llm_stage is not None
)

REGISTERED_LLM_BATCH_STAGE_BY_TASK_TYPE: dict[str, RegisteredLlmBatchStage] = {
    spec.task_type: spec
    for spec in REGISTERED_LLM_BATCH_STAGES
}

BATCH_TASK_EXECUTORS: dict[str, Callable[[TaskEvent], dict[str, object]]] = {
    spec.task_type: spec.executor
    for spec in REGISTERED_BATCH_TASKS
}


def get_registered_batch_task(task_type: str) -> RegisteredBatchTask:
    return REGISTERED_BATCH_TASK_BY_TYPE[task_type]


def get_registered_llm_batch_stage(task_type: str) -> RegisteredLlmBatchStage:
    return REGISTERED_LLM_BATCH_STAGE_BY_TASK_TYPE[task_type]
