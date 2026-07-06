from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from modnews.core.task import TaskEvent
from modnews.service.classify.batch_stage import LlmBatchStage, run_llm_batch_stage, run_llm_batch_task, task_batch_progress
from modnews.service.classify.batch_profile import CLUSTERED_EVENT_EXTRACTION_BATCH
from modnews.service.classify.batch_task_registry import (
    REGISTERED_BATCH_TASK_BY_TYPE,
    REGISTERED_BATCH_TASKS,
    REGISTERED_LLM_BATCH_STAGE_BY_TASK_TYPE,
    run_registered_llm_batch_item,
)
from modnews.service.classify.task_registry import REGISTERED_CLASSIFY_TASK_BY_TYPE


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
            type="classify.clustered_event_extraction.batch",
            payload={"batch": {"batch_index": 2, "batch_count": 5}},
        )

        self.assertEqual(task_batch_progress(task), (2, 5))

    def test_run_llm_batch_task_emits_stage_events_for_queue_task(self) -> None:
        client = _FakeClient()
        stage = LlmBatchStage[list[dict[str, object]]](
            profile=CLUSTERED_EVENT_EXTRACTION_BATCH,
            llm_task="clustered_event_extraction",
            request_event="clustered_extraction_request",
            done_event="clustered_extraction_batch_done",
            system_prompt="system",
            payload_key="items",
            request_event_key="items",
            build_payload=lambda batch: batch,
        )
        task = TaskEvent(
            id="task-1",
            type="classify.clustered_event_extraction.batch",
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
            "clustered_extraction_request",
            batch_index=2,
            batch_count=5,
            items=[{"index": 0, "title": "hello"}],
        )
        emit.assert_any_call("clustered_extraction_batch_done", batch_index=2, batch_count=5)
        self.assertEqual(client.calls[0]["task"], "clustered_event_extraction")

    def test_run_llm_batch_stage_uses_stage_payload_builder(self) -> None:
        client = _FakeClient()
        stage = LlmBatchStage[list[int]](
            profile=CLUSTERED_EVENT_EXTRACTION_BATCH,
            llm_task="clustered_event_extraction",
            request_event="clustered_extraction_request",
            done_event="clustered_extraction_batch_done",
            system_prompt="system",
            payload_key="items",
            request_event_key="items",
            build_payload=lambda batch: [{"value": item} for item in batch],
        )

        with patch("modnews.service.classify.batch_stage.emit") as emit:
            result = run_llm_batch_stage(
                client=client,
                stage=stage,
                batches=[[1, 2]],
                max_workers=1,
            )

        self.assertEqual(result, [{"items": [{"index": 0, "status": "candidate"}]}])
        emit.assert_any_call(
            "clustered_extraction_request",
            batch_index=1,
            batch_count=1,
            items=[{"value": 1}, {"value": 2}],
        )
        payload = json.loads(client.calls[0]["messages"][1]["content"])  # type: ignore[index]
        self.assertEqual(payload, {"items": [{"value": 1}, {"value": 2}]})

    def test_registered_llm_batch_task_reuses_stage_helper(self) -> None:
        task = TaskEvent(
            id="task-1",
            type="classify.clustered_event_extraction.batch",
            payload={
                "batch": {"batch_index": 3, "batch_count": 4},
                "item_payload": [{"index": 0, "title": "hello"}],
            },
        )

        with patch("modnews.service.classify.batch_task_registry.build_classify_llm_client_for_context", return_value=_FakeClient()):
            with patch("modnews.service.classify.batch_task_registry.run_llm_batch_task") as helper:
                helper.return_value = {"items": [{"index": 0, "status": "candidate"}]}
                result = run_registered_llm_batch_item(task)

        self.assertEqual(result, {"batch_result": {"items": [{"index": 0, "status": "candidate"}]}})
        helper.assert_called_once()
        self.assertEqual(helper.call_args.kwargs["stage"].request_event, "clustered_extraction_request")
        self.assertEqual(helper.call_args.kwargs["task"].id, "task-1")

    def test_batch_task_registry_exposes_registered_task_types(self) -> None:
        self.assertEqual(
            sorted(spec.task_type for spec in REGISTERED_BATCH_TASKS),
            [
                "classify.clustered_event_extraction.batch",
                "classify.clustered_event_merge.batch",
                "classify.embedding",
            ],
        )

    def test_batch_task_registry_unifies_executor_and_profile_metadata(self) -> None:
        spec = REGISTERED_BATCH_TASK_BY_TYPE["classify.clustered_event_extraction.batch"]

        self.assertEqual(spec.profile.task_type, spec.task_type)
        self.assertEqual(spec.profile.queue_task_type, spec.task_type)
        self.assertIs(spec.executor, run_registered_llm_batch_item)
        self.assertIsNotNone(spec.llm_stage)
        self.assertEqual(spec.llm_stage.task_type, spec.task_type)

    def test_llm_batch_stage_registry_is_keyed_by_queue_task_type(self) -> None:
        self.assertEqual(
            sorted(REGISTERED_LLM_BATCH_STAGE_BY_TASK_TYPE),
            [
                "classify.clustered_event_extraction.batch",
                "classify.clustered_event_merge.batch",
            ],
        )

    def test_classify_task_registry_is_keyed_by_outer_task_type(self) -> None:
        self.assertEqual(
            sorted(REGISTERED_CLASSIFY_TASK_BY_TYPE),
            [
                "classify.clustered_event_extraction",
                "classify.clustered_event_merge",
            ],
        )
        extraction = REGISTERED_CLASSIFY_TASK_BY_TYPE["classify.clustered_event_extraction"]
        merge = REGISTERED_CLASSIFY_TASK_BY_TYPE["classify.clustered_event_merge"]
        self.assertEqual(extraction.step_names, ("start_checkpoint", "clustered_event_extraction"))
        self.assertEqual(merge.step_names, ("clustered_event_merge",))
        self.assertEqual(extraction.default_input_path, "__combined_ingest__")
        self.assertEqual(merge.default_input_path, "__combined_ingest__")
        self.assertEqual(extraction.concurrency_key, "classify")
        self.assertEqual(merge.max_concurrency, 1)
        self.assertEqual([step.name for step in extraction.build_steps()], list(extraction.step_names))
        self.assertEqual([step.name for step in merge.build_steps()], list(merge.step_names))


if __name__ == "__main__":
    unittest.main()
