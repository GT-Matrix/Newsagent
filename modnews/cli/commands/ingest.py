from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from modnews.cli.api_client import ApiClient
from modnews.service.ingest.registry import default_ingest_registry


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ingest", help="Run individual ingest steps through the task queue.")
    nested = parser.add_subparsers(dest="ingest_command", required=True)
    run = nested.add_parser("run")
    run.add_argument("step", choices=default_ingest_registry().list())
    run.add_argument("--run-id")
    run.add_argument("--site", action="append", dest="sites")
    run.add_argument("--limit-per-site", type=int)
    run.add_argument("--max-concurrency", type=int)
    run.set_defaults(handler=run_ingest)


def run_ingest(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    step_cls = default_ingest_registry().get(args.step)
    options = step_cls.options_from_cli_args(args)
    payload = {"step_id": args.step, "run_id": args.run_id}
    payload.update(options)
    if isinstance(client, ApiClient):
        return client.post("/api/ingest/run", payload)
    from modnews.service.ingest.entrypoints import run_ingest_step_tasks

    return run_ingest_step_tasks(
        project_root=Path(client.project_root),
        queue=client.container.event_queue,
        queue_show=client.queue_show,
        step_id=args.step,
        run_id=args.run_id,
        options=options,
    )
