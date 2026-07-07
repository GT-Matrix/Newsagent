from __future__ import annotations

from datetime import datetime, timezone
import unittest

from modnews.core.models import EventRecord, NewsItem
from modnews.service.classify.retriever_ops import (
    cosine_similarity,
    event_text,
    news_text,
    outside_time_window,
    parse_datetime,
    rank_event_candidates,
)


class ClassifyRetrieverOpsTest(unittest.TestCase):
    def test_text_serializers_skip_empty_parts(self) -> None:
        item = NewsItem(
            platform="site-1",
            title="Title",
            url="https://example.com/1",
            pubtime=None,
            scrape_date="2026-07-06T10:00:00+08:00",
            canonical_summary="Summary",
            entities=["A", "B"],
            event_type="launch",
        )
        event = EventRecord(
            event_id="evt_1",
            event_label="Event",
            member_count=1,
            platforms=["site-1"],
            latest_pubtime=None,
            representative_titles=["T1", "T2"],
            event_summary="Summary",
            event_type="launch",
            key_entities=["A"],
        )

        self.assertEqual(news_text(item), "Summary\nTitle\nA B\nlaunch")
        self.assertEqual(event_text(event), "Event\nSummary\nA\nlaunch\nT1\nT2")

    def test_rank_event_candidates_respects_similarity_and_time_window(self) -> None:
        older = EventRecord(
            event_id="evt_old",
            event_label="Old",
            member_count=1,
            platforms=["site-1"],
            latest_pubtime="2026-07-01T10:00:00+00:00",
            representative_titles=["Old"],
        )
        near = EventRecord(
            event_id="evt_near",
            event_label="Near",
            member_count=1,
            platforms=["site-2"],
            latest_pubtime="2026-07-06T09:00:00+00:00",
            representative_titles=["Near"],
        )
        strong = EventRecord(
            event_id="evt_strong",
            event_label="Strong",
            member_count=1,
            platforms=["site-3"],
            latest_pubtime="2026-07-06T08:30:00+00:00",
            representative_titles=["Strong"],
        )
        vectors = {
            "evt_old": [0.99, 0.01],
            "evt_near": [0.5, 0.5],
            "evt_strong": [1.0, 0.0],
        }

        ranked = rank_event_candidates(
            query_vector=[1.0, 0.0],
            query_pubtime=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
            events=[older, near, strong],
            limit=2,
            time_window_hours=12,
            vector_for_event=lambda event: vectors[event.event_id],
        )

        self.assertEqual([event.event_id for event in ranked], ["evt_strong", "evt_near"])

    def test_rank_event_candidates_can_exclude_seed_event(self) -> None:
        seed = EventRecord(event_id="evt_seed", event_label="Seed", member_count=1, platforms=["s"], latest_pubtime=None, representative_titles=["Seed"])
        other = EventRecord(event_id="evt_other", event_label="Other", member_count=1, platforms=["o"], latest_pubtime=None, representative_titles=["Other"])

        ranked = rank_event_candidates(
            query_vector=[1.0],
            query_pubtime=None,
            events=[seed, other],
            limit=2,
            time_window_hours=24,
            vector_for_event=lambda event: [1.0],
            exclude_event_id="evt_seed",
        )

        self.assertEqual([event.event_id for event in ranked], ["evt_other"])

    def test_similarity_and_datetime_helpers_are_defensive(self) -> None:
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertEqual(cosine_similarity([], [1.0]), 0.0)
        self.assertIsNotNone(parse_datetime("2026-07-06T10:00:00Z"))
        self.assertIsNone(parse_datetime("not-a-date"))
        self.assertTrue(
            outside_time_window(
                datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
                datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc),
                24,
            )
        )


if __name__ == "__main__":
    unittest.main()
