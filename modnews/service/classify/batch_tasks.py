from __future__ import annotations

from pathlib import Path

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.task import TaskEvent

from .batch_stage import run_llm_batch_task
from .clustered_extract import CLUSTERED_EXTRACTION_STAGE
from .clustered_merge import CLUSTERED_MERGE_STAGE
from .llm_client import LlmClient
from .retriever import EventVectorRetriever


def run_embedding_batch_item(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    config = load_config(task.payload.get("config"), project_root=project_root)
    ctx = PipelineContext.create(config)
    retriever = EventVectorRetriever(config.classification.embedding, ctx.session)
    item_payload = task.payload.get("item_payload") if isinstance(task.payload.get("item_payload"), dict) else {}
    key = item_payload.get("key")
    text = str(item_payload.get("text") or "")
    return {
        "batch_result": {
            "key": key,
            "vector": retriever.embed_text_for_clustering(text),
        }
    }

def run_clustered_event_extraction_batch_item(task: TaskEvent) -> dict[str, object]:
    client = _build_llm_client(task)
    item_payload = task.payload.get("item_payload")
    items = item_payload if isinstance(item_payload, list) else []
    response = run_llm_batch_task(
        client=client,
        stage=CLUSTERED_EXTRACTION_STAGE,
        task=task,
        payload=items,
    )
    return {"batch_result": response}


def run_clustered_event_merge_batch_item(task: TaskEvent) -> dict[str, object]:
    client = _build_llm_client(task)
    item_payload = task.payload.get("item_payload")
    events = item_payload if isinstance(item_payload, list) else []
    response = run_llm_batch_task(
        client=client,
        stage=CLUSTERED_MERGE_STAGE,
        task=task,
        payload=events,
    )
    return {"batch_result": response}


def _build_llm_client(task: TaskEvent) -> LlmClient:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    config = load_config(task.payload.get("config"), project_root=project_root)
    ctx = PipelineContext.create(config)
    return LlmClient(config.classification.llm, ctx.session)
