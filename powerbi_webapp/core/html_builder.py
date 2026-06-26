"""Email HTML and interactive HTML report builders."""
import base64
import json
import os
from datetime import datetime

from . import config as cfg
from .config import C_NAVY, C_YELLOW, C_BG, C_LIGHT


def get_logo_b64():
    if os.path.exists(cfg.LOGO_PATH):
        with open(cfg.LOGO_PATH, "rb") as f:
            data = f.read()
        ext  = os.path.splitext(cfg.LOGO_PATH)[1].lower().lstrip(".")
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        return f"data:image/{mime};base64," + base64.b64encode(data).decode()
    return None


def _is_total_row(row):
    if not row:
        return True
    v = row[0].strip().upper()
    return not v or v == "TOTAL" or v.startswith("TOTAL") or v.startswith("KPI")


def _table_html_email(t, n):
    label = t["title"] or f"Tableau {n} — {' | '.join(t['headers'][:3])}"
    th = "".join(
        f'<th style="padding:9px 14px;background:{C_NAVY};color:#fff;'
        f'text-align:left;white-space:nowrap;font-size:12px;">{h}</th>'
        for h in t["headers"])
    rows_html = ""
    for i, row in enumerate(t["rows"]):
        is_tot = _is_total_row(row)
        if is_tot:
            cells = "".join(
                f'<td style="padding:7px 14px;background:#FFF8E1;font-weight:bold;'
                f'border-top:2px solid {C_YELLOW};font-size:12px;">{c}</td>' for c in row)
        else:
            bg = "#fff" if i % 2 == 0 else C_BG
            cells = "".join(
                f'<td style="padding:7px 14px;border-bottom:1px solid #E4EAF5;'
                f'background:{bg};font-size:12px;">{c}</td>' for c in row)
        rows_html += f"<tr>{cells}</tr>"
    return (
        f'<div style="margin-bottom:28px;">'
        f'<div style="background:{C_NAVY};color:#fff;padding:10px 16px;font-size:13px;'
        f'font-weight:bold;border-radius:6px 6px 0 0;">{label}</div>'
        f'<p style="color:#555;font-size:11px;margin:0;padding:6px 16px;'
        f'background:{C_LIGHT};border:1px solid #D5E1F5;border-top:none;">'
        f'{t["num_rows"]} ligne(s) &times; {t["num_cols"]} colonne(s)</p>'
        f'<div style="overflow-x:auto;border:1px solid #D5E1F5;border-top:none;'
        f'border-radius:0 0 6px 6px;">'
        f'<table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;">'
        f'<thead><tr>{th}</tr></thead><tbody>{rows_html}</tbody></table></div></div>'
    )


def _table_html_preview(t, n, source="", table_type="", region=""):
    """Like _table_html_email but cells are clickable for ID drill-down.
    Livraison pivot: all data cells clickable (passes col header).
    Depot: only first column clickable."""
    label    = t["title"] or f"Tableau {n} — {' | '.join(t['headers'][:3])}"
    is_liv   = (table_type == "livraison")
    th = "".join(
        f'<th style="padding:9px 14px;background:{C_NAVY};color:#fff;'
        f'text-align:left;white-space:nowrap;font-size:12px;">{h}</th>'
        for h in t["headers"])
    rows_html = ""
    src_js   = source.replace("'", "\\'")
    type_js  = table_type.replace("'", "\\'")
    reg_js   = region.replace("'", "\\'")
    headers  = t.get("headers", [])
    for i, row in enumerate(t["rows"]):
        is_tot = _is_total_row(row)
        if is_tot:
            cells = "".join(
                f'<td style="padding:7px 14px;background:#FFF8E1;font-weight:bold;'
                f'border-top:2px solid {C_YELLOW};font-size:12px;">{c}</td>' for c in row)
        else:
            bg = "#fff" if i % 2 == 0 else C_BG
            dim_js = row[0].replace("'", "\\'") if row else ""
            cells  = ""
            for ci, val in enumerate(row):
                hdr     = headers[ci] if ci < len(headers) else ""
                hdr_js  = hdr.replace("'", "\\'")
                if ci == 0:
                    # First column always clickable (dim value)
                    cells += (
                        f'<td style="padding:7px 14px;border-bottom:1px solid #E4EAF5;'
                        f'background:{bg};font-size:12px;cursor:pointer;color:{C_NAVY};'
                        f'font-weight:600;text-decoration:underline dotted;" '
                        f'title="Cliquer pour voir les IDs" '
                        f'onclick="previewDrill(\'{dim_js}\',\'{src_js}\',\'{type_js}\',\'{reg_js}\')">'
                        f'{val}</td>'
                    )
                elif is_liv:
                    # Livraison pivot: every data cell clickable with its col header
                    cells += (
                        f'<td style="padding:7px 14px;border-bottom:1px solid #E4EAF5;'
                        f'background:{bg};font-size:12px;cursor:pointer;" '
                        f'title="Cliquer pour voir les IDs — {hdr}" '
                        f'onclick="previewDrill(\'{dim_js}\',\'{src_js}\',\'{type_js}\',\'{reg_js}\',\'{hdr_js}\')">'
                        f'{val}</td>'
                    )
                else:
                    cells += (
                        f'<td style="padding:7px 14px;border-bottom:1px solid #E4EAF5;'
                        f'background:{bg};font-size:12px;">{val}</td>'
                    )
        rows_html += f"<tr>{cells}</tr>"
    return (
        f'<div style="margin-bottom:28px;">'
        f'<div style="background:{C_NAVY};color:#fff;padding:10px 16px;font-size:13px;'
        f'font-weight:bold;border-radius:6px 6px 0 0;">{label}</div>'
        f'<p style="color:#555;font-size:11px;margin:0;padding:6px 16px;'
        f'background:{C_LIGHT};border:1px solid #D5E1F5;border-top:none;">'
        f'{t["num_rows"]} ligne(s) &times; {t["num_cols"]} colonne(s) '
        f'<em>— cliquez sur un bureau pour voir les identifiants</em></p>'
        f'<div style="overflow-x:auto;border:1px solid #D5E1F5;border-top:none;'
        f'border-radius:0 0 6px 6px;">'
        f'<table style="border-collapse:collapse;width:100%;font-family:Arial,sans-serif;">'
        f'<thead><tr>{th}</tr></thead><tbody>{rows_html}</tbody></table></div></div>'
    )


