from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("queue", help="Inspect the local task event queue.")
    nested = parser.add_subparsers(dest="queue_command", required=True)
    nested.add_parser("status").set_defaults(handler=status)
    list_cmd = nested.add_parser("list")
    list_cmd.add_argument("--state", default="")
    list_cmd.set_defaults(handler=list_queue)
    show_cmd = nested.add_parser("show")
    show_cmd.add_argument("task_id")
    show_cmd.set_defaults(handler=show_queue)
    drain_cmd = nested.add_parser("drain")
    drain_cmd.add_argument("--limit", type=int)
    drain_cmd.set_defaults(handler=drain_queue)
    cancel_cmd = nested.add_parser("cancel")
    cancel_cmd.add_argument("task_id")
    cancel_cmd.add_argument("--reason", default="cancelled by user")
    cancel_cmd.set_defaults(handler=cancel_queue)
    retry_cmd = nested.add_parser("retry")
    retry_cmd.add_argument("task_id")
    retry_cmd.set_defaults(handler=retry_queue)
    echo_cmd = nested.add_parser("echo")
    echo_cmd.add_argument("task_id")
    echo_cmd.add_argument("--message", default="ok")
    echo_cmd.set_defaults(handler=echo_queue)


def status(_ctx: Any, client: Any, _args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.get("/api/queue/status")
    return getattr(client, "queue_status", lambda: {"error": "queue status is local-only"})()


def list_queue(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    states = {item for item in args.state.split(",") if item}
    if isinstance(client, ApiClient):
        query = f"?state={args.state}" if args.state else ""
        return client.get(f"/api/queue{query}").get("items", [])
    return getattr(client, "queue_list", lambda _states=None: [])(states or None)


def show_queue(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.get(f"/api/queue/{args.task_id}")
    return client.queue_show(args.task_id)


def drain_queue(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.post("/api/queue/drain", {"limit": args.limit})
    return client.queue_drain(args.limit)


def echo_queue(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"message": args.message}
    if isinstance(client, ApiClient):
        return client.post("/api/queue/echo", {"task_id": args.task_id, "payload": payload})
    return client.queue_echo(args.task_id, payload)


def cancel_queue(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"reason": args.reason}
    if isinstance(client, ApiClient):
        return client.post(f"/api/queue/{args.task_id}/cancel", payload)
    return client.queue_cancel(args.task_id, args.reason)


def retry_queue(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    if isinstance(client, ApiClient):
        return client.post(f"/api/queue/{args.task_id}/retry", {})
    return client.queue_retry(args.task_id)
