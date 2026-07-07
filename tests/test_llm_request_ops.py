from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from modnews.core.config import LlmConfig
from modnews.service.classify.llm_request_ops import (
    build_llm_request_context,
    emit_cached_llm_response,
    ensure_llm_request_config,
)


class LlmRequestOpsTest(unittest.TestCase):
    def test_build_request_context_compacts_messages_and_descriptor(self) -> None:
        context = build_llm_request_context(
            "event_membership",
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "{\"news\": {\"title\": \"user\"}, \"candidate_events\": []}"},
            ],
        )

        self.assertTrue(str(context["request_id"]).startswith("event_membership-"))
        self.assertEqual(context["descriptor"]["name"], "事件归并")
        self.assertEqual(len(context["compact_messages"]), 2)

    def test_emit_cached_llm_response_can_skip_or_simulate_stream(self) -> None:
        config = LlmConfig(model="m1", simulate_cache_stream=False)
        with patch("modnews.service.classify.llm_request_ops.emit") as emit_mock, patch(
            "modnews.service.classify.llm_request_ops.simulate_stream"
        ) as simulate_mock:
            emit_cached_llm_response(
                config=config,
                task="task-a",
                request_id="req-1",
                descriptor={"name": "task-a"},
                compacted_messages=[{"role": "user", "content": "hello"}],
                cached={"ok": True},
            )

        simulate_mock.assert_not_called()
        self.assertEqual(emit_mock.call_count, 1)

        config = LlmConfig(
            model="m1",
            simulate_cache_stream=True,
            cache_first_token_delay_seconds=0.01,
            cache_tokens_per_second=100.0,
        )
        with patch("modnews.service.classify.llm_request_ops.emit") as emit_mock, patch(
            "modnews.service.classify.llm_request_ops.simulate_stream"
        ) as simulate_mock:
            emit_cached_llm_response(
                config=config,
                task="task-a",
                request_id="req-1",
                descriptor={"name": "task-a"},
                compacted_messages=[{"role": "user", "content": "hello"}],
                cached={"ok": True},
            )

        simulate_mock.assert_called_once()
        self.assertEqual(emit_mock.call_count, 3)

    def test_ensure_llm_request_config_requires_base_url_and_api_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "LLM_BASE_URL"):
            ensure_llm_request_config(LlmConfig(model="m1", api_key="k"))
        with self.assertRaisesRegex(ValueError, "LLM_API_KEY"):
            ensure_llm_request_config(LlmConfig(model="m1", base_url="https://example.com/v1"))

        self.assertEqual(
            ensure_llm_request_config(
                LlmConfig(model="m1", base_url="https://example.com/v1/", api_key="k", cache_path=Path("/tmp/cache.sqlite3"))
            ),
            "https://example.com/v1/chat/completions",
        )


if __name__ == "__main__":
    unittest.main()
