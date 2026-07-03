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
    publish_cmd = nested.add_parser("publish")
    publish_cmd.add_argument("checkpoint_path")
    publish_cmd.set_defaults(handler=publish_checkpoint)


def list_checkpoints(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        query = f"?run={args.run}" if args.run else ""
        return client.get(f"/api/checkpoints{query}").get("items", [])
    return client.checkpoints_list(args.run)


def publish_checkpoint(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.post("/api/checkpoints/publish", {"checkpoint_path": args.checkpoint_path})
    return client.checkpoint_publish(args.checkpoint_path)
