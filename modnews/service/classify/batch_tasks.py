from __future__ import annotations

import json
from pathlib import Path

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.progress import emit
from modnews.core.task import TaskEvent

from .llm_client import LlmClient
from .prompts import (
    batch_relevance_system_prompt,
    clustered_event_extraction_system_prompt,
    clustered_event_merge_system_prompt,
)
from .retriever import EventVectorRetriever


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


def run_relevance_batch_item(task: TaskEvent) -> dict[str, object]:
    client = _build_llm_client(task)
    item_payload = task.payload.get("item_payload")
    items = item_payload if isinstance(item_payload, list) else []
    response = client.complete_json(
        task="batch_ai_relevance",
        messages=[
            {"role": "system", "content": batch_relevance_system_prompt()},
            {"role": "user", "content": json.dumps({"items": items}, ensure_ascii=False)},
        ],
    )
    return {"batch_result": response}


def run_clustered_event_extraction_batch_item(task: TaskEvent) -> dict[str, object]:
    client = _build_llm_client(task)
    item_payload = task.payload.get("item_payload")
    items = item_payload if isinstance(item_payload, list) else []
    batch_index, batch_count = _batch_progress(task)
    response = _run_llm_batch_item(
        client=client,
        task_name="clustered_event_extraction",
        request_event="clustered_extraction_request",
        done_event="clustered_extraction_batch_done",
        request_event_key="items",
        system_prompt=clustered_event_extraction_system_prompt(),
        payload_key="items",
        payload=items,
        batch_index=batch_index,
        batch_count=batch_count,
    )
    return {"batch_result": response}


def run_clustered_event_merge_batch_item(task: TaskEvent) -> dict[str, object]:
    client = _build_llm_client(task)
    item_payload = task.payload.get("item_payload")
    events = item_payload if isinstance(item_payload, list) else []
    batch_index, batch_count = _batch_progress(task)
    response = _run_llm_batch_item(
        client=client,
        task_name="clustered_event_merge",
        request_event="clustered_merge_request",
        done_event="clustered_merge_batch_done",
        request_event_key="events",
        system_prompt=clustered_event_merge_system_prompt(),
        payload_key="events",
        payload=events,
        batch_index=batch_index,
        batch_count=batch_count,
    )
    return {"batch_result": response}


def _build_llm_client(task: TaskEvent) -> LlmClient:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    config = load_config(task.payload.get("config"), project_root=project_root)
    ctx = PipelineContext.create(config)
    return LlmClient(config.classification.llm, ctx.session)


def _batch_progress(task: TaskEvent) -> tuple[int, int]:
    batch = task.payload.get("batch")
    if isinstance(batch, list) and batch and isinstance(batch[0], dict):
        batch_index = batch[0].get("batch_index")
        batch_count = batch[0].get("batch_count")
        if isinstance(batch_index, int) and isinstance(batch_count, int):
            return batch_index, batch_count
    return 1, 1


def _run_llm_batch_item(
    *,
    client: LlmClient,
    task_name: str,
    request_event: str,
    done_event: str,
    request_event_key: str,
    system_prompt: str,
    payload_key: str,
    payload: list[dict[str, object]],
    batch_index: int,
    batch_count: int,
) -> dict[str, object]:
    emit(
        request_event,
        batch_index=batch_index,
        batch_count=batch_count,
        **{request_event_key: payload},
    )
    response = client.complete_json(
        task=task_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({payload_key: payload}, ensure_ascii=False)},
        ],
    )
    emit(done_event, batch_index=batch_index, batch_count=batch_count)
    return response
