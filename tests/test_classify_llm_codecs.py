from __future__ import annotations

import json
import unittest

from modnews.core.models import EventRecord, NewsItem
from modnews.service.classify.event_membership_codec import (
    build_membership_candidate_payload,
    build_membership_messages,
    decode_membership_decision,
)
from modnews.service.classify.event_merge_codec import (
    build_merge_candidate_payload,
    build_merge_messages,
    decode_merge_event_ids,
)
from modnews.service.classify.types import EventState, PreparedItem


class ClassifyLlmCodecsTest(unittest.TestCase):
    def test_membership_codec_builds_payload_and_messages(self) -> None:
        item = NewsItem(platform="x", title="title", url="https://example.com", pubtime=None, scrape_date="2026-07-03")
        entry = PreparedItem(index=1, item=item, normalized_title="title", domain="example.com", pubtime=None)
        candidate = EventState(EventRecord(event_id="e1", event_label="label", member_count=1, platforms=["x"], latest_pubtime=None, representative_titles=["title"]))

        payload = build_membership_candidate_payload(entry, [candidate])
        messages = build_membership_messages(entry, [candidate])

        self.assertEqual(payload["news"]["title"], "title")
        self.assertEqual(payload["candidate_events"][0]["event_id"], "e1")
        self.assertEqual(json.loads(messages[1]["content"]), payload)

    def test_membership_codec_decodes_normalized_decision(self) -> None:
        decoded = decode_membership_decision(
            {
                "decision": "create",
                "event_label": "label",
                "event_summary": "summary",
                "event_type": "company",
                "key_entities": ["a"],
                "confidence": 91,
                "reason": "ok",
            }
        )

        self.assertEqual(decoded["action"], "create")
        self.assertEqual(decoded["event_type"], "company")
        self.assertEqual(decoded["key_entities"], ["a"])
        self.assertEqual(decoded["confidence"], 0.91)

    def test_merge_codec_builds_payload_and_filters_selected_ids(self) -> None:
        seed = EventState(EventRecord(event_id="e1", event_label="seed", member_count=1, platforms=["x"], latest_pubtime=None, representative_titles=["seed"]))
        candidate = EventState(EventRecord(event_id="e2", event_label="candidate", member_count=1, platforms=["y"], latest_pubtime=None, representative_titles=["candidate"]))

        payload = build_merge_candidate_payload(seed, [candidate])
        messages = build_merge_messages(seed, [candidate])
        selected = decode_merge_event_ids(
            {"merge_event_ids": ["e2", "missing"]},
            allowed_event_ids={"e2"},
            known_event_ids={"e1", "e2"},
        )

        self.assertEqual(payload["seed_event"]["event_id"], "e1")
        self.assertEqual(payload["candidate_events"][0]["event_id"], "e2")
        self.assertEqual(json.loads(messages[1]["content"]), payload)
        self.assertEqual(selected, {"e2"})


if __name__ == "__main__":
    unittest.main()
