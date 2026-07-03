from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("outputs", help="Inspect published output files.")
    nested = parser.add_subparsers(dest="outputs_command", required=True)
    nested.add_parser("status").set_defaults(handler=status)


def status(_ctx: Any, client: Any, _args: argparse.Namespace) -> Any:
    return client.get("/api/outputs") if isinstance(client, ApiClient) else client.outputs_status()
