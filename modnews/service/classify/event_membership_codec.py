from __future__ import annotations

import json
from typing import Any

from .prompts import membership_system_prompt
from .types import EventState, PreparedItem
from .utils import clean_event_type, clean_list, clean_string, event_payload, news_payload, normalize_confidence


def build_membership_candidate_payload(
    entry: PreparedItem,
    candidates: list[EventState],
) -> dict[str, object]:
    return {
        "news": news_payload(entry),
        "candidate_events": [event_payload(candidate.record) for candidate in candidates],
    }


def build_membership_messages(
    entry: PreparedItem,
    candidates: list[EventState],
) -> list[dict[str, str]]:
    payload = build_membership_candidate_payload(entry, candidates)
    return [
        {"role": "system", "content": membership_system_prompt()},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def decode_membership_decision(decision: dict[str, Any]) -> dict[str, object]:
    return {
        "action": str(decision.get("decision", "discard")).lower(),
        "matched_event_id": clean_string(decision.get("matched_event_id")),
        "event_label": clean_string(decision.get("event_label")),
        "event_summary": clean_string(decision.get("event_summary")),
        "event_type": clean_event_type(decision.get("event_type")),
        "key_entities": clean_list(decision.get("key_entities")),
        "confidence": normalize_confidence(decision.get("confidence")),
        "reason": clean_string(decision.get("reason")),
    }
