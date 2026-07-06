from __future__ import annotations

import unittest
from unittest.mock import patch

from modnews.core.task import TaskEvent
from modnews.service.classify.batch_stage import LlmBatchStage, run_llm_batch_task, task_batch_progress
from modnews.service.classify.batch_profile import RELEVANCE_BATCH
from modnews.service.classify.batch_tasks import run_relevance_batch_item


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def complete_json(self, *, task: str, messages: list[dict[str, str]]) -> dict[str, object]:
        self.calls.append({"task": task, "messages": messages})
        return {"items": [{"index": 0, "status": "candidate"}]}


class ClassifyBatchTaskTest(unittest.TestCase):
    def test_task_batch_progress_supports_dict_batch_metadata(self) -> None:
        task = TaskEvent(
            id="task-1",
            type="classify.batch_relevance",
            payload={"batch": {"batch_index": 2, "batch_count": 5}},
        )

        self.assertEqual(task_batch_progress(task), (2, 5))

    def test_run_llm_batch_task_emits_stage_events_for_queue_task(self) -> None:
        client = _FakeClient()
        stage = LlmBatchStage[list[dict[str, object]]](
            profile=RELEVANCE_BATCH,
            llm_task="batch_ai_relevance",
            request_event="batch_relevance_request",
            done_event="batch_relevance_batch_done",
            system_prompt="system",
            payload_key="items",
        )
        task = TaskEvent(
            id="task-1",
            type="classify.batch_relevance",
            payload={
                "batch": {"batch_index": 2, "batch_count": 5},
                "item_payload": [{"index": 0, "title": "hello"}],
            },
        )

        with patch("modnews.service.classify.batch_stage.emit") as emit:
            response = run_llm_batch_task(
                client=client,
                stage=stage,
                task=task,
                payload=[{"index": 0, "title": "hello"}],
            )

        self.assertEqual(response, {"items": [{"index": 0, "status": "candidate"}]})
        emit.assert_any_call(
            "batch_relevance_request",
            batch_index=2,
            batch_count=5,
            items=[{"index": 0, "title": "hello"}],
        )
        emit.assert_any_call("batch_relevance_batch_done", batch_index=2, batch_count=5)
        self.assertEqual(client.calls[0]["task"], "batch_ai_relevance")

    def test_relevance_batch_task_reuses_stage_helper(self) -> None:
        task = TaskEvent(
            id="task-1",
            type="classify.batch_relevance",
            payload={
                "batch": {"batch_index": 3, "batch_count": 4},
                "item_payload": [{"index": 0, "title": "hello"}],
            },
        )

        with patch("modnews.service.classify.batch_tasks._build_llm_client", return_value=_FakeClient()):
            with patch("modnews.service.classify.batch_tasks.run_llm_batch_task") as helper:
                helper.return_value = {"items": [{"index": 0, "status": "candidate"}]}
                result = run_relevance_batch_item(task)

        self.assertEqual(result, {"batch_result": {"items": [{"index": 0, "status": "candidate"}]}})
        helper.assert_called_once()
        self.assertEqual(helper.call_args.kwargs["stage"].request_event, "batch_relevance_request")
        self.assertEqual(helper.call_args.kwargs["task"].id, "task-1")


if __name__ == "__main__":
    unittest.main()
