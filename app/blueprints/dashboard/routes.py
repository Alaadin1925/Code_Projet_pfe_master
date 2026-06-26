"""Dashboard (home) — recent report jobs, like the original app."""
from flask import render_template
from flask_login import login_required

from ...repositories import job_repository
from . import dashboard_bp


@dashboard_bp.route("/")
@login_required
def index():
    return render_template("dashboard/index.html",
                           recent_jobs=job_repository.recent(limit=10))
