from __future__ import annotations

from flask import Flask

from modnews.cli.local_client import LocalClient

from .router import register_routes


def create_app() -> Flask:
    app = Flask(__name__)
    app.extensions["modnews_local_client"] = LocalClient()
    register_routes(app)
    return app
