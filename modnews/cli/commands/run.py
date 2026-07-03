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


def start_run(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"only": args.only or None, "disable_classification": args.disable_classify, "background": not args.foreground}
    if isinstance(client, ApiClient):
        return client.post("/api/run", payload)
    return client.run_start(payload)


def list_runs(_ctx: Any, client: Any, _args: argparse.Namespace) -> Any:
    return [] if isinstance(client, ApiClient) else client.run_list()


def status_run(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    return client.get("/api/state") if isinstance(client, ApiClient) else client.run_status(args.run_id)
