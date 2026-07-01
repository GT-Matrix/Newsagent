from __future__ import annotations

from dataclasses import dataclass

from .checkpoint import build_checkpoint_meta, write_outputs
from .events import apply_event_decision, decide_event_membership, merge_similar_events, recall_event_candidates
from .relevance import classify_relevance_batches, handle_suspected_items
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
class BatchRelevanceStep:
    name: str = "batch_relevance"
    output_stage: str = "after_batch_relevance"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "started"

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyState:
        classify_relevance_batches(
            runtime.client,
            state.prepared,
            runtime.config.batch_size,
            runtime.config.batch_concurrency,
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
class SuspectHandlingStep:
    name: str = "suspect_handling"
    output_stage: str = "after_suspect_handling"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "after_batch_relevance"

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyState:
        handle_suspected_items(
            runtime.ctx,
            runtime.client,
            state.prepared,
            state.discarded,
            runtime.config.suspect_mode,
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
class EventMembershipStep:
    name: str = "event_membership"
    output_stage: str = "after_event_membership"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage in {"after_suspect_handling", "during_event_membership"}

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyState:
        state.total_candidates = sum(1 for entry in state.prepared if entry.item.classification_decision == "candidate")

        for entry in state.prepared:
            if entry.item.classification_decision != "candidate":
                continue
            if entry.item.event_id:
                state.processed_candidates += 1
                continue

            candidates = recall_event_candidates(entry, state.events, runtime.config, runtime.retriever)
            decision = decide_event_membership(runtime.client, entry, candidates)
            apply_event_decision(runtime.ctx, entry, decision, state.events, state.discarded)
            state.processed_candidates += 1

            if state.processed_candidates % 25 == 0 or state.processed_candidates == state.total_candidates:
                write_outputs(
                    runtime.config,
                    state.items,
                    state.event_records,
                    state.discarded,
                    build_checkpoint_meta(
                        state.items,
                        state.event_records,
                        state.discarded,
                        stage="during_event_membership",
                        processed_candidates=state.processed_candidates,
                        total_candidates=state.total_candidates,
                    ),
                )
        return state


@dataclass(slots=True)
class EventMergeStep:
    name: str = "event_merge"
    output_stage: str = "completed"

    def should_run(self, state: ClassifyState) -> bool:
        return state.stage == "after_event_membership"

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyState:
        state.merged_event_count = merge_similar_events(
            runtime.client,
            state.events,
            runtime.config,
            runtime.retriever,
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

