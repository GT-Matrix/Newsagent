from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .checkpoint import build_checkpoint_meta, write_outputs
from .clustered_extract import extract_events_from_title_clusters
from .clustered_merge import merge_event_clusters
from .runner import ClassifyRuntime, ClassifyStepResult
from .state import ClassifyState


class ClassifyStepDefinition(Protocol):
    name: str
    output_stage: str

    def should_run(self, state: ClassifyState) -> bool:
        ...

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyStepResult:
        ...


@dataclass(slots=True)
class StartCheckpointStep:
    name: str = "start_checkpoint"
    output_stage: str = "started"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "started"

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyStepResult:
        state.total_candidates = len(state.prepared)
        result = _build_step_result(state, next_stage=self.output_stage)
        if runtime.write_fixed_outputs:
            write_outputs(runtime.config, state.items, state.event_records, state.discarded, result.checkpoint_meta)
        return result


@dataclass(slots=True)
class ClusteredEventExtractionStep:
    name: str = "clustered_event_extraction"
    output_stage: str = "after_clustered_event_extraction"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "started"

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyStepResult:
        state.total_candidates = len(state.prepared)
        state.events = extract_events_from_title_clusters(
            runtime.ctx,
            runtime.client,
            runtime.retriever,
            state.prepared,
            runtime.config,
            state.discarded,
        )
        state.processed_candidates = len(state.prepared)
        result = _build_step_result(state, next_stage=self.output_stage)
        if runtime.write_fixed_outputs:
            write_outputs(runtime.config, state.items, state.event_records, state.discarded, result.checkpoint_meta)
        return result


@dataclass(slots=True)
class ClusteredEventMergeStep:
    name: str = "clustered_event_merge"
    output_stage: str = "completed"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "after_clustered_event_extraction"

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyStepResult:
        state.merged_event_count = merge_event_clusters(
            runtime.client,
            runtime.retriever,
            state.events,
            runtime.config,
        )
        result = _build_step_result(state, next_stage=self.output_stage)
        if runtime.write_fixed_outputs:
            write_outputs(runtime.config, state.items, state.event_records, state.discarded, result.checkpoint_meta)
        return result


def build_full_classify_steps() -> list[ClassifyStepDefinition]:
    return [
        StartCheckpointStep(),
        ClusteredEventExtractionStep(),
        ClusteredEventMergeStep(),
    ]


def build_extraction_task_steps() -> list[ClassifyStepDefinition]:
    return [
        StartCheckpointStep(),
        ClusteredEventExtractionStep(),
    ]


def build_merge_task_steps() -> list[ClassifyStepDefinition]:
    return [ClusteredEventMergeStep()]


def _build_step_result(state: ClassifyState, *, next_stage: str) -> ClassifyStepResult:
    return ClassifyStepResult(
        state=state,
        next_stage=next_stage,
        checkpoint_meta=build_checkpoint_meta(
            state.items,
            state.event_records,
            state.discarded,
            stage=next_stage,
            processed_candidates=state.processed_candidates,
            total_candidates=state.total_candidates,
            merged_event_count=state.merged_event_count,
        ),
        stats={
            "item_count": len(state.items),
            "event_count": len(state.events),
            "discarded_count": len(state.discarded),
            "processed_candidates": state.processed_candidates,
            "total_candidates": state.total_candidates,
            "merged_event_count": state.merged_event_count,
        },
    )
