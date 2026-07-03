from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("sources", help="Inspect configured sources.")
    nested = parser.add_subparsers(dest="sources_command", required=True)
    list_cmd = nested.add_parser("list")
    list_cmd.add_argument("--type", choices=["rss", "newsnow", "site_lists"], default=None)
    list_cmd.set_defaults(handler=list_sources)


def list_sources(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    config = client.get("/api/source-config") if isinstance(client, ApiClient) else client.config_show()
    sources = config.get("sources", {})
    if args.type:
        return _rows(args.type, sources.get(args.type))
    rows = []
    for source_type, value in sources.items():
        rows.extend(_rows(source_type, value))
    return rows


def _rows(source_type: str, value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [{"source_type": source_type, **row} for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [
            {"source_type": source_type, "id": source_id, **row}
            for source_id, row in value.items()
            if isinstance(row, dict)
        ]
    return []
