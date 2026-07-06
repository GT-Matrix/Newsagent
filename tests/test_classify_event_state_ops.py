from __future__ import annotations

from datetime import datetime, timezone
import unittest

from modnews.core.models import EventRecord, NewsItem
from modnews.service.classify.event_state_ops import (
    assign_item_to_event,
    build_event_state,
    merge_event_records,
    new_event_id,
)
from modnews.service.classify.types import PreparedItem


class ClassifyEventStateOpsTest(unittest.TestCase):
    def test_new_event_id_uses_scrape_date_prefix(self) -> None:
        self.assertEqual(new_event_id("2026-07-06T10:00:00+08:00", 12), "evt_20260706_0012")

    def test_build_event_state_assign_and_merge_share_consistent_record_ops(self) -> None:
        state = build_event_state(
            scrape_date="2026-07-06T10:00:00+08:00",
            index=1,
            event_label="Event A",
            event_summary="Summary A",
            event_type="launch",
            key_entities=["A"],
            confidence=0.8,
        )
        item = NewsItem(platform="site-1", title="Title 1", url="https://example.com/1", pubtime=None, scrape_date="2026-07-06T10:00:00+08:00")
        entry = PreparedItem(
            index=3,
            item=item,
            normalized_title=item.title,
            domain="example.com",
            pubtime=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
        )

        assign_item_to_event(entry, state, 0.9)

        self.assertEqual(item.event_id, "evt_20260706_0001")
        self.assertEqual(item.classification_decision, "assign")
        self.assertEqual(state.record.member_count, 1)
        self.assertEqual(state.record.platforms, ["site-1"])
        self.assertEqual(state.record.source_news_ids, [3])
        self.assertEqual(state.record.confidence, 0.9)

        source = EventRecord(
            event_id="evt_20260706_0002",
            event_label="Event B",
            member_count=1,
            platforms=["site-2"],
            latest_pubtime="2026-07-06T11:00:00+00:00",
            representative_titles=["Title 2"],
            first_pubtime="2026-07-06T09:00:00+00:00",
            confidence=0.95,
            event_summary="Summary B",
            event_type="launch",
            key_entities=["B"],
            source_news_ids=[5],
            last_llm_updated_at="2026-07-06T10:00:00+08:00",
        )

        merge_event_records(state.record, source)

        self.assertEqual(state.record.member_count, 2)
        self.assertEqual(state.record.platforms, ["site-1", "site-2"])
        self.assertEqual(state.record.source_news_ids, [3, 5])
        self.assertEqual(state.record.key_entities, ["A", "B"])
        self.assertEqual(state.record.confidence, 0.95)
        self.assertEqual(state.record.latest_pubtime, "2026-07-06T11:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
