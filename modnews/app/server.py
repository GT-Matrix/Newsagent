from __future__ import annotations

from pathlib import Path

from flask import Flask

from modnews.cli.local_client import LocalClient

from .router import register_routes


def create_app(project_root: Path | None = None) -> Flask:
    app = Flask(__name__)
    app.extensions["modnews_local_client"] = LocalClient(project_root)
    register_routes(app)
    return app
