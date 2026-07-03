from __future__ import annotations

import argparse
import json
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("config", help="Read and update runtime configuration.")
    nested = parser.add_subparsers(dest="config_command", required=True)
    nested.add_parser("show").set_defaults(handler=show)
    set_cmd = nested.add_parser("set")
    set_cmd.add_argument("key")
    set_cmd.add_argument("value")
    set_cmd.add_argument("--dry-run", action="store_true")
    set_cmd.set_defaults(handler=set_value)


def show(_ctx: Any, client: Any, _args: argparse.Namespace) -> Any:
    return client.get("/api/runtime-config") if isinstance(client, ApiClient) else client.config_show(include_paths=True)


def set_value(ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    value = _parse_value(args.value)
    if ctx.dry_run or args.dry_run:
        return {"dry_run": True, "key": args.key, "value": value}
    if isinstance(client, ApiClient):
        if args.key.startswith("steps."):
            _, step_id, leaf = args.key.split(".", 2)
            return client.patch(f"/api/runtime-config/steps/{step_id}", {leaf: value})
        if args.key.startswith("classification."):
            leaf = args.key.split(".", 1)[1]
            return client.patch("/api/runtime-config/classification", {leaf: value})
        raise SystemExit("API config set supports steps.* and classification.*")
    return client.config_set(args.key, value)


def _parse_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        return value
