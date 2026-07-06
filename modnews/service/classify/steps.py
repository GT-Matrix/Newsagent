from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .checkpoint import build_checkpoint_meta, write_outputs
from .clustered_extract import extract_events_from_title_clusters
from .clustered_merge import merge_event_clusters
from .runner import ClassifyRuntime, ClassifyStep, ClassifyStepResult
from .state import ClassifyState


@dataclass(frozen=True, slots=True)
class ClassifyStepSpec:
    name: str
    output_stage: str
    should_run: Callable[[ClassifyState], bool]
    apply: Callable[[ClassifyState, ClassifyRuntime], None]


@dataclass(slots=True)
class DeclaredClassifyStep:
    spec: ClassifyStepSpec

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def output_stage(self) -> str:
        return self.spec.output_stage

    def should_run(self, state: ClassifyState) -> bool:
        return self.spec.should_run(state)

    def run(self, state: ClassifyState, runtime: ClassifyRuntime) -> ClassifyStepResult:
        self.spec.apply(state, runtime)
        return _complete_step_result(state, runtime, next_stage=self.spec.output_stage)


class StartCheckpointStep(DeclaredClassifyStep):
    def __init__(self) -> None:
        self.spec = get_registered_classify_step_spec("start_checkpoint")


class ClusteredEventExtractionStep(DeclaredClassifyStep):
    def __init__(self) -> None:
        self.spec = get_registered_classify_step_spec("clustered_event_extraction")


class ClusteredEventMergeStep(DeclaredClassifyStep):
    def __init__(self) -> None:
        self.spec = get_registered_classify_step_spec("clustered_event_merge")


@dataclass(frozen=True, slots=True)
class RegisteredClassifyFlow:
    name: str
    step_names: tuple[str, ...]

    def build_steps(self) -> list[ClassifyStep]:
        return build_registered_classify_steps(*self.step_names)


def build_full_classify_steps() -> list[ClassifyStep]:
    return get_registered_classify_flow("full").build_steps()


def build_extraction_task_steps() -> list[ClassifyStep]:
    return get_registered_classify_flow("clustered_event_extraction_task").build_steps()


def build_merge_task_steps() -> list[ClassifyStep]:
    return get_registered_classify_flow("clustered_event_merge_task").build_steps()


def build_registered_classify_steps(*step_names: str) -> list[ClassifyStep]:
    return [DeclaredClassifyStep(get_registered_classify_step_spec(step_name)) for step_name in step_names]


def _apply_start_checkpoint(state: ClassifyState, runtime: ClassifyRuntime) -> None:
    del runtime
    state.total_candidates = len(state.prepared)


def _apply_clustered_event_extraction(state: ClassifyState, runtime: ClassifyRuntime) -> None:
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


def _apply_clustered_event_merge(state: ClassifyState, runtime: ClassifyRuntime) -> None:
    state.merged_event_count = merge_event_clusters(
        runtime.client,
        runtime.retriever,
        state.events,
        runtime.config,
    )


def _complete_step_result(state: ClassifyState, runtime: ClassifyRuntime, *, next_stage: str) -> ClassifyStepResult:
    result = ClassifyStepResult(
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
    if runtime.write_fixed_outputs:
        write_outputs(runtime.config, state.items, state.event_records, state.discarded, result.checkpoint_meta)
    return result


REGISTERED_CLASSIFY_STEP_SPECS: tuple[ClassifyStepSpec, ...] = (
    ClassifyStepSpec(
        name="start_checkpoint",
        output_stage="started",
        should_run=lambda state: state.stage == "started",
        apply=_apply_start_checkpoint,
    ),
    ClassifyStepSpec(
        name="clustered_event_extraction",
        output_stage="after_clustered_event_extraction",
        should_run=lambda state: state.stage == "started",
        apply=_apply_clustered_event_extraction,
    ),
    ClassifyStepSpec(
        name="clustered_event_merge",
        output_stage="completed",
        should_run=lambda state: state.stage == "after_clustered_event_extraction",
        apply=_apply_clustered_event_merge,
    ),
)

REGISTERED_CLASSIFY_STEP_SPEC_BY_NAME: dict[str, ClassifyStepSpec] = {
    spec.name: spec
    for spec in REGISTERED_CLASSIFY_STEP_SPECS
}


REGISTERED_CLASSIFY_FLOWS: tuple[RegisteredClassifyFlow, ...] = (
    RegisteredClassifyFlow(
        name="full",
        step_names=(
            "start_checkpoint",
            "clustered_event_extraction",
            "clustered_event_merge",
        ),
    ),
    RegisteredClassifyFlow(
        name="clustered_event_extraction_task",
        step_names=(
            "start_checkpoint",
            "clustered_event_extraction",
        ),
    ),
    RegisteredClassifyFlow(
        name="clustered_event_merge_task",
        step_names=("clustered_event_merge",),
    ),
)

REGISTERED_CLASSIFY_FLOW_BY_NAME: dict[str, RegisteredClassifyFlow] = {
    flow.name: flow
    for flow in REGISTERED_CLASSIFY_FLOWS
}


def get_registered_classify_step_spec(step_name: str) -> ClassifyStepSpec:
    return REGISTERED_CLASSIFY_STEP_SPEC_BY_NAME[step_name]


def get_registered_classify_flow(flow_name: str) -> RegisteredClassifyFlow:
    return REGISTERED_CLASSIFY_FLOW_BY_NAME[flow_name]
