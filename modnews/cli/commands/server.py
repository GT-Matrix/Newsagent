from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("server", help="Manage the API server.")
    nested = parser.add_subparsers(dest="server_command", required=True)
    start = nested.add_parser("start")
    start.add_argument("--host", default=os.environ.get("MODNEWS_PROGRESS_HOST", "127.0.0.1"))
    start.add_argument("--port", type=int, default=int(os.environ.get("MODNEWS_PROGRESS_PORT", "5055")))
    start.set_defaults(handler=start_server)
    status = nested.add_parser("status")
    status.set_defaults(handler=server_status)


def start_server(_ctx: Any, _client: Any, args: argparse.Namespace) -> None:
    subprocess.run([sys.executable, "-m", "modnews.cli.commands.server_entry", "--host", args.host, "--port", str(args.port)], check=True)


def server_status(ctx: Any, _client: Any, _args: argparse.Namespace) -> dict[str, Any]:
    api = ApiClient(ctx.api_url)
    return {"api_url": ctx.api_url, "available": api.available()}
