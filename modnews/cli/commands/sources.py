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
    nested.add_parser("diagnostics").set_defaults(handler=diagnostics)
    rss_cmd = nested.add_parser("rss")
    rss_nested = rss_cmd.add_subparsers(dest="rss_command", required=True)
    rss_add = rss_nested.add_parser("add")
    rss_add.add_argument("id")
    rss_add.add_argument("url")
    rss_add.add_argument("--name")
    rss_add.add_argument("--content-type", default="news")
    rss_add.set_defaults(handler=add_rss_source)
    rss_update = rss_nested.add_parser("update")
    rss_update.add_argument("id")
    rss_update.add_argument("--url")
    rss_update.add_argument("--name")
    rss_update.add_argument("--content-type")
    rss_update.add_argument("--enable", action="store_true")
    rss_update.add_argument("--disable", action="store_true")
    rss_update.set_defaults(handler=update_rss_source)
    rss_disable = rss_nested.add_parser("disable")
    rss_disable.add_argument("id")
    rss_disable.set_defaults(handler=disable_rss_source)
    rss_delete = rss_nested.add_parser("delete")
    rss_delete.add_argument("id")
    rss_delete.set_defaults(handler=delete_rss_source)
    newsnow_cmd = nested.add_parser("newsnow")
    newsnow_nested = newsnow_cmd.add_subparsers(dest="newsnow_command", required=True)
    newsnow_update = newsnow_nested.add_parser("update")
    newsnow_update.add_argument("id")
    newsnow_update.add_argument("--content-type")
    newsnow_update.add_argument("--enable", action="store_true")
    newsnow_update.add_argument("--disable", action="store_true")
    newsnow_update.set_defaults(handler=update_newsnow_source)
    newsnow_enable = newsnow_nested.add_parser("enable")
    newsnow_enable.add_argument("id")
    newsnow_enable.set_defaults(handler=lambda ctx, client, args: update_newsnow_source_value(ctx, client, args.id, {"enabled": True}))
    newsnow_disable = newsnow_nested.add_parser("disable")
    newsnow_disable.add_argument("id")
    newsnow_disable.set_defaults(handler=lambda ctx, client, args: update_newsnow_source_value(ctx, client, args.id, {"enabled": False}))
    site_cmd = nested.add_parser("site")
    site_nested = site_cmd.add_subparsers(dest="site_command", required=True)
    site_add = site_nested.add_parser("add")
    site_add.add_argument("id")
    site_add.add_argument("url")
    site_add.add_argument("--name")
    site_add.add_argument("--extractor")
    site_add.add_argument("--content-type", default="news")
    site_add.set_defaults(handler=add_site_source)
    site_update = site_nested.add_parser("update")
    site_update.add_argument("id")
    site_update.add_argument("--url")
    site_update.add_argument("--name")
    site_update.add_argument("--extractor")
    site_update.add_argument("--content-type")
    site_update.add_argument("--enable", action="store_true")
    site_update.add_argument("--disable", action="store_true")
    site_update.set_defaults(handler=update_site_source)
    site_disable = site_nested.add_parser("disable")
    site_disable.add_argument("id")
    site_disable.set_defaults(handler=disable_site_source)
    site_delete = site_nested.add_parser("delete")
    site_delete.add_argument("id")
    site_delete.set_defaults(handler=delete_site_source)


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


def diagnostics(_ctx: Any, client: Any, _args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.get("/api/source-config/diagnostics")
    return client.source_diagnostics()


def add_rss_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"id": args.id, "url": args.url, "name": args.name or args.id, "enabled": True, "content_type": args.content_type}
    if isinstance(client, ApiClient):
        return client.put(f"/api/source-config/rss/{args.id}", payload)
    return client.sources_rss_add(args.id, args.url, name=args.name, content_type=args.content_type)


def update_rss_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    patch = _source_patch(args)
    if isinstance(client, ApiClient):
        return client.put(f"/api/source-config/rss/{args.id}", {"id": args.id, **patch})
    current = next((row for row in client.sources_list("rss") if row.get("id") == args.id), {})
    return client.rss_update_item(args.id, {**current, **patch, "id": args.id})


def disable_rss_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"id": args.id, "enabled": False}
    if isinstance(client, ApiClient):
        return client.put(f"/api/source-config/rss/{args.id}", payload)
    return client.sources_rss_disable(args.id)


def delete_rss_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.delete(f"/api/source-config/rss/{args.id}")
    return client.rss_delete_item(args.id)


def update_newsnow_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    patch = _source_patch(args)
    return update_newsnow_source_value(_ctx, client, args.id, patch)


def update_newsnow_source_value(_ctx: Any, client: Any, source_id: str, patch: dict[str, Any]) -> Any:
    if isinstance(client, ApiClient):
        return client.patch(f"/api/source-config/newsnow/{source_id}", patch)
    return client.newsnow_update_item(source_id, patch)


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


def update_site_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    patch = _source_patch(args, extractor_key="extractor_id")
    if isinstance(client, ApiClient):
        return client.patch(f"/api/source-config/site-lists/{args.id}", patch)
    return client.site_list_update_item(args.id, patch)


def disable_site_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.patch(f"/api/source-config/site-lists/{args.id}", {"enabled": False})
    return client.sources_site_disable(args.id)


def delete_site_source(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.delete(f"/api/source-config/site-lists/{args.id}")
    return client.sources_site_delete(args.id)


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


def _source_patch(args: argparse.Namespace, *, extractor_key: str | None = None) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    for key in ("url", "name", "content_type"):
        value = getattr(args, key, None)
        if value is not None:
            patch[key] = value
    if extractor_key:
        extractor = getattr(args, "extractor", None)
        if extractor is not None:
            patch[extractor_key] = extractor
    if getattr(args, "enable", False):
        patch["enabled"] = True
    if getattr(args, "disable", False):
        patch["enabled"] = False
    if not patch:
        raise SystemExit("at least one update flag is required")
    return patch
