from __future__ import annotations

import json
from pathlib import Path

from modnews.core.config import load_config
from modnews.core.context import PipelineContext
from modnews.core.task import TaskEvent

from .llm_client import LlmClient
from .prompts import batch_relevance_system_prompt
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


def run_relevance_batch_item(task: TaskEvent) -> dict[str, object]:
    project_root = Path(str(task.payload.get("project_root") or Path.cwd())).resolve()
    config = load_config(task.payload.get("config"), project_root=project_root)
    ctx = PipelineContext.create(config)
    client = LlmClient(config.classification.llm, ctx.session)
    item_payload = task.payload.get("item_payload")
    items = item_payload if isinstance(item_payload, list) else []
    response = client.complete_json(
        task="batch_ai_relevance",
        messages=[
            {"role": "system", "content": batch_relevance_system_prompt()},
            {"role": "user", "content": json.dumps({"items": items}, ensure_ascii=False)},
        ],
    )
    return {"batch_result": response}
