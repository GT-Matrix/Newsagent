from __future__ import annotations

import json

from modnews.core.context import PipelineContext
from modnews.core.progress import emit

from .article import fetch_article_excerpt
from .batch_executor import run_batch_parallel
from .llm_client import LlmClient
from .prompts import batch_relevance_system_prompt, suspect_review_system_prompt
from .types import DiscardedRecord, PreparedItem
from .utils import clean_event_type, clean_list, clean_string, discard, int_or_none


def classify_relevance_batches(
    client: LlmClient,
    prepared: list[PreparedItem],
    batch_size: int,
    batch_concurrency: int,
    discarded: list[DiscardedRecord],
) -> None:
    batches = [prepared[start : start + batch_size] for start in range(0, len(prepared), batch_size)]
    max_workers = max(1, batch_concurrency)
    emit("batch_relevance_start", batch_count=len(batches), batch_size=batch_size, concurrency=max_workers)
    responses = run_batch_parallel(
        lambda args: _classify_relevance_batch(client, *args),
        [(batch, batch_index, len(batches)) for batch_index, batch in enumerate(batches, start=1)],
        max_workers=max_workers,
    )
    for batch_index in range(1, len(batches) + 1):
        emit("batch_relevance_done", batch_index=batch_index, batch_count=len(batches))

    for response in responses:
        for row in response.get("items", []):
            index = int(row.get("index", -1))
            if index < 0 or index >= len(prepared):
                continue
            item = prepared[index].item
            status = str(row.get("status", "discard")).lower()
            item.is_ai_relevant = status == "candidate"
            item.relevance_score = int_or_none(row.get("relevance_score"))
            item.canonical_summary = clean_string(row.get("canonical_summary"))
            item.entities = clean_list(row.get("entities"))
            item.event_type = clean_event_type(row.get("event_type"))
            item.classification_reason = clean_string(row.get("reason"))
            if status == "candidate":
                item.classification_decision = "candidate"
            elif status == "suspect":
                item.classification_decision = "suspect"
                item.is_ai_relevant = None
            else:
                item.classification_decision = "discard"
                discarded.append(discard(index, item, "batch_relevance", item.classification_reason or "not AI relevant"))


def handle_suspected_items(
    ctx: PipelineContext,
    client: LlmClient,
    prepared: list[PreparedItem],
    discarded: list[DiscardedRecord],
    suspect_mode: str,
) -> None:
    for entry in prepared:
        item = entry.item
        if item.classification_decision != "suspect":
            continue
        if suspect_mode != "article":
            item.classification_decision = "discard"
            item.is_ai_relevant = False
            item.classification_reason = item.classification_reason or "suspect discarded by configuration"
            discarded.append(discard(entry.index, item, "suspect_discard", item.classification_reason))
            continue
        try:
            excerpt = fetch_article_excerpt(ctx, item.url)
        except Exception as exc:
            item.classification_decision = "discard"
            item.classification_reason = f"article fetch failed: {exc}"
            discarded.append(discard(entry.index, item, "suspect_article_fetch", item.classification_reason))
            continue

        response = client.complete_json(
            task="suspect_article_review",
            messages=[
                {"role": "system", "content": suspect_review_system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "index": entry.index,
                            "title": item.title,
                            "platform": item.platform,
                            "url": item.url,
                            "excerpt": excerpt,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        decision = str(response.get("decision", "discard")).lower()
        item.relevance_score = int_or_none(response.get("relevance_score"))
        item.canonical_summary = clean_string(response.get("canonical_summary")) or item.canonical_summary
        item.entities = clean_list(response.get("entities")) or item.entities
        item.event_type = clean_event_type(response.get("event_type") or item.event_type)
        item.classification_reason = clean_string(response.get("reason"))
        if decision == "candidate":
            item.classification_decision = "candidate"
            item.is_ai_relevant = True
        else:
            item.classification_decision = "discard"
            item.is_ai_relevant = False
            discarded.append(discard(entry.index, item, "suspect_article_review", item.classification_reason or "discarded"))


def _classify_relevance_batch(
    client: LlmClient,
    batch: list[PreparedItem],
    batch_index: int,
    batch_count: int,
) -> dict:
    payload = [
        {
            "index": entry.index,
            "title": entry.item.title,
            "platform": entry.item.platform,
            "pubtime": entry.item.pubtime,
            "url_domain": entry.domain,
        }
        for entry in batch
    ]
    emit(
        "batch_relevance_request",
        batch_index=batch_index,
        batch_count=batch_count,
        items=payload,
    )
    return client.complete_json(
        task="batch_ai_relevance",
        messages=[
            {"role": "system", "content": batch_relevance_system_prompt()},
            {"role": "user", "content": json.dumps({"items": payload}, ensure_ascii=False)},
        ],
    )
