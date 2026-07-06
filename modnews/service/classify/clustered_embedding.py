from __future__ import annotations

from dataclasses import dataclass

from modnews.core.progress import emit

from .batch_profile import CLUSTERED_EMBEDDING_BATCH, run_profiled_batch
from .retriever import EventVectorRetriever, cosine_similarity
from .types import EventState, PreparedItem


@dataclass(slots=True)
class VectorRow:
    key: int | str
    vector: list[float]


def cluster_prepared_items(
    prepared: list[PreparedItem],
    retriever: EventVectorRetriever,
    batch_size: int,
    concurrency: int,
) -> list[list[PreparedItem]]:
    emit("clustered_embedding_start", target="titles", item_count=len(prepared), concurrency=max(1, concurrency))
    vectors = embed_rows_parallel(
        [(entry.index, title_text(entry.item)) for entry in prepared],
        retriever,
        concurrency,
    )
    emit("clustered_embedding_done", target="titles", item_count=len(vectors))
    groups = greedy_vector_groups(vectors, batch_size)
    by_index = {entry.index: entry for entry in prepared}
    return [[by_index[int(row.key)] for row in group] for group in groups]


def cluster_events(
    events: list[EventState],
    retriever: EventVectorRetriever,
    batch_size: int,
    concurrency: int,
) -> list[list[EventState]]:
    emit("clustered_embedding_start", target="events", item_count=len(events), concurrency=max(1, concurrency))
    vectors = embed_rows_parallel(
        [(state.record.event_id, event_text(state.record)) for state in events],
        retriever,
        concurrency,
    )
    emit("clustered_embedding_done", target="events", item_count=len(vectors))
    groups = greedy_vector_groups(vectors, batch_size)
    by_id = {state.record.event_id: state for state in events}
    return [[by_id[str(row.key)] for row in group] for group in groups]


def embed_rows_parallel(
    rows: list[tuple[int | str, str]],
    retriever: EventVectorRetriever,
    concurrency: int,
) -> list[VectorRow]:
    workers = max(1, concurrency)
    if workers == 1:
        return [VectorRow(key, retriever.embed_text_for_clustering(text)) for key, text in rows]
    return run_profiled_batch(
        lambda row: VectorRow(row[0], retriever.embed_text_for_clustering(row[1])),
        rows,
        max_workers=workers,
        profile=CLUSTERED_EMBEDDING_BATCH,
    )


def greedy_vector_groups(rows: list[VectorRow], batch_size: int) -> list[list[VectorRow]]:
    pending = rows[:]
    groups: list[list[VectorRow]] = []
    size = max(1, batch_size)
    while pending:
        seed = pending.pop(0)
        scored = [(cosine_similarity(seed.vector, row.vector), row) for row in pending]
        scored.sort(key=lambda row: row[0], reverse=True)
        selected = [seed, *[row for _, row in scored[: size - 1]]]
        selected_keys = {row.key for row in selected}
        pending = [row for row in pending if row.key not in selected_keys]
        groups.append(selected)
    return groups


def title_text(item) -> str:
    return "\n".join(part for part in [item.title, item.platform, item.pubtime] if part)


def event_text(event) -> str:
    return "\n".join(
        part
        for part in [
            event.event_label,
            event.event_summary,
            " ".join(event.key_entities),
            event.event_type,
            "\n".join(event.representative_titles),
        ]
        if part
    )
