"""Report generation: per-region interactive HTML report (KPI cards + Dépôt &
Livraison tables with drill-down + date slider), written to REPORTS_DIR and
optionally emailed (branded body + interactive HTML attached)."""
from __future__ import annotations

import os
import re
from datetime import datetime

from flask import current_app

from ..extensions import db
from ..reports import build_email_html, build_interactive_html, get_logo_b64
from ..repositories import job_repository, shipment_repository
from . import table_builder as tb


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name or "national")


def _build(region, params: dict) -> dict:
    """Build report artifacts for one region: National+Export (Dépôt) and
    National+Import (Livraison) comparison, all from SQL Server."""
    nr = params.get("next_regions")
    nat_df = shipment_repository.national_dataframe(next_regions=nr)
    exp_df = shipment_repository.export_dataframe(next_regions=nr)
    imp_df = shipment_repository.import_dataframe(next_regions=nr)
    cat_depot = params.get("cat_depot") or None
    cat_livraison = params.get("cat_livraison") or None
    include_depot = params.get("include_depot", True)
    include_livraison = params.get("include_livraison", True)

    # Top KPI block (kept; hidden in the report when per-source KPI cards show).
    if nat_df.empty:
        fdf = nat_df
    elif region:
        rc = tb._col(nat_df, "Region Depot")
        fdf = nat_df[nat_df[rc].str.strip() == region] if rc else nat_df
    else:
        fdf = nat_df
    kpis = tb.compute_kpis(fdf)

    slicers = []
    if region:
        slicers.append({"title": "Region Depot", "selected": [region]})
    if nr:
        slicers.append({"title": "Region Next", "selected": list(nr)})

    # Per-source KPI cards (always computed → matches the original report).
    depot_kpis = tb.compute_depot_kpis(nat_df, exp_df, region)
    livraison_kpis = tb.compute_livraison_kpis(nat_df, imp_df, region)

    tables, section_labels, drill_mappings = [], {}, {}
    liv_slider, dep_slider = [], []
    idx = 0
    if include_depot:
        t = tb.build_depot_kpi_table(nat_df, region, cat_filter=cat_depot)
        t["title"] = "National — Dépôt"
        tables.append(t); section_labels[idx] = "DEPOT"
        drill_mappings[f"t{idx}"] = tb.build_depot_kpi_drill(
            nat_df, region, f"t{idx}", cat_filter=cat_depot).get(f"t{idx}", {})
        dep_slider = tb.collect_depot_slider_data(nat_df, region, cat_filter=cat_depot)
        idx += 1
        te = tb.build_depot_kpi_table(exp_df, region, cat_filter=cat_depot)
        te["title"] = "Export — Dépôt"
        tables.append(te)
        drill_mappings[f"t{idx}"] = tb.build_export_drill(
            exp_df, region, f"t{idx}").get(f"t{idx}", {})
        idx += 1
    if include_livraison:
        t = tb.build_livraison_pivot_table(nat_df, region, cat_filter=cat_livraison)
        t["title"] = "National — Livraison"
        tables.append(t); section_labels[idx] = "LIVRAISON"
        drill_mappings[f"t{idx}"] = tb.build_livraison_pivot_drill(
            nat_df, region, f"t{idx}", cat_filter=cat_livraison).get(f"t{idx}", {})
        liv_slider = tb.collect_livraison_slider_data(nat_df, region, cat_filter=cat_livraison)
        idx += 1
        ti = tb.build_livraison_pivot_table(imp_df, region, cat_filter=cat_livraison)
        ti["title"] = "Import — Livraison"
        tables.append(ti)
        drill_mappings[f"t{idx}"] = tb.build_import_drill(
            imp_df, region, f"t{idx}").get(f"t{idx}", {})
        idx += 1

    return {"tables": tables, "section_labels": section_labels,
            "drill_mappings": drill_mappings, "slicers": slicers, "kpis": kpis,
            "depot_kpis": depot_kpis, "livraison_kpis": livraison_kpis,
            "liv_slider": liv_slider, "dep_slider": dep_slider}


def render_region_html(region, params: dict | None = None) -> str:
    """Interactive HTML report for a region (used by preview + file generation)."""
    params = params or {}
    a = _build(region, params)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return build_interactive_html(
        a["slicers"], a["tables"], a["drill_mappings"], ts, get_logo_b64(),
        a["kpis"], section_labels=a["section_labels"], depot_kpis=a["depot_kpis"],
        livraison_kpis=a["livraison_kpis"],
        liv_slider_data=a["liv_slider"], dep_slider_data=a["dep_slider"])


def generate_region_report(region, params: dict | None = None) -> str:
    """Write the interactive HTML report file. Returns the absolute path."""
    html = render_region_html(region, params)
    reports_dir = current_app.config["REPORTS_DIR"]
    os.makedirs(reports_dir, exist_ok=True)
    fname = f"report_{_safe(region or 'national')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    path = os.path.join(reports_dir, fname)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return path


def run_report_job(job, log=None) -> tuple[int, list[str]]:
    """One interactive report per region; email each to its recipient if enabled."""
    log = log or (lambda *_: None)
    params = job.params
    regions = params.get("regions") or [None]
    region_emails = params.get("region_emails") or {}
    want_email = bool(params.get("email"))
    mail_on = current_app.config.get("MAIL_ENABLED")
    if want_email and not mail_on:
        log("⚠ Email demandé mais désactivé (MAIL_ENABLED=false) — génération sans envoi.")

    files, success = [], 0
    for region in regions:
        try:
            a = _build(region, params)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            html = build_interactive_html(
                a["slicers"], a["tables"], a["drill_mappings"], ts, get_logo_b64(),
                a["kpis"], section_labels=a["section_labels"], depot_kpis=a["depot_kpis"],
        livraison_kpis=a["livraison_kpis"],
        liv_slider_data=a["liv_slider"], dep_slider_data=a["dep_slider"])
            reports_dir = current_app.config["REPORTS_DIR"]
            os.makedirs(reports_dir, exist_ok=True)
            fname = f"report_{_safe(region or 'national')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            path = os.path.join(reports_dir, fname)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
            files.append(path)

            emailed_to = None
            if want_email and mail_on:
                emailed_to = _email_region(region, path, a, ts, region_emails, log)
            job_repository.add_generated_report(job.id, fname, region=region, emailed_to=emailed_to)
            success += 1
            log(f"✅ Rapport généré : {fname} ({region or 'national'})"
                + (f" → 📧 {emailed_to}" if emailed_to else ""))
        except Exception as exc:
            db.session.rollback()
            log(f"❌ Échec pour {region or 'national'} : {exc}")
    return success, files


def _email_region(region, path, artifacts, ts, region_emails, log):
    from .mail_service import MailNotConfigured, send
    recipient = (region_emails.get(region or "") or "").strip() or None
    body = build_email_html(artifacts["slicers"], artifacts["tables"], ts,
                            kpis=artifacts["kpis"], section_labels=artifacts["section_labels"])
    date_fr = datetime.strptime(ts, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y")
    subject = f"[La Poste Tunisienne] Rapport National — {region or 'National'} — {date_fr}"
    try:
        return send(recipient, subject, body, attachment_path=path)
    except MailNotConfigured as exc:
        log(f"  ⚠ Email non configuré : {exc}")
    except Exception as exc:
        log(f"  ⚠ Échec d'envoi email ({region or 'national'}) : {exc}")
    return None
