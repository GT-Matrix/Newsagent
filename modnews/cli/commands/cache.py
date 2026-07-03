from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("cache", help="Inspect and clear caches.")
    nested = parser.add_subparsers(dest="cache_command", required=True)
    nested.add_parser("status").set_defaults(handler=status_cache)
    clear = nested.add_parser("clear")
    clear.add_argument("--llm", action="store_true")
    clear.add_argument("--embedding", action="store_true")
    clear.set_defaults(handler=clear_cache)


def status_cache(_ctx: Any, client: Any, _args: argparse.Namespace) -> Any:
    return client.get("/api/cache") if isinstance(client, ApiClient) else client.cache_status()


def clear_cache(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.post("/api/cache/clear", {"llm": args.llm, "embedding": args.embedding})
    return client.cache_clear(llm=args.llm, embedding=args.embedding)
