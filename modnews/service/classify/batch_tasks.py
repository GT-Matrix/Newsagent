from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.task import TaskEvent

from .batch_stage import run_llm_batch_task
from .clustered_extract import CLUSTERED_EXTRACTION_STAGE
from .clustered_merge import CLUSTERED_MERGE_STAGE
from .batch_stage import LlmBatchStage
from .llm_client import LlmClient
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
    return _run_llm_batch_stage_task(
        task,
        stage=CLUSTERED_EXTRACTION_STAGE,
        payload_loader=lambda payload: payload if isinstance(payload, list) else [],
    )


def run_clustered_event_merge_batch_item(task: TaskEvent) -> dict[str, object]:
    return _run_llm_batch_stage_task(
        task,
        stage=CLUSTERED_MERGE_STAGE,
        payload_loader=lambda payload: payload if isinstance(payload, list) else [],
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
    BatchTaskExecutorSpec(
        task_type="classify.clustered_event_extraction.batch",
        executor=run_clustered_event_extraction_batch_item,
    ),
    BatchTaskExecutorSpec(
        task_type="classify.clustered_event_merge.batch",
        executor=run_clustered_event_merge_batch_item,
    ),
)

BATCH_TASK_EXECUTORS: dict[str, Callable[[TaskEvent], dict[str, object]]] = {
    spec.task_type: spec.executor
    for spec in BATCH_TASK_EXECUTOR_SPECS
}
