from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("jobs", help="Inspect web extraction jobs.")
    nested = parser.add_subparsers(dest="jobs_command", required=True)
    nested.add_parser("list").set_defaults(handler=list_jobs)
    show = nested.add_parser("show")
    show.add_argument("job_id")
    show.set_defaults(handler=show_job)
    events = nested.add_parser("events")
    events.add_argument("job_id")
    events.set_defaults(handler=job_events)


def list_jobs(_ctx: Any, client: Any, _args: argparse.Namespace) -> Any:
    return client.get("/api/web-jobs").get("items", []) if isinstance(client, ApiClient) else client.web_jobs()


def show_job(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    return client.get(f"/api/web-jobs/{args.job_id}") if isinstance(client, ApiClient) else client.web_job(args.job_id, include_events=True)


def job_events(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    return client.get(f"/api/web-jobs/{args.job_id}/events").get("items", []) if isinstance(client, ApiClient) else client.web_job_events(args.job_id)
