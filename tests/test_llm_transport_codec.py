from __future__ import annotations

import json
import unittest

from modnews.service.classify.llm_transport_codec import (
    build_chat_completion_body,
    decode_stream_response_lines,
    extract_message_content,
)


class LlmTransportCodecTest(unittest.TestCase):
    def test_build_chat_completion_body_toggles_stream_flag(self) -> None:
        stream_body = build_chat_completion_body(
            model="model",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.2,
            stream=True,
        )
        non_stream_body = build_chat_completion_body(
            model="model",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.2,
            stream=False,
        )

        self.assertTrue(stream_body["stream"])
        self.assertNotIn("stream", non_stream_body)

    def test_decode_stream_response_lines_supports_stream_and_non_stream_payloads(self) -> None:
        stream_lines = [
            'data: {"choices":[{"delta":{"content":"he"}}]}',
            'data: {"choices":[{"delta":{"content":"llo"}}]}',
            "data: [DONE]",
        ]
        non_stream = json.dumps({"choices": [{"message": {"content": '{"ok":true}'}}]})

        self.assertEqual(decode_stream_response_lines(stream_lines), (True, "hello"))
        self.assertEqual(decode_stream_response_lines([non_stream]), (False, non_stream))

    def test_extract_message_content_validates_choices(self) -> None:
        payload = {"choices": [{"message": {"content": '{"ok":true}'}}]}
        self.assertEqual(extract_message_content(payload), '{"ok":true}')
        with self.assertRaisesRegex(ValueError, "empty choices"):
            extract_message_content({"choices": []})


if __name__ == "__main__":
    unittest.main()
