from __future__ import annotations

from flask import Flask

from .router import register_routes


def create_app() -> Flask:
    app = Flask(__name__)
    register_routes(app)
    return app
