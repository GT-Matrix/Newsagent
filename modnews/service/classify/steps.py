from __future__ import annotations

from dataclasses import dataclass

from .checkpoint import build_checkpoint_meta, write_outputs
from .clustered import extract_events_from_title_clusters, merge_event_clusters
from .runner import ClassifyRuntime
from .state import ClassifyState


@dataclass(slots=True)
class StartCheckpointStep:
    name: str = "start_checkpoint"
    output_stage: str = "started"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "started"

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyState:
        write_outputs(runtime.config, state.items, state.event_records, state.discarded, {"stage": "started"})
        return state


@dataclass(slots=True)
class ClusteredEventExtractionStep:
    name: str = "clustered_event_extraction"
    output_stage: str = "after_clustered_event_extraction"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "started"

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyState:
        state.events = extract_events_from_title_clusters(
            runtime.ctx,
            runtime.client,
            runtime.retriever,
            state.prepared,
            runtime.config,
            state.discarded,
        )
        write_outputs(
            runtime.config,
            state.items,
            state.event_records,
            state.discarded,
            build_checkpoint_meta(
                state.items,
                state.event_records,
                state.discarded,
                stage=self.output_stage,
            ),
        )
        return state


@dataclass(slots=True)
class ClusteredEventMergeStep:
    name: str = "clustered_event_merge"
    output_stage: str = "completed"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "after_clustered_event_extraction"

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyState:
        state.merged_event_count = merge_event_clusters(
            runtime.client,
            runtime.retriever,
            state.events,
            runtime.config,
        )
        write_outputs(
            runtime.config,
            state.items,
            state.event_records,
            state.discarded,
            build_checkpoint_meta(
                state.items,
                state.event_records,
                state.discarded,
                stage=self.output_stage,
                merged_event_count=state.merged_event_count,
            ),
        )
        return state
