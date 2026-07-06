from __future__ import annotations

import json
from typing import Any

from .prompts import merge_system_prompt
from .types import EventState
from .utils import clean_list, event_payload


def build_merge_candidate_payload(
    seed: EventState,
    candidates: list[EventState],
) -> dict[str, object]:
    return {
        "seed_event": event_payload(seed.record),
        "candidate_events": [event_payload(candidate.record) for candidate in candidates],
    }


def build_merge_messages(
    seed: EventState,
    candidates: list[EventState],
) -> list[dict[str, str]]:
    payload = build_merge_candidate_payload(seed, candidates)
    return [
        {"role": "system", "content": merge_system_prompt()},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def decode_merge_event_ids(
    response: dict[str, Any],
    *,
    allowed_event_ids: set[str],
    known_event_ids: set[str],
) -> set[str]:
    return {
        event_id
        for event_id in clean_list(response.get("merge_event_ids"))
        if event_id in allowed_event_ids and event_id in known_event_ids
    }
