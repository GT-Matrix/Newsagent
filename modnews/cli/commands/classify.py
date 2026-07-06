from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient
from modnews.service.classify.entrypoints import run_classify_tasks


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("classify", help="Run classification through the task queue.")
    nested = parser.add_subparsers(dest="classify_command", required=True)
    run = nested.add_parser("run")
    run.add_argument("--input")
    run.add_argument("--run-id")
    run.set_defaults(handler=run_classify)


def run_classify(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {
        "input_path": args.input,
        "run_id": args.run_id,
    }
    if isinstance(client, ApiClient):
        return client.post("/api/classify/run", payload)
    return run_classify_tasks(
        project_root=client.project_root,
        queue=client.container.event_queue,
        queue_show=client.queue_show,
        run_id=payload["run_id"],
        input_path=payload["input_path"],
        pipeline_descriptors=client.container.pipeline_manager.describe_steps(),
    )
