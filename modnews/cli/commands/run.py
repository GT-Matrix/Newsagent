from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("run", help="Start and inspect pipeline runs.")
    nested = parser.add_subparsers(dest="run_command", required=True)
    start = nested.add_parser("start")
    start.add_argument("--only", action="append", default=[])
    start.add_argument("--disable-classify", action="store_true")
    start.add_argument("--foreground", action="store_true")
    start.set_defaults(handler=start_run)
    nested.add_parser("list").set_defaults(handler=list_runs)
    status = nested.add_parser("status")
    status.add_argument("run_id", nargs="?")
    status.set_defaults(handler=status_run)
    resume = nested.add_parser("resume")
    resume.add_argument("run_id")
    resume.set_defaults(handler=resume_run)
    cancel = nested.add_parser("cancel")
    cancel.add_argument("run_id")
    cancel.add_argument("--reason", default="cancelled by user")
    cancel.set_defaults(handler=cancel_run)


def start_run(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {
        "only": args.only or None,
        "disable_classification": args.disable_classify,
        "background": not args.foreground,
    }
    if isinstance(client, ApiClient):
        return client.post("/api/run", payload)
    return client.run_start(payload)


def list_runs(_ctx: Any, client: Any, _args: argparse.Namespace) -> Any:
    return client.get("/api/runs").get("items", []) if isinstance(client, ApiClient) else client.run_list()


def status_run(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.get(f"/api/runs/{args.run_id}").get("item") if args.run_id else client.get("/api/state")
    return client.run_status(args.run_id)


def resume_run(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.post(f"/api/runs/{args.run_id}/resume", {})
    return client.run_resume(args.run_id)


def cancel_run(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"reason": args.reason}
    if isinstance(client, ApiClient):
        return client.post(f"/api/runs/{args.run_id}/cancel", payload)
    return client.run_cancel(args.run_id, args.reason)
