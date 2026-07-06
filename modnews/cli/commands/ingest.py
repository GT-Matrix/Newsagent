from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from modnews.cli.api_client import ApiClient
from modnews.service.ingest.planner import plan_ingest_tasks


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
    tasks = plan_ingest_tasks(
        project_root=Path(client.project_root),
        step_id=args.step,
        run_id=args.run_id,
    )
    for task in tasks:
        client.container.event_queue.register(task)
    client.container.event_queue.drain_ready()
    task_payloads = [client.queue_show(task.id) for task in tasks]
    return {"ok": all(task.get("state") == "succeeded" for task in task_payloads), "tasks": task_payloads}
