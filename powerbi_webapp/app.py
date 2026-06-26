import os

from flask import Flask, redirect, render_template, request, url_for, flash, send_from_directory, jsonify
from flask_login import (LoginManager, current_user, login_required,
                          login_user, logout_user)

from core import config as cfg
from core.html_builder import _table_html_preview
from models import JobRun, RegionEmail, User, db, init_db
from jobs.worker import start_worker


def create_app(start_background_worker=True):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = cfg.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{cfg.DB_PATH}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    init_db(app)

    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ── Auth ──────────────────────────────────────────────────────────────────
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for("index"))
            flash("Identifiants invalides.", "error")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # ── Dashboard ────────────────────────────────────────────────────────────
    @app.route("/")
    @login_required
    def index():
        recent_jobs = JobRun.query.order_by(JobRun.created_at.desc()).limit(10).all()
        return render_template("index.html", recent_jobs=recent_jobs)

    # ── Nouveau rapport (dedicated config page) ──────────────────────────────
    @app.route("/new", methods=["GET", "POST"])
    @login_required
    def new_report():
        if request.method == "POST":
            selected_regions = request.form.getlist("regions")
            if not selected_regions:
                flash("Veuillez sélectionner au moins une région.", "error")
            else:
                include_depot     = "include_depot"     in request.form
                include_livraison = "include_livraison" in request.form
                if not include_depot and not include_livraison:
                    flash("Veuillez sélectionner au moins un type de tableau.", "error")
                else:
                    col_depot      = request.form.getlist("col_depot")      or cfg.DEPOT_COL_KEYS_DEFAULT
                    col_livraison  = request.form.getlist("col_livraison") or cfg.LIVRAISON_COL_KEYS_DEFAULT
                    cat_depot      = request.form.getlist("cat_depot")     or cfg.DEPOT_CAT_KEYS_DEFAULT
                    cat_livraison  = request.form.getlist("cat_livraison") or cfg.LIVRAISON_CAT_KEYS_DEFAULT

                    for region in cfg.REGIONS:
                        new_email = request.form.get(f"email_{region}", "").strip()
                        re_row = RegionEmail.query.filter_by(region=region).first()
                        if re_row and re_row.email != new_email:
                            re_row.email = new_email
                    db.session.commit()

                    region_next = request.form.getlist("region_next")

                    job = JobRun(user_id=current_user.id,
                                 include_depot=include_depot,
                                 include_livraison=include_livraison)
                    job.regions        = selected_regions
                    job.col_depot      = col_depot
                    job.col_livraison  = col_livraison
                    job.cat_depot      = cat_depot
                    job.cat_livraison  = cat_livraison
                    job.region_next    = region_next
                    db.session.add(job)
                    db.session.commit()
                    flash(f"Job #{job.id} lancé pour {len(selected_regions)} région(s).", "success")
                    return redirect(url_for("job_status", job_id=job.id))

        region_emails = {r.region: r.email for r in RegionEmail.query.order_by(RegionEmail.region).all()}

        # Load distinct Region Next values from xlsx
        try:
            from core.data_loaders import load_xlsx_df, norm as _norm
            _df = load_xlsx_df(log=lambda _: None)
            _rn = next((c for c in _df.columns if _norm(c) == _norm("Region Next")), None)
            region_next_values = sorted(
                [v for v in _df[_rn].str.strip().dropna().unique() if v]
            ) if _rn else []
        except Exception:
            region_next_values = []

        return render_template("new_report.html",
                               regions=cfg.REGIONS,
                               region_emails=region_emails,
                               default_email=cfg.DEFAULT_EMAIL,
                               depot_columns=cfg.DEPOT_COLUMNS,
                               livraison_columns=cfg.LIVRAISON_COLUMNS,
                               depot_categories=cfg.DEPOT_CATEGORIES,
                               livraison_categories=cfg.DEPOT_CATEGORIES,
                               region_next_values=region_next_values)

    # ── Preview tables (AJAX) ────────────────────────────────────────────────
    @app.route("/preview", methods=["POST"])
    @login_required
    def preview():
        from core.pbi_scraper import build_preview
        regions          = request.form.getlist("regions")
        region           = regions[0] if regions else (cfg.REGIONS[0] if cfg.REGIONS else "")
        include_depot    = "include_depot"     in request.form
        include_livraison = "include_livraison" in request.form
        col_depot        = request.form.getlist("col_depot")      or cfg.DEPOT_COL_KEYS_DEFAULT
        col_livraison    = request.form.getlist("col_livraison")  or cfg.LIVRAISON_COL_KEYS_DEFAULT
        cat_depot        = request.form.getlist("cat_depot")      or cfg.DEPOT_CAT_KEYS_DEFAULT
        cat_livraison    = request.form.getlist("cat_livraison")  or cfg.LIVRAISON_CAT_KEYS_DEFAULT
        region_next      = request.form.getlist("region_next")    or []
        try:
            tables, section_labels, table_sources = build_preview(
                region, include_depot, include_livraison, col_depot, col_livraison,
                cat_depot, cat_livraison=cat_livraison or None,
                region_next=region_next or None
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        tables_html = ""
        for i, t in enumerate(tables):
            if i in section_labels:
                tables_html += (
                    f'<h3 style="color:#0B2A6F;margin-top:1.5rem;border-left:4px solid #F4C20D;'
                    f'padding-left:10px;">{section_labels[i]}</h3>'
                )
            src  = table_sources[i]["source"]      if i < len(table_sources) else ""
            ttyp = table_sources[i]["table_type"]  if i < len(table_sources) else ""
            tables_html += _table_html_preview(t, i + 1, source=src,
                                               table_type=ttyp, region=region)
        return jsonify({"html": tables_html, "region": region})

    # ── Preview IDs drill-down (AJAX) ────────────────────────────────────────
    @app.route("/preview/ids", methods=["POST"])
    @login_required
    def preview_ids():
        from core.data_loaders import load_xlsx_df, load_export_df, load_import_df, norm

        region        = request.form.get("region", "")
        bureau        = request.form.get("bureau", "")
        source        = request.form.get("source", "national")
        table_type    = request.form.get("table_type", "depot")
        col_header    = request.form.get("col_header", "")
        region_next   = request.form.getlist("region_next")
        cat_livraison = request.form.getlist("cat_livraison") or cfg.LIVRAISON_CAT_KEYS_DEFAULT

        try:
            if source == "national":
                df = load_xlsx_df(log=lambda _: None)
            elif source == "export":
                df = load_export_df(log=lambda _: None)
            elif source == "import":
                df, _ = load_import_df(log=lambda _: None)
            else:
                return jsonify({"error": "Source inconnue"}), 400

            from core.pbi_scraper import _apply_region_next

            # Apply Region Next filter first (before depot/livraison-specific logic)
            df = _apply_region_next(df, region_next)

            if table_type == "depot":
                # Depot: filter by Region Depot then Bureau Depot
                reg_dep_col = next((c for c in df.columns if norm(c) == norm("Region Depot")), None)
                bur_col     = next((c for c in df.columns if norm(c) == norm("Bureau depot")), None)
                if reg_dep_col and region:
                    df = df[df[reg_dep_col].str.strip() == region]
                if bur_col and bureau:
                    df = df[df[bur_col].str.strip() == bureau]

            else:
                # Livraison pivot: filter by Region Dernier E then Bureau Dernier E
                from core.tables import _bureau_category as _bur_cat
                reg_de_col  = next((c for c in df.columns if norm(c) == norm("Region dernier E")), None)
                bur_de_col  = next((c for c in df.columns if norm(c) == norm("Bureau dernier E")), None)
                de_col      = next((c for c in df.columns if norm(c) == norm("Dernier E")), None)
                crbt_col    = next((c for c in df.columns if norm(c) == norm("CRBT/ORD")), None)

                if reg_de_col and region:
                    df = df[df[reg_de_col].str.strip() == region]
                # Apply livraison bureau category filter
                active_liv_cats = set(cat_livraison)
                if bur_de_col and active_liv_cats:
                    df = df[df[bur_de_col].str.strip().map(_bur_cat).isin(active_liv_cats)]
                if bur_de_col and bureau:
                    df = df[df[bur_de_col].str.strip() == bureau]

                # Sub-filter by column header (Dernier E value / CRBT / Ordinaire)
                if col_header and col_header not in ("Total IDs", "CA (DT)", ""):
                    if col_header == "CRBT" and crbt_col:
                        df = df[df[crbt_col].str.strip().str.upper() == "CRBT"]
                    elif col_header == "Ordinaire" and crbt_col:
                        df = df[df[crbt_col].str.strip().str.upper() != "CRBT"]
                    elif de_col:
                        df = df[df[de_col].str.strip() == col_header]

            id_col = next((c for c in df.columns if "mailitm" in norm(c)), None)
            if id_col:
                ids = [i for i in df[id_col].dropna().str.strip().tolist() if i]
            else:
                ids = []

            # Extra columns to show alongside the ID
            extra_cols = {}
            for key, xlcol_name in [("Dernier E", "Dernier E"),
                                     ("Type", "CRBT/ORD"),
                                     ("CA", "CA"),
                                     ("Poids", "poids")]:
                col = next((c for c in df.columns if norm(c) == norm(xlcol_name)), None)
                if col:
                    extra_cols[key] = df[col].str.strip().tolist() if id_col else []

            rows = []
            for j, id_ in enumerate(ids):
                row = {"id": id_}
                for key, vals in extra_cols.items():
                    row[key] = vals[j] if j < len(vals) else ""
                rows.append(row)

            label = f"{bureau} — {col_header}" if col_header else bureau
            return jsonify({"rows": rows, "count": len(rows),
                            "bureau": label, "region": region,
                            "extra_cols": list(extra_cols.keys())})

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Job status / history ──────────────────────────────────────────────────
    @app.route("/jobs/<int:job_id>")
    @login_required
    def job_status(job_id):
        job = db.session.get(JobRun, job_id)
        if job is None:
            flash("Job introuvable.", "error")
            return redirect(url_for("jobs_history"))
        return render_template("job_status.html", job=job)

    @app.route("/jobs")
    @login_required
    def jobs_history():
        jobs = JobRun.query.order_by(JobRun.created_at.desc()).limit(50).all()
        return render_template("jobs_history.html", jobs=jobs)

    @app.route("/reports/<path:filename>")
    @login_required
    def download_report(filename):
        return send_from_directory(cfg.REPORTS_DIR, filename, as_attachment=False)

    # ── Clustering analytics ──────────────────────────────────────────────────
    @app.route("/clustering")
    @login_required
    def clustering():
        import json as _json
        from core.data_loaders import load_xlsx_df
        from core.clustering import run_all
        try:
            df = load_xlsx_df(log=lambda _: None)
        except Exception as e:
            flash(f"Erreur chargement données : {e}", "error")
            return redirect(url_for("index"))
        results = run_all(df)
        return render_template("clustering.html",
                               results=results,
                               results_json=_json.dumps(results, default=str))

    # ── Background worker ────────────────────────────────────────────────────
    if start_background_worker:
        start_worker(app)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=False)