def build_email_html(filename, slicers, tables, timestamp, has_logo=False, logo_b64=None, kpis=None, section_labels=None):
    if slicers:
        fi_rows = "".join(
            f'<tr><td style="padding:3px 0;font-size:13px;color:#333;">'
            f'<span style="display:inline-block;background:{C_NAVY};color:{C_YELLOW};'
            f'padding:2px 10px;border-radius:3px;font-size:11px;font-weight:bold;'
            f'margin-right:8px;">{s["title"] or "Filtre"}</span>'
            f'{", ".join(v if v.lower() != "(blank)" else "(vide)" for v in s["selected"])}'
            f'</td></tr>'
            for s in slicers if s["selected"])
        filters_html = f'<table cellpadding="0" cellspacing="0" style="width:100%;">{fi_rows}</table>'
    else:
        filters_html = (f'<p style="color:#888;font-style:italic;margin:0;font-size:13px;">'
                        f'Aucun filtre actif.</p>')

    tables_html = ""
    for i, t in enumerate(tables):
        if section_labels and i in section_labels:
            lbl = section_labels[i]
            tables_html += (
                f'<div style="margin:28px 0 16px;border-bottom:3px solid {C_NAVY};padding-bottom:8px;">'
                f'<span style="background:{C_NAVY};color:{C_YELLOW};padding:6px 18px;'
                f'border-radius:6px 6px 0 0;font-size:13px;font-weight:700;letter-spacing:1px;'
                f'text-transform:uppercase;">{lbl}</span></div>'
            )
        tables_html += _table_html_email(t, i+1)

    if logo_b64:
        logo_html = (f'<img src="{logo_b64}" alt="La Poste Tunisienne" '
                     f'style="height:52px;vertical-align:middle;margin-right:14px;">')
    elif has_logo:
        logo_html = (f'<img src="cid:logo_img" alt="La Poste Tunisienne" '
                     f'style="height:52px;vertical-align:middle;margin-right:14px;">')
    else:
        logo_html = ""

    date_fr     = datetime.strptime(timestamp, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y à %H:%M")
    logo_margin = "66px" if (logo_b64 or has_logo) else "2px"

    # KPI block for email
    kpi_email = ""
    if kpis:
        taux      = kpis.get("taux", 0)
        livres    = kpis.get("livres", 0)
        total     = kpis.get("total", 0)
        total_ids = kpis.get("total_ids", total)
        avg       = kpis.get("avg_intervalle")
        avg_s     = f"{avg} j" if avg is not None else "—"
        bar_w     = min(int(taux), 100)
        tid_s     = f"{total_ids:,}".replace(",", " ")
        total_ca  = kpis.get("total_ca")
        ca_s      = (f"{total_ca:,.2f}".replace(",", " ") + " DT")\
                    if total_ca is not None else "—"
        kpi_email = (
            f'<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">'
            f'<tr>'
            f'<td width="34%" style="padding-right:6px;vertical-align:top;">'
            f'<div style="background:{C_LIGHT};border:1px solid #D5E1F5;border-radius:10px;padding:16px 18px;">'
            f'<div style="color:#666;font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-bottom:5px;">Taux de livraison</div>'
            f'<div style="color:{C_NAVY};font-size:26px;font-weight:800;line-height:1;margin-bottom:3px;">{taux}%</div>'
            f'<div style="color:#888;font-size:10px;margin-bottom:8px;">{livres} livrés / {total} envois</div>'
            f'<div style="background:#D5E1F5;border-radius:4px;height:7px;">'
            f'<div style="background:{C_YELLOW};border-radius:4px;height:7px;width:{bar_w}%;"></div>'
            f'</div></div></td>'
            f'<td width="25%" style="padding:0 3px;vertical-align:top;">'
            f'<div style="background:{C_LIGHT};border:1px solid #D5E1F5;border-radius:10px;padding:16px 18px;">'
            f'<div style="color:#666;font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-bottom:5px;">Délai moyen</div>'
            f'<div style="color:{C_NAVY};font-size:26px;font-weight:800;line-height:1;margin-bottom:3px;">{avg_s}</div>'
            f'<div style="color:#888;font-size:10px;">Intervalle dépôt → livraison</div>'
            f'</div></td>'
            f'<td width="25%" style="padding:0 3px;vertical-align:top;">'
            f'<div style="background:{C_NAVY};border-radius:10px;padding:16px 18px;">'
            f'<div style="color:{C_YELLOW};font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-bottom:5px;">Total colis</div>'
            f'<div style="color:#fff;font-size:26px;font-weight:800;line-height:1;margin-bottom:3px;">{tid_s}</div>'
            f'<div style="color:rgba(255,255,255,.6);font-size:10px;">identifiants uniques</div>'
            f'</div></td>'
            f'<td width="25%" style="padding-left:6px;vertical-align:top;">'
            f'<div style="background:#1A6B3A;border-radius:10px;padding:16px 18px;">'
            f'<div style="color:#A8E6C0;font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-bottom:5px;">CA Total</div>'
            f'<div style="color:#fff;font-size:26px;font-weight:800;line-height:1;margin-bottom:3px;">{ca_s}</div>'
            f'<div style="color:rgba(255,255,255,.6);font-size:10px;">chiffre d''affaires</div>'
            f'</div></td>'
            f'</tr></table>'
        )

    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#EAEEF6;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#EAEEF6;padding:24px 0;">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0"
  style="background:#fff;border-radius:10px;overflow:hidden;
         box-shadow:0 4px 20px rgba(11,42,111,.15);max-width:680px;">
  <tr><td style="background:{C_NAVY};padding:0;">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="padding:22px 30px 18px;vertical-align:middle;">
          {logo_html}
          <span style="color:#fff;font-size:20px;font-weight:700;letter-spacing:.5px;vertical-align:middle;">
            LA POSTE TUNISIENNE</span><br>
          <span style="color:{C_YELLOW};font-size:11px;letter-spacing:2px;text-transform:uppercase;
                        margin-left:{logo_margin};">
            Rapport Automatisé &mdash; National</span>
        </td>
        <td style="padding:22px 30px 18px;text-align:right;white-space:nowrap;vertical-align:middle;">
          <span style="background:{C_YELLOW};color:{C_NAVY};padding:6px 14px;
                        border-radius:20px;font-size:12px;font-weight:700;">{date_fr}</span>
        </td>
      </tr>
    </table>
    <div style="height:4px;background:{C_YELLOW};"></div>
  </td></tr>
  <tr><td style="padding:32px 36px 24px;">
    <p style="color:{C_NAVY};font-size:15px;font-weight:600;margin:0 0 16px;">Madame, Monsieur,</p>
    <p style="color:#444;font-size:14px;line-height:1.75;margin:0 0 28px;">
      Veuillez trouver ci-dessous le <strong>rapport automatisé de suivi National</strong>,
      généré le <strong>{date_fr}</strong>. Un fichier HTML interactif est joint.</p>
    {kpi_email}
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
      <tr><td style="background:{C_LIGHT};border-left:4px solid {C_NAVY};
                      padding:14px 18px;border-radius:0 6px 6px 0;">
        <div style="color:{C_NAVY};font-weight:700;font-size:12px;
                     text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;">
          Filtres appliqués</div>{filters_html}
      </td></tr>
    </table>
    <div style="margin-bottom:32px;">
      <div style="background:{C_NAVY};color:#fff;padding:10px 16px;font-size:13px;
                   font-weight:700;border-radius:6px 6px 0 0;">
        Aperçu du tableau de bord Power BI</div>
      <img src="cid:report_img" style="width:100%;display:block;border:1px solid #D5E1F5;
               border-top:none;border-radius:0 0 6px 6px;">
    </div>
    <div style="color:{C_NAVY};font-size:14px;font-weight:700;
                 border-bottom:2px solid {C_YELLOW};padding-bottom:8px;margin-bottom:22px;">
      Données détaillées</div>
    {tables_html}
    <p style="color:#888;font-size:12px;line-height:1.6;margin:24px 0 0;">
      Cordialement,<br>
      <strong style="color:{C_NAVY};">Direction des Systèmes d'Information</strong><br>
      La Poste Tunisienne</p>
  </td></tr>
  <tr><td style="background:{C_NAVY};padding:0;">
    <div style="height:3px;background:{C_YELLOW};"></div>
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="padding:18px 30px;text-align:center;">
        <div style="color:{C_YELLOW};font-size:13px;font-weight:700;letter-spacing:1px;margin-bottom:4px;">
          LA POSTE TUNISIENNE</div>
        <div style="color:rgba(255,255,255,.55);font-size:11px;">
          Direction des Systèmes d'Information &bull; Rapport généré automatiquement</div>
      </td></tr>
    </table>
  </td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def _depot_kpis_html(depot_kpis):
    """KPIs dépôt : une rangée de carreaux par source (National / Export / Global)."""
    if not depot_kpis:
        return ""

    def _card_taux(k, accent=C_YELLOW):
        taux   = k.get("taux")
        livres = round((taux or 0) / 100 * k.get("total", 0)) if taux is not None else 0
        total  = k.get("total", 0)
        bar_w  = min(int(taux or 0), 100)
        taux_s = f"{taux}%" if taux is not None else "—"
        return (
            f'<div class="kpi-card">'
            f'<div class="kpi-icon">&#128230;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label">Taux de livraison</div>'
            f'<div class="kpi-val">{taux_s}</div>'
            f'<div class="kpi-sub">{livres} livrés / {total} envois</div>'
            f'<div class="kpi-bar-bg"><div class="kpi-bar-fill" style="width:{bar_w}%"></div></div>'
            f'</div></div>'
        )

    def _card_delai(k):
        avg = k.get("avg_intervalle")
        avg_s = f"{avg} j" if avg is not None else "—"
        return (
            f'<div class="kpi-card">'
            f'<div class="kpi-icon">&#9201;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label">Délai moyen</div>'
            f'<div class="kpi-val">{avg_s}</div>'
            f'<div class="kpi-sub">Intervalle dépôt → livraison</div>'
            f'</div></div>'
        )

    def _card_total(k):
        total = k.get("total", 0)
        tid_s = f"{total:,}".replace(",", " ")
        return (
            f'<div class="kpi-card" style="background:{C_NAVY};border-color:{C_NAVY};">'
            f'<div class="kpi-icon" style="font-size:24px;">&#128221;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label" style="color:{C_YELLOW};">Total colis</div>'
            f'<div class="kpi-val" style="color:#fff;">{tid_s}</div>'
            f'<div class="kpi-sub" style="color:rgba(255,255,255,.6);">identifiants uniques</div>'
            f'</div></div>'
        )

    def _card_ca(k):
        ca   = k.get("ca", 0.0)
        ca_s = (f"{ca:,.0f}".replace(",", " ") + " DT") if ca else "—"
        return (
            f'<div class="kpi-card" style="background:#1A6B3A;border-color:#1A6B3A;">'
            f'<div class="kpi-icon" style="font-size:24px;">&#128176;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label" style="color:#A8E6C0;">CA Total</div>'
            f'<div class="kpi-val" style="color:#fff;">{ca_s}</div>'
            f'<div class="kpi-sub" style="color:rgba(255,255,255,.6);">chiffre d\'affaires</div>'
            f'</div></div>'
        )

    def _card_crbt(k):
        crbt      = k.get("crbt", 0)
        ordinaire = k.get("ordinaire", 0)
        crbt_s    = f"{crbt:,}".replace(",", " ")
        ord_s     = f"{ordinaire:,}".replace(",", " ")
        return (
            f'<div class="kpi-card" style="background:#7B3F00;border-color:#7B3F00;">'
            f'<div class="kpi-icon" style="font-size:24px;">&#127981;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label" style="color:#FFD580;">CRBT</div>'
            f'<div class="kpi-val" style="color:#fff;">{crbt_s}</div>'
            f'<div class="kpi-sub" style="color:rgba(255,255,255,.7);">Ordinaire : {ord_s}</div>'
            f'</div></div>'
        )
    def _section(title, k, show_delai=True):
        cards = (
            _card_taux(k)
            + (_card_delai(k) if show_delai else "")
            + _card_total(k)
            + _card_ca(k)
            + _card_crbt(k)
        )
        return (
            f'<div style="margin-bottom:18px;">'
            f'<div style="font-size:11px;font-weight:700;color:{C_NAVY};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:8px;padding-left:4px;'
            f'border-left:3px solid {C_YELLOW};padding-left:8px;">{title}</div>'
            f'<div class="kpi-row">{cards}</div>'
            f'</div>'
        )

    nat = depot_kpis.get("national", {})
    exp = depot_kpis.get("export", {})
    glo = depot_kpis.get("global", {})
    return (
        f'<div style="margin:24px 0 20px;">'
        f'<div style="font-size:12px;font-weight:700;color:{C_NAVY};text-transform:uppercase;'
        f'letter-spacing:1px;margin-bottom:14px;border-left:4px solid {C_YELLOW};padding-left:10px;">'
        f'KPIs Dépôt</div>'
        + _section("National", nat, show_delai=True)
        + _section("Export",   exp, show_delai=True)
        + _section("Global",   glo, show_delai=False)
        + f'</div>'
    )


def _livraison_kpis_html(livraison_kpis):
    """KPIs livraison : une rangée de carreaux par source (National / Import / Global)."""
    if not livraison_kpis:
        return ""

    def _card_taux(k):
        taux   = k.get("taux")
        livres = round((taux or 0) / 100 * k.get("total", 0))
        total  = k.get("total", 0)
        bar_w  = min(int(taux or 0), 100)
        taux_s = f"{taux}%" if taux is not None else "—"
        return (
            f'<div class="kpi-card">'
            f'<div class="kpi-icon">&#128230;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label">Taux de livraison</div>'
            f'<div class="kpi-val">{taux_s}</div>'
            f'<div class="kpi-sub">{livres} livrés / {total} colis</div>'
            f'<div class="kpi-bar-bg"><div class="kpi-bar-fill" style="width:{bar_w}%"></div></div>'
            f'</div></div>'
        )

    def _card_delai(k):
        avg   = k.get("avg_intervalle")
        avg_s = f"{avg} j" if avg is not None else "—"
        return (
            f'<div class="kpi-card">'
            f'<div class="kpi-icon">&#9201;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label">Délai moyen</div>'
            f'<div class="kpi-val">{avg_s}</div>'
            f'<div class="kpi-sub">Intervalle moyen en jours</div>'
            f'</div></div>'
        )

    def _card_total(k):
        total = k.get("total", 0)
        tid_s = f"{total:,}".replace(",", " ")
        return (
            f'<div class="kpi-card" style="background:{C_NAVY};border-color:{C_NAVY};">'
            f'<div class="kpi-icon" style="font-size:24px;">&#128221;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label" style="color:{C_YELLOW};">Total colis</div>'
            f'<div class="kpi-val" style="color:#fff;">{tid_s}</div>'
            f'<div class="kpi-sub" style="color:rgba(255,255,255,.6);">identifiants uniques</div>'
            f'</div></div>'
        )

    def _card_ca(k):
        ca   = k.get("ca", 0.0)
        ca_s = (f"{ca:,.0f}".replace(",", " ") + " DT") if ca else "—"
        return (
            f'<div class="kpi-card" style="background:#1A6B3A;border-color:#1A6B3A;">'
            f'<div class="kpi-icon" style="font-size:24px;">&#128176;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label" style="color:#A8E6C0;">CA Total</div>'
            f'<div class="kpi-val" style="color:#fff;">{ca_s}</div>'
            f'<div class="kpi-sub" style="color:rgba(255,255,255,.6);">chiffre d\'affaires</div>'
            f'</div></div>'
        )

    def _card_crbt(k):
        crbt      = k.get("crbt", 0)
        ordinaire = k.get("ordinaire", 0)
        crbt_s    = f"{crbt:,}".replace(",", " ")
        ord_s     = f"{ordinaire:,}".replace(",", " ")
        return (
            f'<div class="kpi-card" style="background:#7B3F00;border-color:#7B3F00;">'
            f'<div class="kpi-icon" style="font-size:24px;">&#127981;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label" style="color:#FFD580;">CRBT</div>'
            f'<div class="kpi-val" style="color:#fff;">{crbt_s}</div>'
            f'<div class="kpi-sub" style="color:rgba(255,255,255,.7);">Ordinaire : {ord_s}</div>'
            f'</div></div>'
        )

    def _section(title, k, show_delai=True):
        cards = (
            _card_taux(k)
            + (_card_delai(k) if show_delai else "")
            + _card_total(k)
            + _card_ca(k)
            + _card_crbt(k)
        )
        return (
            f'<div style="margin-bottom:18px;">'
            f'<div style="font-size:11px;font-weight:700;color:{C_NAVY};text-transform:uppercase;'
            f'letter-spacing:1.5px;margin-bottom:8px;'
            f'border-left:3px solid {C_YELLOW};padding-left:8px;">{title}</div>'
            f'<div class="kpi-row">{cards}</div>'
            f'</div>'
        )

    nat = livraison_kpis.get("national", {})
    imp = livraison_kpis.get("import", {})
    glo = livraison_kpis.get("global", {})
    return (
        f'<div style="margin:24px 0 20px;">'
        f'<div style="font-size:12px;font-weight:700;color:{C_NAVY};text-transform:uppercase;'
        f'letter-spacing:1px;margin-bottom:14px;border-left:4px solid {C_YELLOW};padding-left:10px;">'
        f'KPIs Livraison</div>'
        + _section("National", nat, show_delai=True)
        + _section("Import",   imp, show_delai=True)
        + _section("Global",   glo, show_delai=False)
        + f'</div>'
    )


def build_interactive_html(slicers, tables, drill_mappings, timestamp, logo_b64=None, kpis=None, auto_refresh=False, section_labels=None, depot_kpis=None, livraison_kpis=None, liv_slider_data=None):
    fi = ""
    if slicers:
        items = "".join(
            f'<li><strong style="color:{C_NAVY};">{s["title"] or "Filtre"}</strong>'
            f' : {", ".join(v if v.lower() != "(blank)" else "(vide)" for v in s["selected"])}</li>'
            for s in slicers if s["selected"])
        fi = (f'<div class="fbox"><strong>Filtres appliqués :</strong>'
              f'<ul style="margin:8px 0 0;padding-left:20px;">{items}</ul></div>')
    kpi_html = ""
    if kpis:
        taux      = kpis.get("taux", 0)
        livres    = kpis.get("livres", 0)
        total     = kpis.get("total", 0)
        total_ids = kpis.get("total_ids", total)
        avg       = kpis.get("avg_intervalle")
        avg_s     = f"{avg} j" if avg is not None else "—"
        bar_w     = min(int(taux), 100)
        tid_s     = f"{total_ids:,}".replace(",", " ")
        total_ca  = kpis.get("total_ca")
        ca_s      = (f"{total_ca:,.2f}".replace(",", " ") + " DT")\
                    if total_ca is not None else "—"
        kpi_html = (
            f'<div class="kpi-row">'
            f'<div class="kpi-card">'
            f'<div class="kpi-icon">&#128230;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label">Taux de livraison</div>'
            f'<div class="kpi-val">{taux}%</div>'
            f'<div class="kpi-sub">{livres} livrés / {total} envois</div>'
            f'<div class="kpi-bar-bg"><div class="kpi-bar-fill" style="width:{bar_w}%"></div></div>'
            f'</div></div>'
            f'<div class="kpi-card">'
            f'<div class="kpi-icon">&#9201;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label">Délai moyen</div>'
            f'<div class="kpi-val">{avg_s}</div>'
            f'<div class="kpi-sub">Intervalle dépôt → livraison</div>'
            f'</div></div>'
            f'<div class="kpi-card" style="background:{C_NAVY};border-color:{C_NAVY};">'
            f'<div class="kpi-icon" style="font-size:24px;">&#128221;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label" style="color:{C_YELLOW};">Total colis</div>'
            f'<div class="kpi-val" style="color:#fff;">{tid_s}</div>'
            f'<div class="kpi-sub" style="color:rgba(255,255,255,.6);">identifiants uniques</div>'
            f'</div></div>'
            f'<div class="kpi-card" style="background:#1A6B3A;border-color:#1A6B3A;">'
            f'<div class="kpi-icon" style="font-size:24px;">&#128176;</div>'
            f'<div class="kpi-body">'
            f'<div class="kpi-label" style="color:#A8E6C0;">CA Total</div>'
            f'<div class="kpi-val" style="color:#fff;">{ca_s}</div>'
            f'<div class="kpi-sub" style="color:rgba(255,255,255,.6);">chiffre d\'affaires</div>'
            f'</div></div>'
            f'</div>'
        )

    depot_kpis_html     = _depot_kpis_html(depot_kpis)         if depot_kpis     else ""
    livraison_kpis_html = _livraison_kpis_html(livraison_kpis) if livraison_kpis else ""

    # Find the table index of the first LIVRAISON table (for slider targeting)
    _first_liv_idx = next(
        (n for n in range(len(tables)) if section_labels and section_labels.get(n) == "LIVRAISON"),
        None)
    _show_slider = bool(liv_slider_data and any(r.get("d") for r in liv_slider_data)
                        and _first_liv_idx is not None)
    _first_liv_tk = f"t{_first_liv_idx}" if _first_liv_idx is not None else ""

    th_html = ""
    for n, t in enumerate(tables):
        if section_labels and n in section_labels:
            lbl = section_labels[n]
            th_html += (
                f'<div class="section-hdr">'
                f'<span class="section-hdr-text">{lbl}</span></div>'
            )
            if lbl == "DEPOT" and depot_kpis_html:
                th_html += depot_kpis_html
            if lbl == "LIVRAISON" and livraison_kpis_html:
                th_html += livraison_kpis_html
            if lbl == "LIVRAISON" and _show_slider:
                th_html += (
                    f'<div class="liv-slider-box">'
                    f'<div class="liv-slider-title">&#128197; Filtrer par Date Dernier E</div>'
                    f'<div class="liv-slider-row">'
                    f'<label>Du&nbsp;<input type="date" id="liv-d-min" onchange="applyLivFilter()"></label>'
                    f'<span class="liv-sep">&#8594;</span>'
                    f'<label>Au&nbsp;<input type="date" id="liv-d-max" onchange="applyLivFilter()"></label>'
                    f'<button class="liv-reset-btn" onclick="resetLivFilter()">R&#233;initialiser</button>'
                    f'<span id="liv-filter-info" class="liv-filter-info"></span>'
                    f'</div></div>'
                )
        tk         = f"t{n}"
        dm         = drill_mappings.get(tk, {})
        dm_data    = dm.get("data", {}) if isinstance(dm, dict) else {}
        has_drill  = bool(dm_data)
        dim_idx_dm = dm.get("dim_idx", 0) if isinstance(dm, dict) else 0
        label      = t["title"] or f"Tableau {n+1}"
        hint       = ' <span class="hint">— cliquez pour explorer</span>' if has_drill else ""
        pbi_tot_idx = set(
            ri for ri, row in enumerate(t["rows"])
            if not (row[dim_idx_dm].strip() if dim_idx_dm < len(row) else "")
            or (row[dim_idx_dm].strip().lower() if dim_idx_dm < len(row) else "") == "total"
        )
        col_totals = [None] * len(t["headers"])
        for ci in range(len(t["headers"])):
            vals = []
            for ri, row in enumerate(t["rows"]):
                if ri in pbi_tot_idx: continue
                if ci < len(row):
                    try: vals.append(float(row[ci].replace(" ","").replace(" ","").replace(",",".")))
                    except: pass
            if vals: col_totals[ci] = str(int(round(sum(vals))))
        th = "".join(f'<th>{h}</th>' for h in t["headers"])
        # Compute CA per dim value from drill entries
        ca_by_dv = {}
        if has_drill and dm_data:
            for _dv, _dd in dm_data.items():
                _ents = _dd.get("__all__", []) if isinstance(_dd, dict) else _dd
                _s = 0.0
                for _e in _ents:
                    try: _s += float(str(_e.get("CA") or "0").replace(",","").replace(" ","") or "0")
                    except: pass
                if _s: ca_by_dv[_dv] = round(_s, 2)
        show_ca = bool(ca_by_dv)
        if show_ca:
            th += '<th style="color:#1A6B3A;font-weight:700;white-space:nowrap;">CA (DT)</th>'
        rows_html = ""
        for ri, row in enumerate(t["rows"]):
            is_tot = ri in pbi_tot_idx
            cells = ""
            dv_js  = (row[dim_idx_dm].replace("\\", "\\\\").replace("'", "\\'")
                     if dim_idx_dm < len(row) else "")
            for ci, val in enumerate(row):
                hdr = t["headers"][ci] if ci < len(t["headers"]) else ""
                if is_tot:
                    cells += f'<td class="tot-cell">{val}</td>'
                elif has_drill:
                    if ci == dim_idx_dm:
                        cells += f'<td class="cl dim-cell" onclick="drill(\'{tk}\',\'{dv_js}\',undefined)">{val}</td>'
                    elif "total" not in hdr.lower():
                        hdr_js = hdr.replace("\\", "\\\\").replace("'", "\\'")
                        cells += f'<td class="cl dat-cell" onclick="drill(\'{tk}\',\'{dv_js}\',\'{hdr_js}\')">{val}</td>'
                    else:
                        cells += f'<td class="cl" onclick="drill(\'{tk}\',\'{dv_js}\',undefined)">{val}</td>'
                else:
                    cells += f'<td>{val}</td>'
            if show_ca:
                _dv_k = row[dim_idx_dm].strip() if dim_idx_dm < len(row) else ""
                _ca_v = ca_by_dv.get(_dv_k, 0)
                if is_tot:
                    _ca_s2 = f"{sum(ca_by_dv.values()):.2f}" if ca_by_dv else "—"
                    cells += f'<td class="tot-cell">{_ca_s2}</td>'
                elif _ca_v:
                    cells += f'<td class="ca-cell">{_ca_v:.2f}</td>'
                else:
                    cells += '<td class="ca-cell">—</td>'
            rows_html += f'<tr class="{"tot" if is_tot else ""}">{cells}</tr>'

        foot_cells = ""
        for ci, tot in enumerate(col_totals):
            if ci == 0 and not tot:
                foot_cells += '<td class="foot-total"><strong>Total</strong></td>'
            else:
                foot_cells += f'<td class="foot-total">{tot or "—"}</td>'
        if show_ca and ca_by_dv:
            _ca_gt = round(sum(ca_by_dv.values()), 2)
            foot_cells += f'<td class="foot-total" style="color:#28A745;">{_ca_gt:.2f}</td>'
        tfoot = f"<tfoot><tr>{foot_cells}</tr></tfoot>" if any(col_totals) else ""
        _is_first_liv = (_show_slider and n == _first_liv_idx)
        _head_id = ' id="liv-nat-head"' if _is_first_liv else ""
        _body_id = ' id="liv-nat-body"' if _is_first_liv else ""
        _meta_id = ' id="liv-nat-meta"' if _is_first_liv else ""
        th_html += (
            f'<h3>{label}{hint}</h3>'
            f'<p class="meta"{_meta_id}>{t["num_rows"]} lignes × {t["num_cols"]} colonnes</p>'
            f'<div class="tw"><table id="{tk}"><thead{_head_id}><tr>{th}</tr></thead>'
            f'<tbody{_body_id}>{rows_html}</tbody>{tfoot}</table></div>'
        )
    js_data      = json.dumps(drill_mappings, ensure_ascii=False)
    liv_raw_json = json.dumps(liv_slider_data or [], ensure_ascii=False) if _show_slider else "[]"
    date_fr  = datetime.strptime(timestamp, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y à %H:%M")
    logo_tag = (f'<img src="{logo_b64}" alt="La Poste Tunisienne" '
                f'style="height:48px;margin-right:14px;vertical-align:middle;">'
                if logo_b64 else "")
    refresh  = '<meta http-equiv="refresh" content="6">' if auto_refresh else ""
    html = f"""<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">{refresh}
<title>Rapport National — La Poste Tunisienne</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:'Segoe UI',Arial,sans-serif;margin:0;padding:0;background:{C_BG};color:#333;font-size:14px}}
.wrapper{{max-width:1400px;margin:auto;padding:24px}}
.page-header{{background:{C_NAVY};border-radius:10px 10px 0 0;overflow:hidden}}
.page-header .top{{display:flex;align-items:center;justify-content:space-between;padding:20px 28px 16px}}
.brand{{color:#fff;font-size:22px;font-weight:700}}.sub{{color:{C_YELLOW};font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-top:4px}}
.badge{{background:{C_YELLOW};color:{C_NAVY};padding:6px 16px;border-radius:20px;font-size:12px;font-weight:700;white-space:nowrap}}
.accent-bar{{height:4px;background:{C_YELLOW}}}
.content{{background:#fff;border-radius:0 0 10px 10px;padding:28px;box-shadow:0 4px 20px rgba(11,42,111,.1);margin-bottom:24px}}
h3{{color:{C_NAVY};border-left:4px solid {C_YELLOW};padding-left:12px;margin-top:32px;margin-bottom:6px;font-size:15px}}
.hint{{color:{C_YELLOW};font-size:11px;font-weight:normal;font-style:italic}}
.meta{{color:#666;font-size:12px;margin:2px 0 8px}}.tw{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin-bottom:10px;background:white;border-radius:6px;box-shadow:0 1px 6px rgba(11,42,111,.08)}}
th{{background:{C_NAVY};color:white;padding:9px 14px;text-align:left;white-space:nowrap;font-size:12px}}
td{{padding:7px 14px;border-bottom:1px solid #E4EAF5;font-size:13px}}
tr:nth-child(even) td{{background:{C_BG}}}
.tot td,.tot-cell{{background:#FFF8E1;font-weight:bold;border-top:2px solid {C_YELLOW}}}.ca-cell{{color:#1A6B3A;font-weight:600;}}
tfoot td,.foot-total{{background:{C_NAVY}!important;color:#fff!important;font-weight:700;font-size:12px;padding:7px 14px;border-top:3px solid {C_YELLOW}}}
.cl{{cursor:pointer}}.dim-cell:hover td,.dim-cell:hover{{background:#FFF0C8!important;font-weight:600}}
.dat-cell:hover{{background:{C_LIGHT}!important}}
.fbox{{background:{C_LIGHT};border-left:4px solid {C_NAVY};padding:14px 18px;margin-bottom:24px;border-radius:0 6px 6px 0}}
.kpi-row{{display:flex;gap:16px;margin-bottom:28px;flex-wrap:wrap}}
.kpi-card{{flex:1;min-width:200px;background:{C_LIGHT};border:1px solid #D5E1F5;border-radius:10px;padding:18px 20px;display:flex;gap:14px;align-items:flex-start}}
.kpi-icon{{font-size:28px;line-height:1}}.kpi-body{{flex:1}}
.kpi-label{{color:#666;font-size:11px;text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-bottom:4px}}
.kpi-val{{color:{C_NAVY};font-size:26px;font-weight:800;line-height:1;margin-bottom:4px}}
.kpi-sub{{color:#888;font-size:11px}}
.kpi-bar-bg{{background:#D5E1F5;border-radius:4px;height:6px;margin-top:8px}}
.kpi-bar-fill{{background:{C_YELLOW};border-radius:4px;height:6px}}
#panel{{display:none;position:fixed;bottom:0;left:0;right:0;background:white;border-top:4px solid {C_YELLOW};padding:16px 28px;box-shadow:0 -4px 24px rgba(11,42,111,.2);max-height:50vh;overflow-y:auto;z-index:999}}
#panel h3{{margin:0 0 4px;border-left:4px solid {C_YELLOW};padding-left:10px;font-size:15px}}
#xbtn{{float:right;cursor:pointer;font-size:24px;color:#999;background:none;border:none;line-height:1}}
.tag{{display:inline-block;background:{C_NAVY};color:{C_YELLOW};padding:3px 12px;border-radius:12px;font-size:12px;margin-left:6px;font-weight:600}}
.col-tag{{display:inline-block;background:{C_YELLOW};color:{C_NAVY};padding:2px 10px;border-radius:12px;font-size:11px;margin-left:4px;font-weight:600;vertical-align:middle}}
#ptable{{width:auto;min-width:420px;box-shadow:none}}
#ptable th{{background:#1A3D8A;font-size:12px;padding:7px 12px}}
#ptable td{{font-size:12px;padding:6px 12px}}
.no-data{{color:#999;font-style:italic}}
.section-hdr{{margin:32px 0 16px;border-bottom:3px solid {C_NAVY};padding-bottom:0;}}
.section-hdr-text{{background:{C_NAVY};color:{C_YELLOW};padding:7px 20px;display:inline-block;border-radius:6px 6px 0 0;font-size:13px;font-weight:700;letter-spacing:1px;text-transform:uppercase;}}
.liv-slider-box{{background:#EEF4FF;border:1px solid #C5D9F8;border-radius:8px;padding:14px 18px;margin-bottom:18px;}}
.liv-slider-title{{font-size:11px;font-weight:700;color:{C_NAVY};text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px;}}
.liv-slider-row{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}}
.liv-slider-row label{{font-size:13px;color:#444;display:flex;align-items:center;gap:6px;}}
.liv-slider-row input[type=date]{{padding:5px 10px;border:1px solid #C5D9F8;border-radius:5px;font-size:13px;color:{C_NAVY};font-family:inherit;cursor:pointer;}}
.liv-sep{{color:{C_NAVY};font-weight:700;font-size:18px;}}
.liv-reset-btn{{padding:6px 14px;background:{C_NAVY};color:#fff;border:none;border-radius:5px;font-size:12px;cursor:pointer;font-weight:600;}}
.liv-reset-btn:hover{{background:#1A3D8A;}}
.liv-filter-info{{font-size:12px;color:#666;font-style:italic;}}
footer{{text-align:center;padding:16px;background:{C_NAVY};border-radius:10px;color:rgba(255,255,255,.5);font-size:11px;margin-top:4px}}
footer span{{color:{C_YELLOW};font-weight:700}}
</style></head><body>
<div class="wrapper">
  <div class="page-header">
    <div class="top">
      <div style="display:flex;align-items:center;">{logo_tag}
        <div><div class="brand">LA POSTE TUNISIENNE</div>
             <div class="sub">Rapport National &mdash; Interactif</div></div>
      </div>
      <div class="badge">{date_fr}</div>
    </div>
    <div class="accent-bar"></div>
  </div>
  <div class="content">KPIS_BLOCKFILTER_INFOTABLES_HTML</div>
  <footer><span>LA POSTE TUNISIENNE</span> &bull; Direction des Systèmes d'Information</footer>
</div>
<div id="panel">
  <button id="xbtn" onclick="closeP()">&#x2715;</button>
  <h3>Identifiants &mdash; <span id="lbl"></span></h3>
  <p id="cnt" style="color:#666;font-size:12px;margin:4px 0 10px"></p>
  <div style="overflow-x:auto">
    <table id="ptable"><thead id="phead"></thead><tbody id="pbody"></tbody></table>
  </div>
</div>
<script>
const D=DRILL_DATA;
function drill(tk,dv,colH){{
  const tm=D[tk]||{{}};const cols=tm.cols||[];
  const ddata=(tm.data||{{}})[dv]||{{}};
  const key=colH||'__all__';
  let rows=ddata[key]||(Array.isArray(ddata)?ddata:[]);
  rows=Array.isArray(rows)?rows:[];
  let label='<span class="tag">'+dv+'</span>';
  if(colH)label+='<span class="col-tag">'+colH+'</span>';
  document.getElementById('lbl').innerHTML=label;
  document.getElementById('cnt').textContent=rows.length+' identifiant(s)';
  document.getElementById('phead').innerHTML='<tr><th>MAILITM_FID</th>'+cols.map(c=>'<th>'+c+'</th>').join('')+'</tr>';
  if(rows.length){{
    document.getElementById('pbody').innerHTML=rows.map(r=>{{
      const id=typeof r==='string'?r:(r.id||'');
      const extras=cols.map(c=>{{

        return '<td>'+(r[c]!==undefined?r[c]:'')+'</td>';
      }}).join('');
      return '<tr><td>'+id+'</td>'+extras+'</tr>';
    }}).join('');
  }}else{{
    document.getElementById('pbody').innerHTML='<tr><td class="no-data" colspan="'+(cols.length+1)+'">Aucun identifiant.</td></tr>';
  }}
  document.getElementById('panel').style.display='block';
  document.getElementById('panel').scrollIntoView({{behavior:'smooth',block:'end'}});
}}
function closeP(){{document.getElementById('panel').style.display='none';}}
LIV_SLIDER_JS
</script></body></html>"""
    if _show_slider:
        _liv_tk_js = _first_liv_tk
        _slider_js = f"""
const LIV_RAW={liv_raw_json};
const _livDs=LIV_RAW.map(r=>r.d).filter(Boolean).sort();
const LIV_MIN=_livDs[0]||'';
const LIV_MAX=_livDs[_livDs.length-1]||'';
window.addEventListener('load',function(){{
  var mn=document.getElementById('liv-d-min');
  var mx=document.getElementById('liv-d-max');
  if(!mn)return;
  mn.value=LIV_MIN; mx.value=LIV_MAX;
  applyLivFilter();
}});
function applyLivFilter(){{
  var mn=(document.getElementById('liv-d-min')||{{}}).value||'';
  var mx=(document.getElementById('liv-d-max')||{{}}).value||'';
  var fil=LIV_RAW.filter(function(r){{
    if(!r.d)return true;
    return(!mn||r.d>=mn)&&(!mx||r.d<=mx);
  }});
  rebuildLivTable(fil,mn,mx);
}}
function resetLivFilter(){{
  var mn=document.getElementById('liv-d-min');
  var mx=document.getElementById('liv-d-max');
  if(mn)mn.value=LIV_MIN; if(mx)mx.value=LIV_MAX;
  applyLivFilter();
}}
function rebuildLivTable(data,mn,mx){{
  var bHead=document.getElementById('liv-nat-head');
  var bBody=document.getElementById('liv-nat-body');
  var bMeta=document.getElementById('liv-nat-meta');
  if(!bHead||!bBody)return;
  var bureaux=[...new Set(data.map(r=>r.b))].filter(Boolean).sort();
  var deSet=new Set(data.map(r=>r.e).filter(Boolean));
  var envoi=[...deSet].filter(v=>v.toLowerCase().startsWith('envoi liv')).sort();
  var rest=[...deSet].filter(v=>!v.toLowerCase().startsWith('envoi liv')).sort();
  var deVals=[...envoi,...rest];
  var hdrs=['Bureau Dernier E',...deVals,'Total IDs','CRBT','Ordinaire','CA (DT)'];
  bHead.innerHTML='<tr>'+hdrs.map(h=>'<th>'+h+'</th>').join('')+'</tr>';
  var tIds=0,tCrbt=0,tOrd=0,tCa=0.0;
  var tDe={{}};
  deVals.forEach(v=>{{tDe[v]=0;}});
  var C_NAV='{C_NAVY}',C_BG='{C_BG}',C_YEL='{C_YELLOW}';
  var bodyHtml=bureaux.map(function(bur,i){{
    var sub=data.filter(r=>r.b===bur);
    var nb=sub.length;
    var cr=sub.filter(r=>r.t==='CRBT').length;
    var or_=nb-cr;
    var ca=sub.reduce((s,r)=>s+(r.c||0),0);
    var dCts={{}};
    deVals.forEach(v=>{{dCts[v]=sub.filter(r=>r.e===v).length;tDe[v]+=dCts[v];}});
    tIds+=nb;tCrbt+=cr;tOrd+=or_;tCa+=ca;
    var bg=i%2===0?'#fff':C_BG;
    var caS=Math.round(ca).toString().replace(/\\B(?=(\\d{{3}})+(?!\\d))/g,' ');
    var dv_js=bur.replace(/\\\\/g,'\\\\\\\\').replace(/'/g,"\\\\'");
    var cells='<td class="cl dim-cell" style="cursor:pointer;color:'+C_NAV+';font-weight:600;" '
      +'onclick="drill(\\'{_liv_tk_js}\\',\\''+dv_js+'\\',undefined)">'+bur+'</td>';
    deVals.forEach(v=>{{cells+='<td style="background:'+bg+'">'+(dCts[v]?dCts[v]:'&mdash;')+'</td>';}});
    cells+='<td style="background:'+bg+'">'+nb+'</td>';
    cells+='<td style="background:'+bg+'">'+cr+'</td>';
    cells+='<td style="background:'+bg+'">'+or_+'</td>';
    cells+='<td style="background:'+bg+'">'+caS+'</td>';
    return '<tr>'+cells+'</tr>';
  }}).join('');
  var tCaS=Math.round(tCa).toString().replace(/\\B(?=(\\d{{3}})+(?!\\d))/g,' ');
  var totCells='<td class="tot-cell">TOTAL</td>';
  deVals.forEach(v=>{{totCells+='<td class="tot-cell">'+(tDe[v]?tDe[v]:'&mdash;')+'</td>';}});
  totCells+='<td class="tot-cell">'+tIds+'</td><td class="tot-cell">'+tCrbt+'</td>';
  totCells+='<td class="tot-cell">'+tOrd+'</td><td class="tot-cell">'+tCaS+'</td>';
  bBody.innerHTML=bodyHtml+'<tr>'+totCells+'</tr>';
  if(bMeta){{
    var rng=(mn&&mx)?' | '+mn.split('-').reverse().join('/')+' → '+mx.split('-').reverse().join('/'):'';
    bMeta.textContent=data.length+' colis'+rng;
  }}
  var fi=document.getElementById('liv-filter-info');
  if(fi)fi.textContent=data.length+' / '+LIV_RAW.length+' colis';
}}"""
    else:
        _slider_js = ""

    return (html.replace("KPIS_BLOCK", kpi_html)
                .replace("FILTER_INFO", fi)
                .replace("TABLES_HTML", th_html)
                .replace("DRILL_DATA", js_data)
                .replace("LIV_SLIDER_JS", _slider_js))