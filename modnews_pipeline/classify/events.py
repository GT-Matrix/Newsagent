from __future__ import annotations

import json

from modnews_pipeline.config import ClassificationConfig
from modnews_pipeline.context import PipelineContext
from modnews_pipeline.models import EventRecord
from modnews_pipeline.progress import emit

from .llm_client import LlmClient
from .prompts import membership_system_prompt, merge_system_prompt
from .retriever import EventVectorRetriever
from .types import DiscardedRecord, EventState, PreparedItem
from .utils import clean_event_type, clean_list, clean_string, discard, event_payload, news_payload, normalize_confidence, parse_datetime


def decide_event_membership(
    client: LlmClient,
    entry: PreparedItem,
    candidates: list[EventState],
) -> dict:
    emit(
        "membership_candidates",
        index=entry.index,
        news=news_payload(entry),
        candidates=[event_payload(candidate.record) for candidate in candidates],
    )
    return client.complete_json(
        task="event_membership",
        messages=[
            {"role": "system", "content": membership_system_prompt()},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "news": news_payload(entry),
                        "candidate_events": [event_payload(candidate.record) for candidate in candidates],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    )


def apply_event_decision(
    ctx: PipelineContext,
    entry: PreparedItem,
    decision: dict,
    events: list[EventState],
    discarded: list[DiscardedRecord],
) -> None:
    item = entry.item
    action = str(decision.get("decision", "discard")).lower()
    confidence = normalize_confidence(decision.get("confidence"))
    reason = clean_string(decision.get("reason"))
    item.classification_reason = reason

    if action == "assign":
        event_id = clean_string(decision.get("matched_event_id"))
        target = next((event for event in events if event.record.event_id == event_id), None)
        if target is not None:
            assign_item_to_event(entry, target, confidence)
            emit(
                "membership_decision",
                index=entry.index,
                decision="assign",
                event_id=target.record.event_id,
                confidence=confidence,
                reason=reason,
            )
            return
        action = "create"

    if action == "create":
        event_id = _new_event_id(ctx.scrape_date, len(events) + 1)
        event = EventRecord(
            event_id=event_id,
            event_label=clean_string(decision.get("event_label")) or item.canonical_summary or item.title,
            member_count=0,
            platforms=[],
            latest_pubtime=None,
            representative_titles=[],
            confidence=confidence,
            event_summary=clean_string(decision.get("event_summary")) or item.canonical_summary,
            event_type=clean_event_type(decision.get("event_type") or item.event_type),
            key_entities=clean_list(decision.get("key_entities")) or item.entities,
            source_news_ids=[],
            last_llm_updated_at=ctx.scrape_date,
        )
        state = EventState(record=event)
        events.append(state)
        assign_item_to_event(entry, state, confidence)
        emit(
            "membership_decision",
            index=entry.index,
            decision="create",
            event_id=event.event_id,
            confidence=confidence,
            reason=reason,
        )
        return

    item.classification_decision = "discard"
    item.is_ai_relevant = False
    discarded.append(discard(entry.index, item, "event_membership", reason or "LLM discarded during event matching"))
    emit("membership_decision", index=entry.index, decision="discard", confidence=confidence, reason=reason)


def assign_item_to_event(entry: PreparedItem, state: EventState, confidence: float | None) -> None:
    item = entry.item
    record = state.record
    item.event_id = record.event_id
    item.event_label = record.event_label
    item.event_confidence = confidence if confidence is not None else record.confidence
    item.classification_decision = "assign"
    item.is_ai_relevant = True

    platforms = set(record.platforms)
    platforms.add(item.platform)
    record.platforms = sorted(platforms)
    if entry.index not in record.source_news_ids:
        record.source_news_ids.append(entry.index)
    titles = [*record.representative_titles, item.title]
    record.representative_titles = sorted(set(titles), key=lambda value: (len(value), value))[:5]
    record.member_count = len(record.source_news_ids)
    if record.confidence is None or (confidence is not None and confidence > record.confidence):
        record.confidence = confidence
    if entry.pubtime:
        first = parse_datetime(record.first_pubtime)
        latest = parse_datetime(record.latest_pubtime)
        if first is None or entry.pubtime < first:
            record.first_pubtime = entry.pubtime.isoformat()
        if latest is None or entry.pubtime > latest:
            record.latest_pubtime = entry.pubtime.isoformat()


def merge_similar_events(
    client: LlmClient,
    events: list[EventState],
    config: ClassificationConfig,
    retriever: EventVectorRetriever,
) -> int:
    total_merged = 0
    for round_index in range(1, 3):
        emit("merge_round_start", round=round_index, event_count=len(events))
        merge_groups = _run_merge_round(client, events, config, retriever, round_index)
        if not merge_groups:
            emit("merge_round_done", round=round_index, merged_group_count=0)
            break
        total_merged += len(merge_groups)
        _apply_merge_groups(events, merge_groups)
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


def _run_merge_round(
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
        candidates = _recall_merge_candidates(state, events, config, retriever, skipped)
        if not candidates:
            continue
        emit(
            "merge_candidates",
            round=round_index,
            seed_event=event_payload(state.record),
            candidates=[event_payload(candidate.record) for candidate in candidates],
        )
        response = client.complete_json(
            task="event_merge_group",
            messages=[
                {"role": "system", "content": merge_system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "seed_event": event_payload(state.record),
                            "candidate_events": [event_payload(candidate.record) for candidate in candidates],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        allowed = {candidate.record.event_id for candidate in candidates}
        selected = {
            event_id
            for event_id in clean_list(response.get("merge_event_ids"))
            if event_id in allowed and event_id in by_id
        }
        if selected:
            merge_groups.setdefault(seed_id, set()).update(selected)
            skipped.update(selected)
            emit("merge_decision", round=round_index, seed_event_id=seed_id, merge_event_ids=sorted(selected))
        else:
            emit("merge_decision", round=round_index, seed_event_id=seed_id, merge_event_ids=[])
    return merge_groups


def _recall_merge_candidates(
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


def _apply_merge_groups(events: list[EventState], merge_groups: dict[str, set[str]]) -> None:
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
            _merge_event_records(target.record, source.record)
            remove_ids.add(source_id)
    if remove_ids:
        events[:] = [state for state in events if state.record.event_id not in remove_ids]


def _merge_event_records(target: EventRecord, source: EventRecord) -> None:
    target.event_summary = target.event_summary or source.event_summary
    target.event_type = target.event_type or source.event_type
    target.platforms = sorted(set(target.platforms) | set(source.platforms))
    target.representative_titles = sorted(
        set(target.representative_titles) | set(source.representative_titles),
        key=lambda value: (len(value), value),
    )[:5]
    target.source_news_ids = sorted(set(target.source_news_ids) | set(source.source_news_ids))
    target.member_count = len(target.source_news_ids)
    target.key_entities = sorted(set(target.key_entities) | set(source.key_entities))
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


def _new_event_id(scrape_date: str, index: int) -> str:
    date_part = scrape_date[:10].replace("-", "")
    return f"evt_{date_part}_{index:04d}"
