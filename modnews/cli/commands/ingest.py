from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from modnews.cli.api_client import ApiClient
from modnews.core.task import TaskEvent


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ingest", help="Run individual ingest steps through the task queue.")
    nested = parser.add_subparsers(dest="ingest_command", required=True)
    run = nested.add_parser("run")
    run.add_argument("step", choices=["rss", "newsnow", "site_lists"])
    run.add_argument("--run-id")
    run.set_defaults(handler=run_ingest)


def run_ingest(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"step_id": args.step, "run_id": args.run_id}
    if isinstance(client, ApiClient):
        return client.post("/api/ingest/run", payload)
    task_id = f"ingest-{args.step}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    task = TaskEvent(
        id=task_id,
        type="ingest.run_step",
        pipeline_run_id=args.run_id,
        step_id=f"ingest/{args.step}",
        payload={"project_root": str(client.project_root), **payload},
        concurrency_key=f"ingest:{args.step}",
        max_concurrency=1,
    )
    client.container.event_queue.dispatch(task)
    return client.queue_show(task_id)
