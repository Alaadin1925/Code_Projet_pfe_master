"""Application factory for the La Poste Tunisienne — National Reporting app.

    from app import create_app
    app = create_app()

Layering:  blueprint (route) → service (business logic) → repository (DB) → model.
"""
from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, render_template

from .config import BaseConfig, get_config
from .extensions import csrf, db, login_manager, migrate


def create_app(config: type[BaseConfig] | str | None = None) -> Flask:
    app = Flask(__name__)

    cfg = config if isinstance(config, type) else get_config(config)
    app.config.from_object(cfg)

    _validate_config(app)
    _configure_logging(app)
    _ensure_dirs(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_cli(app)
    _register_error_handlers(app)
    _register_shell_context(app)

    if app.config.get("START_BACKGROUND_WORKER"):
        _start_worker(app)

    app.logger.info("Application ready (env=%s, db=%s)",
                    os.environ.get("FLASK_ENV", "production"),
                    _safe_db_label(app))
    return app


# ── Setup helpers ─────────────────────────────────────────────────────────────

def _validate_config(app: Flask) -> None:
    if not app.config.get("SECRET_KEY"):
        if app.config.get("TESTING"):
            app.config["SECRET_KEY"] = "test-secret-key"
        else:
            raise RuntimeError(
                "SECRET_KEY is not set. Copy .env.example to .env and set a real "
                "value (python -c \"import secrets; print(secrets.token_hex(32))\")."
            )


def _configure_logging(app: Flask) -> None:
    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _ensure_dirs(app: Flask) -> None:
    for key in ("REPORTS_DIR", "UPLOADS_DIR"):
        path = app.config.get(key)
        if path:
            os.makedirs(path, exist_ok=True)


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Import models so SQLAlchemy/Alembic see them, and wire the user loader.
    from .models import User  # noqa: WPS433  (local import avoids circular deps)

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))


def _register_blueprints(app: Flask) -> None:
    from .blueprints.analytics import analytics_bp
    from .blueprints.auth import auth_bp
    from .blueprints.dashboard import dashboard_bp
    from .blueprints.health import health_bp
    from .blueprints.reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(health_bp)

    # The health endpoint must answer without a CSRF token / login.
    csrf.exempt(health_bp)


def _register_cli(app: Flask) -> None:
    from .cli import register_cli
    register_cli(app)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_e):
        db.session.rollback()
        return render_template("errors/500.html"), 500


def _register_shell_context(app: Flask) -> None:
    @app.shell_context_processor
    def _ctx():
        from . import models
        return {"db": db, "models": models}


def _start_worker(app: Flask) -> None:
    try:
        from .jobs.worker import start_worker
        start_worker(app)
    except Exception as exc:  # pragma: no cover - worker must never block boot
        app.logger.warning("Background worker not started: %s", exc)


def _safe_db_label(app: Flask) -> str:
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    return uri.split("@")[-1] if "@" in uri else uri.split("///")[0] + "://..."
