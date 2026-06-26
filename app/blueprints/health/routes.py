"""Health check endpoint (used by Docker healthcheck / load balancers)."""
from flask import jsonify
from sqlalchemy import text

from ...extensions import db
from . import health_bp


@health_bp.route("/health")
def health():
    db_ok = True
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    status = "ok" if db_ok else "degraded"
    return jsonify({"status": status, "database": db_ok}), (200 if db_ok else 503)
