from __future__ import annotations

from flask import current_app

from modnews.cli.local_client import LocalClient


def local_client() -> LocalClient:
    client = current_app.extensions.get("modnews_local_client")
    if client is None:
        client = LocalClient()
        current_app.extensions["modnews_local_client"] = client
    return client
