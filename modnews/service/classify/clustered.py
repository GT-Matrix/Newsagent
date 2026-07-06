from __future__ import annotations

import json
from modnews.core.config import ClassificationConfig
from modnews.core.context import PipelineContext

from .clustered_extract import extract_events_from_title_clusters
from .clustered_merge import merge_event_clusters
from .llm_client import LlmClient
from .retriever import EventVectorRetriever
from .types import DiscardedRecord, EventState, PreparedItem


def extract_events_from_title_clusters(
    ctx: PipelineContext,
    client: LlmClient,
    retriever: EventVectorRetriever,
    prepared: list[PreparedItem],
    config: ClassificationConfig,
    discarded: list[DiscardedRecord],
) -> list[EventState]:
    return extract_events_from_title_clusters(ctx, client, retriever, prepared, config, discarded)


def merge_event_clusters(
    client: LlmClient,
    retriever: EventVectorRetriever,
    events: list[EventState],
    config: ClassificationConfig,
) -> int:
    return merge_event_clusters(client, retriever, events, config)
