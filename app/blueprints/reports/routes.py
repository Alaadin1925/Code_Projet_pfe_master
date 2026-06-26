"""Report job routes: create (with per-region recipients), preview, status, history, download."""
import os

from flask import (Response, abort, current_app, flash, redirect,
                   render_template, request, send_from_directory, url_for)
from flask_login import current_user, login_required

from ...repositories import (job_repository, recipient_repository,
                             shipment_repository)
from ...services import report_service
from . import reports_bp


@reports_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_report():
    cfg = current_app.config
    regions = cfg["REGIONS"]
    recipient_repository.ensure_seeded(regions)

    if request.method == "POST":
        params, error = _parse_form(regions)
        if error:
            flash(error, "error")
        else:
            recipient_repository.upsert_many(params.pop("_emails_edit"))
            params["region_emails"] = recipient_repository.email_map()
            job = job_repository.create_job(current_user.id, params)
            flash(f"Job #{job.id} lancé pour {len(params['regions'])} région(s).", "success")
            return redirect(url_for("reports.job_status", job_id=job.id))

    return render_template(
        "reports/new.html",
        regions=regions,
        region_emails=recipient_repository.email_map(),
        default_recipient=cfg.get("MAIL_DEFAULT_RECIPIENT") or "(adresse par défaut non définie)",
        depot_categories=cfg["DEPOT_CATEGORIES"],
        livraison_categories=cfg["LIVRAISON_CATEGORIES"],
        depot_columns=cfg["DEPOT_COLUMNS"],
        livraison_columns=cfg["LIVRAISON_COLUMNS"],
        next_region_values=shipment_repository.distinct_next_regions(),
        mail_enabled=cfg.get("MAIL_ENABLED"),
    )


@reports_bp.route("/preview", methods=["POST"])
@login_required
def preview():
    params, error = _parse_form(current_app.config["REGIONS"], for_preview=True)
    if error:
        return Response(f"<p style='color:#a6271c;font-family:sans-serif'>{error}</p>",
                        mimetype="text/html")
    region = (params["regions"] or [None])[0]
    return Response(report_service.render_region_html(region, params), mimetype="text/html")


@reports_bp.route("/jobs")
@login_required
def history():
    return render_template("reports/history.html", jobs=job_repository.recent(limit=50))


@reports_bp.route("/jobs/<int:job_id>")
@login_required
def job_status(job_id):
    job = job_repository.get(job_id)
    if job is None:
        flash("Job introuvable.", "error")
        return redirect(url_for("reports.history"))
    return render_template("reports/job_status.html", job=job)


@reports_bp.route("/download/<path:filename>")
@login_required
def download(filename):
    reports_dir = current_app.config["REPORTS_DIR"]
    if os.path.basename(filename) != filename:  # block path traversal
        abort(404)
    return send_from_directory(reports_dir, filename, as_attachment=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_form(regions, for_preview=False):
    """Build job params from the submitted form. Returns (params, error_message)."""
    selected = request.form.getlist("regions")
    include_depot = "include_depot" in request.form
    include_livraison = "include_livraison" in request.form

    if not for_preview and not selected:
        return None, "Veuillez sélectionner au moins une région."
    if not include_depot and not include_livraison:
        return None, "Veuillez sélectionner au moins un type de rapport (Dépôt / Livraison)."

    params = {
        "regions": selected,
        "include_depot": include_depot,
        "include_livraison": include_livraison,
        "cat_depot": request.form.getlist("cat_depot"),
        "cat_livraison": request.form.getlist("cat_livraison"),
        "col_depot": request.form.getlist("col_depot"),
        "col_livraison": request.form.getlist("col_livraison"),
        "next_regions": request.form.getlist("region_next"),
        "email": "email" in request.form,
        "_emails_edit": {r: request.form.get(f"email_{r}", "").strip() for r in regions},
    }
    return params, None
