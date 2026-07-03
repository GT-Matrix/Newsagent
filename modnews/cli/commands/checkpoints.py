from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("checkpoints", help="Inspect run checkpoints.")
    nested = parser.add_subparsers(dest="checkpoints_command", required=True)
    list_cmd = nested.add_parser("list")
    list_cmd.add_argument("--run")
    list_cmd.set_defaults(handler=list_checkpoints)


def list_checkpoints(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        query = f"?run={args.run}" if args.run else ""
        return client.get(f"/api/checkpoints{query}").get("items", [])
    return client.checkpoints_list(args.run)
