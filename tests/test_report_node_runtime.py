from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from modnews.bootstrap import configure_services
from modnews.core.task import TaskBlocked, TaskEvent
from modnews.repository.runs import RunRepository


def _write_report_input(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "platform": "openai",
                        "title": "OpenAI releases new coding model",
                        "url": "https://openai.com/index/new-coding-model",
                        "pubtime": "2026-07-06T08:00:00+00:00",
                        "scrape_date": "2026-07-07",
                        "event_id": "evt_1",
                        "classification_decision": "assign",
                        "classification_reason": "clustered title extraction",
                    }
                ],
                "events": [
                    {
                        "event_id": "evt_1",
                        "event_label": "OpenAI releases new coding model",
                        "member_count": 1,
                        "platforms": ["openai"],
                        "latest_pubtime": "2026-07-06T08:00:00+00:00",
                        "representative_titles": ["OpenAI releases new coding model"],
                        "confidence": 0.96,
                        "event_summary": "OpenAI released a new coding model for developers.",
                        "event_type": "model_release",
                        "key_entities": ["OpenAI"],
                        "source_news_ids": [0],
                        "last_llm_updated_at": "2026-07-07T00:00:00+08:00",
                    }
                ],
                "discarded": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class ReportNodeRuntimeTest(unittest.TestCase):
    def test_report_node_advances_by_child_task_callbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "LLM_BASE_URL": "https://example.com/v1",
                "LLM_API_KEY": "test-key",
                "LLM_MODEL": "test-model",
            },
            clear=False,
        ):
            project_root = Path(tmp)
            input_path = project_root / "classification_progress.json"
            _write_report_input(input_path)
            config_path = project_root / "report-config.json"
            config_path.write_text("{}", encoding="utf-8")
            output_dir = project_root / "data" / "report"

            container = configure_services(project_root)
            RunRepository(project_root).create("run-1", {})

            container.event_queue.register_executor(
                "report.polish_event",
                lambda task: {
                    "event_id": task.payload["event"]["event_id"],
                    "polish": {
                        "title": "OpenAI 发布新编程模型",
                        "brief": "OpenAI 面向开发者发布新的编程模型，并强化代码生成与修复能力。",
                        "why_important": "这会直接影响 AI 编程产品的模型选择与集成节奏。",
                    },
                },
            )
            container.event_queue.register_executor(
                "report.trend_summary",
                lambda _task: {"trend_summary": "AI 编程模型继续向更强的开发工作流集成演进。"},
            )

            task = TaskEvent(
                id="report-run-1-generate",
                type="report.generate",
                pipeline_run_id="run-1",
                step_id="report/generate",
                payload={
                    "project_root": str(project_root),
                    "run_id": "run-1",
                    "input_path": str(input_path),
                    "output_dir": str(output_dir),
                    "config": str(config_path),
                    "date": "2026-07-07",
                },
            )

            container.event_queue.submit(task)

            parent = container.event_queue.get(task.id)
            self.assertEqual(parent.state, "succeeded")
            result = container.event_queue.result(task.id)
            self.assertEqual(result["node_stage"], "completed")

            checkpoint_path = Path(str(result["checkpoint_path"]))
            checkpoint_payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint_payload["step_id"], "report/generate")

            events_payload = json.loads((output_dir / "enriched_events.json").read_text(encoding="utf-8"))
            self.assertEqual(events_payload[0]["title"], "OpenAI 发布新编程模型")

            trend_payload = json.loads((output_dir / "trend_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(trend_payload["mode"], "llm")
            self.assertIn("AI 编程模型", trend_payload["trend_summary"])

    def test_report_node_skips_blocked_polish_child_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            os.environ,
            {
                "LLM_BASE_URL": "https://example.com/v1",
                "LLM_API_KEY": "test-key",
                "LLM_MODEL": "test-model",
            },
            clear=False,
        ):
            project_root = Path(tmp)
            input_path = project_root / "classification_progress.json"
            _write_report_input(input_path)
            config_path = project_root / "report-config.json"
            config_path.write_text("{}", encoding="utf-8")
            output_dir = project_root / "data" / "report"

            container = configure_services(project_root)
            RunRepository(project_root).create("run-2", {})

            def blocked_polish(_task: TaskEvent) -> dict[str, object]:
                raise TaskBlocked("llm blocked", details={"kind": "llm_rate_limit"})

            container.event_queue.register_executor("report.polish_event", blocked_polish)
            container.event_queue.register_executor(
                "report.trend_summary",
                lambda _task: {"trend_summary": "趋势总结仍可基于原始草稿继续生成。"},
            )

            task = TaskEvent(
                id="report-run-2-generate",
                type="report.generate",
                pipeline_run_id="run-2",
                step_id="report/generate",
                payload={
                    "project_root": str(project_root),
                    "run_id": "run-2",
                    "input_path": str(input_path),
                    "output_dir": str(output_dir),
                    "config": str(config_path),
                    "date": "2026-07-07",
                },
            )

            container.event_queue.submit(task)

            parent = container.event_queue.get(task.id)
            self.assertEqual(parent.state, "succeeded")
            result = container.event_queue.result(task.id)
            self.assertEqual(result["node_stage"], "completed")

            events_payload = json.loads((output_dir / "enriched_events.json").read_text(encoding="utf-8"))
            self.assertNotEqual(events_payload[0]["title"], "OpenAI 发布新编程模型")
            self.assertTrue(any("report_polish_blocked:" in warning for warning in events_payload[0]["warnings"]))

            trend_payload = json.loads((output_dir / "trend_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(trend_payload["mode"], "llm")
            self.assertIn("趋势总结", trend_payload["trend_summary"])


if __name__ == "__main__":
    unittest.main()
