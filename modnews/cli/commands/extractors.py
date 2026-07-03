from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("extractors", help="Manage managed extractors.")
    nested = parser.add_subparsers(dest="extractors_command", required=True)
    nested.add_parser("list").set_defaults(handler=list_extractors)
    nested.add_parser("scan").set_defaults(handler=list_extractors)
    enable = nested.add_parser("enable")
    enable.add_argument("id")
    enable.set_defaults(handler=lambda ctx, client, args: set_enabled(ctx, client, args.id, True))
    disable = nested.add_parser("disable")
    disable.add_argument("id")
    disable.set_defaults(handler=lambda ctx, client, args: set_enabled(ctx, client, args.id, False))


def list_extractors(_ctx: Any, client: Any, _args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.get("/api/extractors").get("items", [])
    return client.extractors_list()


def set_enabled(_ctx: Any, client: Any, source_id: str, enabled: bool) -> Any:
    if isinstance(client, ApiClient):
        return client.patch(f"/api/extractors/{source_id}", {"enabled": enabled})
    return client.extractor_set_enabled(source_id, enabled)
