from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modnews.service.report.io.event_loader import load_processed_candidates, resolve_report_input_path


class ReportEventLoaderTest(unittest.TestCase):
    def test_loads_classification_progress_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "classification_progress.json"
            path.write_text(
                json.dumps(
                    {
                        "meta": {"stage": "completed"},
                        "items": [
                            {
                                "platform": "huggingface",
                                "title": "Example title",
                                "url": "https://example.com/post",
                                "pubtime": "2026-07-03T08:00:00+00:00",
                                "scrape_date": "2026-07-03T16:00:00+08:00",
                                "event_id": "evt_1",
                                "classification_decision": "assign",
                                "classification_reason": "same event",
                            }
                        ],
                        "events": [
                            {
                                "event_id": "evt_1",
                                "event_label": "Example event",
                                "member_count": 1,
                                "platforms": ["huggingface"],
                                "latest_pubtime": "2026-07-03T08:00:00+00:00",
                                "representative_titles": ["Example title"],
                                "confidence": 0.9,
                                "event_summary": "Example summary",
                                "event_type": "research",
                                "key_entities": ["Example"],
                                "source_news_ids": [0],
                                "last_llm_updated_at": "2026-07-03T16:00:00+08:00",
                            }
                        ],
                        "discarded": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            candidates = load_processed_candidates(path)

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].event_id, "evt_1")
            self.assertEqual(len(candidates[0].source_items), 1)
            self.assertEqual(candidates[0].source_items[0].title, "Example title")

    def test_resolves_report_input_from_directory_and_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            artifact = base / "classification_progress.json"
            artifact.write_text(
                json.dumps({"items": [], "events": [], "discarded": [], "meta": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            checkpoint = base / "checkpoint.json"
            checkpoint.write_text(
                json.dumps({"output_refs": {"classification_progress": str(artifact)}}, ensure_ascii=False),
                encoding="utf-8",
            )

            self.assertEqual(resolve_report_input_path(base), artifact.resolve())
            self.assertEqual(resolve_report_input_path(checkpoint), artifact.resolve())


if __name__ == "__main__":
    unittest.main()
