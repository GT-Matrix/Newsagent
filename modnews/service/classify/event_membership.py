from __future__ import annotations

from modnews.core.context import PipelineContext
from modnews.core.progress import emit

from .event_membership_codec import build_membership_candidate_payload, build_membership_messages, decode_membership_decision
from .event_state_ops import assign_item_to_event, build_event_state
from .llm_client import LlmClient
from .types import DiscardedRecord, EventState, PreparedItem
from .utils import (
    clean_event_type,
    discard,
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
        state = build_event_state(
            scrape_date=ctx.scrape_date,
            index=len(events) + 1,
            event_label=str(decoded["event_label"] or item.canonical_summary or item.title),
            event_summary=str(decoded["event_summary"] or item.canonical_summary),
            event_type=clean_event_type(decoded["event_type"] or item.event_type),
            key_entities=list(decoded["key_entities"]) or item.entities,
            confidence=confidence,
        )
        events.append(state)
        assign_item_to_event(entry, state, confidence)
        emit(
            "membership_decision",
            index=entry.index,
            decision="create",
            event_id=state.record.event_id,
            confidence=confidence,
            reason=reason,
        )
        return

    item.classification_decision = "discard"
    item.is_ai_relevant = False
    discarded.append(discard(entry.index, item, "event_membership", reason or "LLM discarded during event matching"))
    emit("membership_decision", index=entry.index, decision="discard", confidence=confidence, reason=reason)
