from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient
from modnews.service.classify.planner import plan_clustered_classify_tasks


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
    tasks = plan_clustered_classify_tasks(
        project_root=client.project_root,
        run_id=args.run_id,
        input_path=args.input,
    )
    for task in tasks:
        client.container.event_queue.register(task)
    client.container.event_queue.drain_ready()
    return {"ok": all(client.queue_show(task.id).get("state") == "succeeded" for task in tasks), "tasks": [client.queue_show(task.id) for task in tasks]}
