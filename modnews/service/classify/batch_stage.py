from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from modnews.core.progress import emit

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


def run_llm_batch_stage(
    *,
    client: LlmClient,
    stage: LlmBatchStage[T],
    batches: list[T],
    max_workers: int,
    build_payload: Callable[[T], object],
    request_event_key: str,
) -> list[dict]:
    return run_profiled_batch(
        lambda args: _run_single_llm_batch(
            client=client,
            stage=stage,
            batch=args[0],
            batch_index=args[1],
            batch_count=args[2],
            build_payload=build_payload,
            request_event_key=request_event_key,
        ),
        [(batch, batch_index, len(batches)) for batch_index, batch in enumerate(batches, start=1)],
        max_workers=max_workers,
        profile=stage.profile,
        batch_indexes=list(range(1, len(batches) + 1)),
        batch_count=len(batches),
    )


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
