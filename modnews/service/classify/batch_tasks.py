from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.task import TaskEvent

from .batch_stage import run_llm_batch_task
from .batch_stage import LlmBatchStage
from .llm_client import LlmClient
from .llm_batch_registry import REGISTERED_LLM_BATCH_STAGES, get_registered_llm_batch_stage
from .retriever import EventVectorRetriever

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class BatchTaskExecutorSpec:
    task_type: str
    executor: Callable[[TaskEvent], dict[str, object]]


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


BATCH_TASK_EXECUTOR_SPECS: tuple[BatchTaskExecutorSpec, ...] = (
    BatchTaskExecutorSpec(
        task_type="classify.embedding",
        executor=run_embedding_batch_item,
    ),
    *(
        BatchTaskExecutorSpec(
            task_type=spec.task_type,
            executor=run_registered_llm_batch_item,
        )
        for spec in REGISTERED_LLM_BATCH_STAGES
    ),
)

BATCH_TASK_EXECUTORS: dict[str, Callable[[TaskEvent], dict[str, object]]] = {
    spec.task_type: spec.executor
    for spec in BATCH_TASK_EXECUTOR_SPECS
}
