from __future__ import annotations

from modnews.core.config import ClassificationConfig
from modnews.core.progress import emit

from .event_merge_codec import build_merge_candidate_payload, build_merge_messages, decode_merge_event_ids
from .event_state_ops import merge_event_records
from .llm_client import LlmClient
from .retriever import EventVectorRetriever
from .types import EventState, PreparedItem


def merge_similar_events(
    client: LlmClient,
    events: list[EventState],
    config: ClassificationConfig,
    retriever: EventVectorRetriever,
) -> int:
    total_merged = 0
    for round_index in range(1, 3):
        emit("merge_round_start", round=round_index, event_count=len(events))
        merge_groups = run_merge_round(client, events, config, retriever, round_index)
        if not merge_groups:
            emit("merge_round_done", round=round_index, merged_group_count=0)
            break
        total_merged += len(merge_groups)
        apply_merge_groups(events, merge_groups)
        emit("merge_round_done", round=round_index, merged_group_count=len(merge_groups), event_count=len(events))
    return total_merged


def recall_event_candidates(
    entry: PreparedItem,
    events: list[EventState],
    config: ClassificationConfig,
    retriever: EventVectorRetriever,
) -> list[EventState]:
    records = retriever.search(
        item=entry.item,
        item_pubtime=entry.pubtime,
        events=[state.record for state in events],
        limit=config.event_candidate_count,
        time_window_hours=config.time_window_hours,
    )
    by_id = {state.record.event_id: state for state in events}
    return [by_id[record.event_id] for record in records if record.event_id in by_id]


def run_merge_round(
    client: LlmClient,
    events: list[EventState],
    config: ClassificationConfig,
    retriever: EventVectorRetriever,
    round_index: int,
) -> dict[str, set[str]]:
    skipped: set[str] = set()
    merge_groups: dict[str, set[str]] = {}
    by_id = {state.record.event_id: state for state in events}
    for state in events:
        seed_id = state.record.event_id
        if seed_id in skipped:
            continue
        candidates = recall_merge_candidates(state, events, config, retriever, skipped)
        if not candidates:
            continue
        payload = build_merge_candidate_payload(state, candidates)
        emit(
            "merge_candidates",
            round=round_index,
            seed_event=payload["seed_event"],
            candidates=payload["candidate_events"],
        )
        response = client.complete_json(
            task="event_merge_group",
            messages=build_merge_messages(state, candidates),
        )
        allowed = {candidate.record.event_id for candidate in candidates}
        selected = decode_merge_event_ids(response, allowed_event_ids=allowed, known_event_ids=set(by_id))
        if selected:
            merge_groups.setdefault(seed_id, set()).update(selected)
            skipped.update(selected)
            emit("merge_decision", round=round_index, seed_event_id=seed_id, merge_event_ids=sorted(selected))
        else:
            emit("merge_decision", round=round_index, seed_event_id=seed_id, merge_event_ids=[])
    return merge_groups


def recall_merge_candidates(
    current: EventState,
    events: list[EventState],
    config: ClassificationConfig,
    retriever: EventVectorRetriever,
    skipped: set[str],
) -> list[EventState]:
    candidates = [state for state in events if state.record.event_id not in skipped and state is not current]
    records = retriever.search_for_event(
        seed=current.record,
        events=[state.record for state in candidates],
        limit=config.merge_candidate_count,
        time_window_hours=config.time_window_hours,
    )
    by_id = {state.record.event_id: state for state in candidates}
    return [by_id[record.event_id] for record in records if record.event_id in by_id]


def apply_merge_groups(events: list[EventState], merge_groups: dict[str, set[str]]) -> None:
    by_id = {state.record.event_id: state for state in events}
    remove_ids: set[str] = set()
    for target_id, source_ids in merge_groups.items():
        target = by_id.get(target_id)
        if target is None or target_id in remove_ids:
            continue
        for source_id in sorted(source_ids):
            if source_id == target_id or source_id in remove_ids:
                continue
            source = by_id.get(source_id)
            if source is None:
                continue
            merge_event_records(target.record, source.record)
            remove_ids.add(source_id)
    if remove_ids:
        events[:] = [state for state in events if state.record.event_id not in remove_ids]
