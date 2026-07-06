from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ingest", help="Run individual ingest steps through the task queue.")
    nested = parser.add_subparsers(dest="ingest_command", required=True)
    run = nested.add_parser("run")
    run.add_argument("step", choices=["rss", "newsnow", "site_lists"])
    run.add_argument("--run-id")
    run.add_argument("--site", action="append", dest="sites")
    run.add_argument("--limit-per-site", type=int)
    run.add_argument("--max-concurrency", type=int)
    run.set_defaults(handler=run_ingest)


def run_ingest(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"step_id": args.step, "run_id": args.run_id}
    sites = getattr(args, "sites", None)
    limit_per_site = getattr(args, "limit_per_site", None)
    max_concurrency = getattr(args, "max_concurrency", None)
    if args.step == "site_lists":
        if sites:
            payload["sites"] = sites
        if limit_per_site is not None:
            payload["limit_per_site"] = limit_per_site
        if max_concurrency is not None:
            payload["max_concurrency"] = max_concurrency
    if isinstance(client, ApiClient):
        return client.post("/api/ingest/run", payload)
    options = None
    if args.step == "site_lists":
        options = {}
        if sites:
            options["sites"] = sites
        if limit_per_site is not None:
            options["limit_per_site"] = limit_per_site
        if max_concurrency is not None:
            options["max_concurrency"] = max_concurrency
    from modnews.service.ingest.entrypoints import run_ingest_step_tasks

    return run_ingest_step_tasks(
        project_root=Path(client.project_root),
        queue=client.container.event_queue,
        queue_show=client.queue_show,
        step_id=args.step,
        run_id=args.run_id,
        options=options,
    )
