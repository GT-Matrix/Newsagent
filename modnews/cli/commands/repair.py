from __future__ import annotations

import argparse
from typing import Any

from modnews.cli.api_client import ApiClient


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("repair", help="Manage extractor repair tasks.")
    nested = parser.add_subparsers(dest="repair_command", required=True)
    nested.add_parser("list").set_defaults(handler=list_tasks)
    create = nested.add_parser("create")
    create.add_argument("source_id")
    create.set_defaults(handler=create_task)
    retry = nested.add_parser("retry")
    retry.add_argument("task_id")
    retry.set_defaults(handler=retry_task)
    promote = nested.add_parser("promote")
    promote.add_argument("task_id")
    promote.set_defaults(handler=promote_task)
    delete = nested.add_parser("delete")
    delete.add_argument("task_id")
    delete.set_defaults(handler=delete_task)


def list_tasks(_ctx: Any, client: Any, _args: argparse.Namespace) -> Any:
    return client.get("/api/repair-tasks").get("items", []) if isinstance(client, ApiClient) else client.repair_tasks()


def create_task(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    payload = {"source_id": args.source_id}
    return client.post("/api/repair-tasks", payload) if isinstance(client, ApiClient) else client.repair_create(payload)


def retry_task(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    return client.post(f"/api/repair-tasks/{args.task_id}/retry", {}) if isinstance(client, ApiClient) else client.repair_retry(args.task_id)


def promote_task(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    return client.post(f"/api/repair-tasks/{args.task_id}/promote", {}) if isinstance(client, ApiClient) else client.repair_promote(args.task_id)


def delete_task(_ctx: Any, client: Any, args: argparse.Namespace) -> Any:
    return client.delete(f"/api/repair-tasks/{args.task_id}") if isinstance(client, ApiClient) else client.repair_delete(args.task_id)
