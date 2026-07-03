from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path
from typing import Any

from .api_client import ApiClient
from .context import CliContext
from .local_client import LocalClient
from .output import print_payload


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    ctx = CliContext(
        project_root=Path(args.project_root).resolve(),
        mode=args.mode,
        api_url=args.api_url,
        output_format=args.format,
        dry_run=args.dry_run,
    )
    client = resolve_client(ctx)
    if ctx.output_format in {"json", "jsonl"}:
        with contextlib.redirect_stdout(io.StringIO()):
            payload = args.handler(ctx, client, args)
    else:
        payload = args.handler(ctx, client, args)
    if payload is not None:
        print_payload(payload, ctx.output_format)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="modnews", description="ModNews command line interface.")
    parser.add_argument("--project-root", default=".", help="Project root. Defaults to current directory.")
    parser.add_argument("--mode", choices=["auto", "api", "local"], default="auto")
    parser.add_argument("--api-url", default="http://127.0.0.1:5055")
    parser.add_argument("--format", choices=["table", "json", "jsonl"], default="table")
    parser.add_argument("--dry-run", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    from .commands import cache, checkpoints, config, events, extractors, ingest, jobs, outputs, queue, repair, run, server, sources

    server.register(subparsers)
    run.register(subparsers)
    events.register(subparsers)
    queue.register(subparsers)
    config.register(subparsers)
    sources.register(subparsers)
    ingest.register(subparsers)
    extractors.register(subparsers)
    jobs.register(subparsers)
    repair.register(subparsers)
    cache.register(subparsers)
    checkpoints.register(subparsers)
    outputs.register(subparsers)
    return parser


def resolve_client(ctx: CliContext) -> Any:
    if ctx.mode in {"auto", "api"}:
        api = ApiClient(ctx.api_url)
        if api.available():
            return api
        if ctx.mode == "api":
            raise SystemExit(f"API is not available at {ctx.api_url}")
    return LocalClient(ctx.project_root)


def _call(client: Any, local_name: str, api_path: str, *args: Any, **kwargs: Any) -> Any:
    if isinstance(client, ApiClient):
        return client.get(api_path)
    return getattr(client, local_name)(*args, **kwargs)


if __name__ == "__main__":
    main()
