from __future__ import annotations

from typing import Any

from modnews.core.progress import emit

from .batch_profile import CLUSTERED_EVENT_MERGE_BATCH
from .batch_stage import LlmBatchStage, run_llm_batch_stage
from .clustered_embedding import VectorRow, cluster_events, event_text, greedy_vector_groups
from .event_state_ops import merge_event_records
from .prompts import clustered_event_merge_system_prompt
from .utils import clean_list, clean_string, event_payload

CLUSTERED_MERGE_STAGE = LlmBatchStage[list[dict[str, object]]](
    profile=CLUSTERED_EVENT_MERGE_BATCH,
    llm_task="clustered_event_merge",
    request_event="clustered_merge_request",
    done_event="clustered_merge_batch_done",
    system_prompt=clustered_event_merge_system_prompt(),
    payload_key="events",
    request_event_key="events",
    build_payload=lambda batch: _batch_payload(batch),
)


def merge_event_clusters(
    client,
    retriever,
    events,
    config,
) -> int:
    batches = cluster_events(events, retriever, config.batch_size, config.batch_concurrency)
    emit(
        "clustered_merge_start",
        event_count=len(events),
        batch_count=len(batches),
        batch_size=config.batch_size,
        concurrency=max(1, config.batch_concurrency),
    )
    responses = run_llm_batch_stage(
        client=client,
        stage=CLUSTERED_MERGE_STAGE,
        batches=batches,
        max_workers=config.batch_concurrency,
    )
    merged_count = apply_clustered_merge_responses(events, responses)
    emit("clustered_merge_done", merged_event_count=merged_count, event_count=len(events))
    return merged_count


def build_event_merge_batches_from_vectors(
    events,
    vector_rows: list[dict[str, Any]],
    batch_size: int,
):
    vectors = [VectorRow(key=row["key"], vector=list(row["vector"])) for row in vector_rows]
    groups = greedy_vector_groups(vectors, batch_size)
    by_id = {state.record.event_id: state for state in events}
    return [[by_id[str(row.key)] for row in group] for group in groups]


def build_event_embedding_rows(events) -> list[dict[str, object]]:
    return [{"key": state.record.event_id, "text": event_text(state.record)} for state in events]


def apply_clustered_merge_responses(events, responses: list[dict[str, Any]]) -> int:
    by_id = {state.record.event_id: state for state in events}
    remove_ids: set[str] = set()
    merged_count = 0
    for response in responses:
        for group in response.get("merge_groups", []):
            target_id = clean_string(group.get("target_event_id"))
            if not target_id or target_id not in by_id or target_id in remove_ids:
                continue
            target = by_id[target_id]
            source_ids = [
                event_id
                for event_id in clean_list(group.get("source_event_ids"))
                if event_id in by_id and event_id != target_id and event_id not in remove_ids
            ]
            if not source_ids:
                continue
            label = clean_string(group.get("event_label"))
            summary = clean_string(group.get("event_summary"))
            if label:
                target.record.event_label = label
            if summary:
                target.record.event_summary = summary
            for source_id in source_ids:
                merge_event_records(target.record, by_id[source_id].record)
                remove_ids.add(source_id)
                merged_count += 1
            emit("clustered_merge_decision", target_event_id=target_id, source_event_ids=source_ids)

    if remove_ids:
        events[:] = [state for state in events if state.record.event_id not in remove_ids]
    return merged_count


def _batch_payload(batch) -> list[dict[str, object]]:
    return [event_payload(state.record) for state in batch]
