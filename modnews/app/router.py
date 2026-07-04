from __future__ import annotations

from flask import Flask


def register_routes(app: Flask) -> None:
    from .routes.events import bp as events_bp
    from .routes.extractors import bp as extractors_bp
    from .routes.classify import bp as classify_bp
    from .routes.health import bp as health_bp
    from .routes.ingest import bp as ingest_bp
    from .routes.pipeline import bp as pipeline_bp
    from .routes.report import bp as report_bp
    from .routes.runtime import bp as runtime_bp
    from .routes.repair_tasks import bp as repair_tasks_bp
    from .routes.runtime_config import bp as runtime_config_bp
    from .routes.ui import bp as ui_bp
    from .routes.web_jobs import bp as web_jobs_bp

    app.register_blueprint(ui_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(classify_bp)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(extractors_bp)
    app.register_blueprint(pipeline_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(runtime_bp)
    app.register_blueprint(repair_tasks_bp)
    app.register_blueprint(runtime_config_bp)
    app.register_blueprint(web_jobs_bp)
