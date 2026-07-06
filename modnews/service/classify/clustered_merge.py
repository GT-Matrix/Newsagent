from __future__ import annotations

from modnews.core.progress import emit

from .batch_profile import CLUSTERED_EVENT_MERGE_BATCH
from .batch_stage import LlmBatchStage, run_llm_batch_stage
from .clustered_embedding import cluster_events
from .prompts import clustered_event_merge_system_prompt
from .utils import clean_list, clean_string, event_payload, parse_datetime

CLUSTERED_MERGE_STAGE = LlmBatchStage[list[dict[str, object]]](
    profile=CLUSTERED_EVENT_MERGE_BATCH,
    llm_task="clustered_event_merge",
    request_event="clustered_merge_request",
    done_event="clustered_merge_batch_done",
    system_prompt=clustered_event_merge_system_prompt(),
    payload_key="events",
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
        build_payload=_batch_payload,
        request_event_key="events",
    )

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
    emit("clustered_merge_done", merged_event_count=merged_count, event_count=len(events))
    return merged_count


def _batch_payload(batch) -> list[dict[str, object]]:
    return [event_payload(state.record) for state in batch]


def merge_event_records(target, source) -> None:
    target.platforms = sorted(set(target.platforms) | set(source.platforms))
    target.representative_titles = sorted(
        set(target.representative_titles) | set(source.representative_titles),
        key=lambda value: (len(value), value),
    )[:5]
    target.source_news_ids = sorted(set(target.source_news_ids) | set(source.source_news_ids))
    target.member_count = len(target.source_news_ids)
    target.key_entities = sorted(set(target.key_entities) | set(source.key_entities))
    target.event_type = target.event_type or source.event_type
    target.event_summary = target.event_summary or source.event_summary
    if source.confidence is not None and (target.confidence is None or source.confidence > target.confidence):
        target.confidence = source.confidence
    first_left = parse_datetime(target.first_pubtime)
    first_right = parse_datetime(source.first_pubtime)
    if first_right and (first_left is None or first_right < first_left):
        target.first_pubtime = source.first_pubtime
    latest_left = parse_datetime(target.latest_pubtime)
    latest_right = parse_datetime(source.latest_pubtime)
    if latest_right and (latest_left is None or latest_right > latest_left):
        target.latest_pubtime = source.latest_pubtime
