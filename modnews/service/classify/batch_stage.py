from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from modnews.core.progress import emit
from modnews.core.task import TaskEvent

from .batch_profile import BatchTaskProfile, run_profiled_batch
from .llm_client import LlmClient

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class LlmBatchStage(Generic[T]):
    profile: BatchTaskProfile
    llm_task: str
    request_event: str
    done_event: str
    system_prompt: str
    payload_key: str
    request_event_key: str
    build_payload: Callable[[T], object]


def run_llm_batch_stage(
    *,
    client: LlmClient,
    stage: LlmBatchStage[T],
    batches: list[T],
    max_workers: int,
) -> list[dict]:
    queue_task_type = stage.profile.queue_task_type
    batch_payload_builder = (lambda batch: batch) if queue_task_type else stage.build_payload
    items = (
        [
            {
                "payload": stage.build_payload(batch),
                "batch_index": batch_index,
                "batch_count": len(batches),
            }
            for batch_index, batch in enumerate(batches, start=1)
        ]
        if queue_task_type
        else [(batch, batch_index, len(batches)) for batch_index, batch in enumerate(batches, start=1)]
    )
    return run_profiled_batch(
        lambda args: _run_single_llm_batch(
            client=client,
            stage=stage,
            batch=args["payload"] if queue_task_type else args[0],
            batch_index=args["batch_index"] if queue_task_type else args[1],
            batch_count=args["batch_count"] if queue_task_type else args[2],
            build_payload=batch_payload_builder,
            request_event_key=stage.request_event_key,
        ),
        items,
        max_workers=max_workers,
        profile=stage.profile,
        batch_indexes=list(range(1, len(batches) + 1)),
        batch_count=len(batches),
    )


def run_llm_batch_task(
    *,
    client: LlmClient,
    stage: LlmBatchStage[T],
    task: TaskEvent,
    payload: T,
    request_event_key: str | None = None,
) -> dict:
    batch_index, batch_count = task_batch_progress(task)
    return _run_single_llm_batch(
        client=client,
        stage=stage,
        batch=payload,
        batch_index=batch_index,
        batch_count=batch_count,
        build_payload=lambda batch: batch,
        request_event_key=request_event_key or stage.request_event_key,
    )


def task_batch_progress(task: TaskEvent) -> tuple[int, int]:
    batch = task.payload.get("batch")
    if isinstance(batch, dict):
        batch_index = batch.get("batch_index")
        batch_count = batch.get("batch_count")
        if isinstance(batch_index, int) and isinstance(batch_count, int):
            return batch_index, batch_count
    if isinstance(batch, list) and batch and isinstance(batch[0], dict):
        batch_index = batch[0].get("batch_index")
        batch_count = batch[0].get("batch_count")
        if isinstance(batch_index, int) and isinstance(batch_count, int):
            return batch_index, batch_count
    return 1, 1


def _run_single_llm_batch(
    *,
    client: LlmClient,
    stage: LlmBatchStage[T],
    batch: T,
    batch_index: int,
    batch_count: int,
    build_payload: Callable[[T], object],
    request_event_key: str,
) -> dict:
    payload = build_payload(batch)
    emit(
        stage.request_event,
        batch_index=batch_index,
        batch_count=batch_count,
        **{request_event_key: payload},
    )
    response = client.complete_json(
        task=stage.llm_task,
        messages=[
            {"role": "system", "content": stage.system_prompt},
            {"role": "user", "content": json.dumps({stage.payload_key: payload}, ensure_ascii=False)},
        ],
    )
    emit(stage.done_event, batch_index=batch_index, batch_count=batch_count)
    return response
