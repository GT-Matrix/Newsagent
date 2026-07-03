from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from modnews.cli.api_client import ApiClient
from modnews.core.task import TaskEvent


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("classify", help="Run classification through the task queue.")
    nested = parser.add_subparsers(dest="classify_command", required=True)
    run = nested.add_parser("run")
    run.add_argument("--input")
    run.add_argument("--run-id")
    run.add_argument("--disable-classification", action="store_true")
    run.set_defaults(handler=run_classify)


def run_classify(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {
        "input_path": args.input,
        "run_id": args.run_id,
        "disable_classification": args.disable_classification,
    }
    if isinstance(client, ApiClient):
        return client.post("/api/classify/run", payload)
    task_id = f"classify-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    task = TaskEvent(
        id=task_id,
        type="classify.clustered_pipeline",
        pipeline_run_id=args.run_id,
        step_id="classify/clustered_pipeline",
        payload={"project_root": str(client.project_root), **payload},
        concurrency_key="classify",
        max_concurrency=1,
    )
    client.container.event_queue.submit(task)
    return client.queue_show(task_id)
