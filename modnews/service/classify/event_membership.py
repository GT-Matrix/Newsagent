from __future__ import annotations

from modnews.core.context import PipelineContext
from modnews.core.models import EventRecord
from modnews.core.progress import emit

from .event_membership_codec import build_membership_candidate_payload, build_membership_messages, decode_membership_decision
from .llm_client import LlmClient
from .types import DiscardedRecord, EventState, PreparedItem
from .utils import (
    clean_event_type,
    discard,
    parse_datetime,
)


def decide_event_membership(
    client: LlmClient,
    entry: PreparedItem,
    candidates: list[EventState],
) -> dict:
    payload = build_membership_candidate_payload(entry, candidates)
    emit(
        "membership_candidates",
        index=entry.index,
        news=payload["news"],
        candidates=payload["candidate_events"],
    )
    return client.complete_json(
        task="event_membership",
        messages=build_membership_messages(entry, candidates),
    )


def apply_event_decision(
    ctx: PipelineContext,
    entry: PreparedItem,
    decision: dict,
    events: list[EventState],
    discarded: list[DiscardedRecord],
) -> None:
    item = entry.item
    decoded = decode_membership_decision(decision)
    action = str(decoded["action"])
    confidence = decoded["confidence"]
    reason = decoded["reason"]
    item.classification_reason = reason

    if action == "assign":
        event_id = str(decoded["matched_event_id"] or "")
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
        event_id = new_event_id(ctx.scrape_date, len(events) + 1)
        event = EventRecord(
            event_id=event_id,
            event_label=str(decoded["event_label"] or item.canonical_summary or item.title),
            member_count=0,
            platforms=[],
            latest_pubtime=None,
            representative_titles=[],
            confidence=confidence,
            event_summary=str(decoded["event_summary"] or item.canonical_summary),
            event_type=clean_event_type(decoded["event_type"] or item.event_type),
            key_entities=list(decoded["key_entities"]) or item.entities,
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


def new_event_id(scrape_date: str, index: int) -> str:
    date_part = scrape_date[:10].replace("-", "")
    return f"evt_{date_part}_{index:04d}"
