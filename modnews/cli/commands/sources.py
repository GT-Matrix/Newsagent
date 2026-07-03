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
    rss_cmd = nested.add_parser("rss")
    rss_nested = rss_cmd.add_subparsers(dest="rss_command", required=True)
    rss_add = rss_nested.add_parser("add")
    rss_add.add_argument("id")
    rss_add.add_argument("url")
    rss_add.add_argument("--name")
    rss_add.add_argument("--content-type", default="news")
    rss_add.set_defaults(handler=add_rss_source)
    rss_disable = rss_nested.add_parser("disable")
    rss_disable.add_argument("id")
    rss_disable.set_defaults(handler=disable_rss_source)
    site_cmd = nested.add_parser("site")
    site_nested = site_cmd.add_subparsers(dest="site_command", required=True)
    site_add = site_nested.add_parser("add")
    site_add.add_argument("id")
    site_add.add_argument("url")
    site_add.add_argument("--name")
    site_add.add_argument("--extractor")
    site_add.add_argument("--content-type", default="news")
    site_add.set_defaults(handler=add_site_source)


def list_sources(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        config = client.get("/api/source-config")
        sources = config.get("sources", {})
        if args.type:
            return _rows(args.type, sources.get(args.type))
        rows = []
        for source_type, value in sources.items():
            rows.extend(_rows(source_type, value))
        return rows
    return client.sources_list(args.type)


def add_rss_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"id": args.id, "url": args.url, "name": args.name or args.id, "enabled": True, "content_type": args.content_type}
    if isinstance(client, ApiClient):
        return client.put(f"/api/source-config/rss/{args.id}", payload)
    return client.sources_rss_add(args.id, args.url, name=args.name, content_type=args.content_type)


def disable_rss_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"id": args.id, "enabled": False}
    if isinstance(client, ApiClient):
        return client.put(f"/api/source-config/rss/{args.id}", payload)
    return client.sources_rss_disable(args.id)


def add_site_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {
        "id": args.id,
        "url": args.url,
        "name": args.name or args.id,
        "enabled": True,
        "extractor_id": args.extractor or args.id,
        "content_type": args.content_type,
    }
    if isinstance(client, ApiClient):
        return client.put(f"/api/source-config/site-lists/{args.id}", payload)
    return client.sources_site_add(
        args.id,
        args.url,
        name=args.name,
        extractor_id=args.extractor,
        content_type=args.content_type,
    )


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
