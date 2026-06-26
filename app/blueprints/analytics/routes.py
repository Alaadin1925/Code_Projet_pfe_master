"""Analytics routes: ML clustering insights."""
import json

from flask import flash, redirect, render_template, url_for
from flask_login import login_required

from ...services import analytics_service, clustering_service
from . import analytics_bp


@analytics_bp.route("/clustering")
@login_required
def clustering():
    if not analytics_service.has_data():
        flash("Aucune donnée nationale importée. Lancez l'import d'abord.", "warning")
        return redirect(url_for("dashboard.index"))
    results = clustering_service.run_all()
    return render_template("analytics/clustering.html",
                           results=results,
                           results_json=json.dumps(results, default=str))
