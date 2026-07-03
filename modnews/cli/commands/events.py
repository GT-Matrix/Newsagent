from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("events", help="Inspect progress events.")
    nested = parser.add_subparsers(dest="events_command", required=True)
    list_cmd = nested.add_parser("list")
    list_cmd.add_argument("--limit", type=int, default=100)
    list_cmd.set_defaults(handler=list_events)
    watch = nested.add_parser("watch")
    watch.add_argument("--limit", type=int, default=100)
    watch.set_defaults(handler=list_events)


def list_events(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.get("/api/state").get("events", [])[-args.limit:]
    return client.events_list(args.limit)
