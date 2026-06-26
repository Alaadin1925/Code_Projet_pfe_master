"""National report table builders + drill-through mappings + KPIs.

Ported from the original `core/tables.py` / `core/data_loaders.py` business logic,
national-only. Operates on a pandas DataFrame whose columns use the ORIGINAL
French headers (built by shipment_repository.national_dataframe), so the proven
logic is preserved verbatim.
"""
from __future__ import annotations

import re

import pandas as pd


def norm(s) -> str:
    return re.sub(r"[\s_\-]+", "", str(s).lower())


def _col(df, name):
    return next((c for c in df.columns if norm(c) == norm(name)), None)


def put_totals_last(rows):
    return ([r for r in rows if str(r).strip()] if rows and not isinstance(rows[0], (list, tuple))
            else rows)


def _bureau_category(name) -> str:
    n = str(name).lower()
    if "agence" in n:
        return "agences"
    if "centre" in n or "cdc" in n:
        return "centres"
    return "bureaux"


# ── Top KPI block (taux livraison, CA, CRBT, intervalle) ──────────────────────

def compute_kpis(fdf) -> dict:
    total = len(fdf)
    kpis = {"livres": 0, "total": total, "taux": 0.0, "avg_intervalle": None, "total_ids": total}
    if total == 0:
        return kpis
    de = _col(fdf, "Dernier E")
    itv = _col(fdf, "Intervalle en jours")
    ca_col = _col(fdf, "CA")
    crbt_col = _col(fdf, "CRBT/ORD")

    if de:
        livres = int(fdf[de].dropna().str.strip().str.lower().str.startswith("envoi liv").sum())
        kpis["livres"] = livres
        kpis["taux"] = round(livres / total * 100, 1)
    if itv:
        vals = pd.to_numeric(fdf[itv], errors="coerce").dropna()
        kpis["avg_intervalle"] = round(float(vals.mean()), 1) if len(vals) else None
    if ca_col:
        kpis["total_ca"] = round(float(pd.to_numeric(fdf[ca_col], errors="coerce").sum()), 2)
    if crbt_col:
        kpis["crbt"] = int((fdf[crbt_col].str.strip().str.upper() == "CRBT").sum())
    return kpis


# ── Dépôt KPI table : Bureau dépôt × CRBT × CA × Nb IDs ───────────────────────

def build_depot_kpi_table(df, region, cat_filter=None):
    """Dépôt KPI table: Bureau dépôt × CRBT × CA × Poids × Nb IDs."""
    reg_col = _col(df, "Region Depot")
    bur_col = _col(df, "Bureau depot")
    crbt_col = _col(df, "CRBT/ORD")
    ca_col = _col(df, "CA")
    poids_col = _col(df, "poids")

    headers = ["Bureau dépôt", "CRBT", "CA", "Poids", "Nb IDs"]
    empty = {"title": "", "headers": headers, "rows": [], "num_rows": 0, "num_cols": len(headers)}
    if not bur_col:
        return empty

    fdf = df[df[reg_col].str.strip() == region].copy() if reg_col else df.copy()
    if fdf.empty:
        return empty

    active = set(cat_filter) if cat_filter else None
    bureaux = sorted(fdf[bur_col].dropna().str.strip().unique())
    rows, tot_crbt, tot_ca, tot_poids, tot_ids = [], 0, 0.0, 0.0, 0
    for b in bureaux:
        if not b or (active and _bureau_category(b) not in active):
            continue
        sub = fdf[fdf[bur_col].str.strip() == b]
        nb_crbt = int((sub[crbt_col].str.strip().str.upper() == "CRBT").sum()) if crbt_col else 0
        ca_val = float(pd.to_numeric(sub[ca_col], errors="coerce").fillna(0).sum()) if ca_col else 0.0
        poids_val = float(pd.to_numeric(sub[poids_col], errors="coerce").fillna(0).sum()) if poids_col else 0.0
        nb_ids = len(sub)
        tot_crbt += nb_crbt
        tot_ca += ca_val
        tot_poids += poids_val
        tot_ids += nb_ids
        rows.append([b, str(nb_crbt) if nb_crbt else "",
                     f"{ca_val:,.0f}".replace(",", " ") if ca_val else "",
                     f"{poids_val:,.0f}".replace(",", " ") if poids_val else "",
                     str(nb_ids)])
    rows.append(["TOTAL", str(tot_crbt), f"{tot_ca:,.0f}".replace(",", " "),
                 f"{tot_poids:,.0f}".replace(",", " "), str(tot_ids)])
    return {"title": "", "headers": headers, "rows": rows,
            "num_rows": len(rows), "num_cols": len(headers)}


def _depot_kpis_for(df, region):
    if df is None or df.empty:
        return {"total": 0, "crbt": 0, "ordinaire": 0, "ca": 0.0, "ca_crbt": 0.0, "ca_ordinaire": 0.0}
    reg_col = _col(df, "Region Depot")
    fdf = df[df[reg_col].str.strip() == region] if (reg_col and region) else df
    total = len(fdf)
    crbt_col = _col(fdf, "CRBT/ORD")
    ca_col = _col(fdf, "CA")
    crbt = int((fdf[crbt_col].str.strip().str.upper() == "CRBT").sum()) if crbt_col else 0
    ca = round(float(pd.to_numeric(fdf[ca_col], errors="coerce").fillna(0).sum()), 2) if ca_col else 0.0
    ca_crbt = ca_ordinaire = 0.0
    if ca_col and crbt_col:
        mask = fdf[crbt_col].str.strip().str.upper() == "CRBT"
        ca_crbt = round(float(pd.to_numeric(fdf.loc[mask, ca_col], errors="coerce").fillna(0).sum()), 2)
        ca_ordinaire = round(float(pd.to_numeric(fdf.loc[~mask, ca_col], errors="coerce").fillna(0).sum()), 2)
    return {"total": total, "crbt": crbt, "ordinaire": total - crbt,
            "ca": ca, "ca_crbt": ca_crbt, "ca_ordinaire": ca_ordinaire}


def compute_depot_kpis(national_df, export_df, region) -> dict:
    """Dépôt KPIs ventilés National / Export / Global (CA split CRBT/Ordinaire)."""
    nat = _depot_kpis_for(national_df, region)
    exp = _depot_kpis_for(export_df, region)
    glo = {"total": nat["total"] + exp["total"], "crbt": nat["crbt"] + exp["crbt"],
           "ordinaire": nat["ordinaire"] + exp["ordinaire"],
           "ca": round(nat["ca"] + exp["ca"], 2),
           "ca_crbt": round(nat["ca_crbt"] + exp["ca_crbt"], 2),
           "ca_ordinaire": round(nat["ca_ordinaire"] + exp["ca_ordinaire"], 2)}
    return {"national": nat, "export": exp, "global": glo}


def _livraison_kpis_for(df, region):
    empty = {"total": 0, "crbt": 0, "ordinaire": 0, "ca": 0.0, "taux": None, "avg_intervalle": None}
    if df is None or df.empty:
        return empty
    reg_de = _col(df, "Region dernier E")
    fdf = df[df[reg_de].str.strip() == region] if (reg_de and region) else df
    if fdf.empty:
        return empty
    total = len(fdf)
    crbt_col = _col(fdf, "CRBT/ORD")
    ca_col = _col(fdf, "CA")
    de_col = _col(fdf, "Dernier E")
    itv_col = _col(fdf, "Intervalle en jours")
    crbt = int((fdf[crbt_col].str.strip().str.upper() == "CRBT").sum()) if crbt_col else 0
    ca = round(float(pd.to_numeric(fdf[ca_col], errors="coerce").fillna(0).sum()), 2) if ca_col else 0.0
    taux = None
    if de_col and total:
        livres = int(fdf[de_col].dropna().str.strip().str.lower().str.startswith("envoi liv").sum())
        taux = round(livres / total * 100, 1)
    avg = None
    if itv_col:
        vals = pd.to_numeric(fdf[itv_col], errors="coerce").dropna()
        avg = round(float(vals.mean()), 1) if len(vals) else None
    return {"total": total, "crbt": crbt, "ordinaire": total - crbt,
            "ca": ca, "taux": taux, "avg_intervalle": avg}


def compute_livraison_kpis(national_df, import_df, region) -> dict:
    """Livraison KPIs ventilés National / Import / Global (filtré par Region dernier E)."""
    nat = _livraison_kpis_for(national_df, region)
    imp = _livraison_kpis_for(import_df, region)
    gtotal = nat["total"] + imp["total"]
    gtaux = None
    if gtotal:
        nl = round((nat["taux"] or 0) / 100 * nat["total"])
        il = round((imp["taux"] or 0) / 100 * imp["total"])
        gtaux = round((nl + il) / gtotal * 100, 1)
    glo = {"total": gtotal, "crbt": nat["crbt"] + imp["crbt"],
           "ordinaire": nat["ordinaire"] + imp["ordinaire"],
           "ca": round(nat["ca"] + imp["ca"], 2), "taux": gtaux, "avg_intervalle": None}
    return {"national": nat, "import": imp, "global": glo}


def build_depot_kpi_drill(df, region, tbl_key, cat_filter=None):
    reg_col = _col(df, "Region Depot")
    bur_col = _col(df, "Bureau depot")
    crbt_col = _col(df, "CRBT/ORD")
    ca_col = _col(df, "CA")
    id_col = _col(df, "MAILITM_FID")
    if not (bur_col and id_col):
        return {}

    fdf = df[df[reg_col].str.strip() == region].copy() if reg_col else df.copy()
    active = set(cat_filter) if cat_filter else None
    headers = ["Bureau dépôt", "CRBT", "CA", "Nb IDs"]
    flat = {}
    for _, row in fdf.iterrows():
        bureau = str(row[bur_col]).strip()
        id_ = str(row[id_col]).strip()
        if not (bureau and id_):
            continue
        if active and _bureau_category(bureau) not in active:
            continue
        crbt_ord = str(row[crbt_col]).strip().upper() if crbt_col else ""
        entry = {"id": id_, "CA": str(row[ca_col]).strip() if ca_col else "",
                 "Type": crbt_ord.capitalize()}
        bkt = flat.setdefault(bureau, {"__all__": []})
        bkt["__all__"].append(entry)
        if crbt_ord == "CRBT":
            bkt.setdefault("CRBT", []).append(entry)
    return {tbl_key: {"cols": ["CA", "Type"], "dim_idx": 0,
                      "headers": ["Bureau dépôt", "CRBT", "CA", "Poids", "Nb IDs"], "data": flat}}


def collect_depot_slider_data(df, region, cat_filter=None):
    """Compact records for the dépôt date-range slider: {b,d,t,c,p}
    (bureau dépôt, date YYYY-MM-DD, CRBT/ORD, ca, poids)."""
    reg_dep = _col(df, "Region Depot")
    bur_dep = _col(df, "Bureau depot")
    date_dep = _col(df, "Date depot")
    crbt_col = _col(df, "CRBT/ORD")
    ca_col = _col(df, "CA")
    poids_col = _col(df, "poids")
    if not bur_dep:
        return []

    fdf = df[df[reg_dep].str.strip() == region].copy() if reg_dep else df.copy()
    active = set(cat_filter) if cat_filter else None
    records = []
    for _, row in fdf.iterrows():
        bur = str(row[bur_dep]).strip()
        if not bur or (active and _bureau_category(bur) not in active):
            continue
        date_val = ""
        if date_dep and str(row[date_dep]).strip():
            try:
                date_val = pd.Timestamp(row[date_dep]).strftime("%Y-%m-%d")
            except Exception:
                date_val = ""
        crbt_ord = str(row[crbt_col]).strip().upper() if crbt_col else ""
        try:
            ca_val = float(str(row[ca_col]).replace(",", ".").replace(" ", "") or "0") if ca_col else 0.0
        except Exception:
            ca_val = 0.0
        try:
            poids_val = float(str(row[poids_col]).replace(",", ".").replace(" ", "") or "0") if poids_col else 0.0
        except Exception:
            poids_val = 0.0
        records.append({"b": bur, "d": date_val, "t": crbt_ord,
                        "c": round(ca_val, 2), "p": round(poids_val, 2)})
    return records


# ── Livraison pivot : Bureau Dernier E × Dernier E + Total + CRBT + Ord + CA ───

def _de_values(fdf, de_col):
    if not de_col:
        return []
    all_de = sorted(fdf[de_col].str.strip().unique())
    envoi = [v for v in all_de if str(v).lower().startswith("envoi liv")]
    rest = [v for v in all_de if v not in envoi and v]
    return envoi + rest


def build_livraison_pivot_table(df, region, cat_filter=None):
    reg_de = _col(df, "Region dernier E")
    bur_de = _col(df, "Bureau dernier E")
    de_col = _col(df, "Dernier E")
    crbt_col = _col(df, "CRBT/ORD")
    ca_col = _col(df, "CA")
    poids_col = _col(df, "poids")

    fdf = df[df[reg_de].str.strip() == region].copy() if reg_de else df.copy()
    empty = {"title": "", "headers": [], "rows": [], "num_rows": 0, "num_cols": 0}
    if fdf.empty or not bur_de:
        return empty

    active = set(cat_filter) if cat_filter else None
    de_vals = _de_values(fdf, de_col)
    headers = ["Bureau Dernier E"] + de_vals + ["Total IDs", "CRBT", "Ordinaire", "CA (DT)", "Poids"]
    bureaux = sorted(fdf[bur_de].str.strip().unique())
    rows = []
    tot_by_de = {v: 0 for v in de_vals}
    tot_ids = tot_crbt = tot_ord = 0
    tot_ca = tot_poids = 0.0
    for bur in bureaux:
        if not bur or (active and _bureau_category(bur) not in active):
            continue
        sub = fdf[fdf[bur_de].str.strip() == bur]
        nb_ids = len(sub)
        crbt = int((sub[crbt_col].str.strip().str.upper() == "CRBT").sum()) if crbt_col else 0
        ord_ = nb_ids - crbt
        ca = float(pd.to_numeric(sub[ca_col], errors="coerce").fillna(0).sum()) if ca_col else 0.0
        poids = float(pd.to_numeric(sub[poids_col], errors="coerce").fillna(0).sum()) if poids_col else 0.0
        tot_ids += nb_ids; tot_crbt += crbt; tot_ord += ord_; tot_ca += ca; tot_poids += poids
        row = [bur]
        if de_col:
            vc = sub[de_col].str.strip().value_counts()
            for v in de_vals:
                c = int(vc.get(v, 0))
                tot_by_de[v] += c
                row.append(str(c) if c else "—")
        row += [str(nb_ids), str(crbt), str(ord_),
                f"{ca:,.0f}".replace(",", " "), f"{poids:,.0f}".replace(",", " ")]
        rows.append(row)
    tot_row = ["TOTAL"] + [str(tot_by_de[v]) if tot_by_de[v] else "—" for v in de_vals]
    tot_row += [str(tot_ids), str(tot_crbt), str(tot_ord),
                f"{tot_ca:,.0f}".replace(",", " "), f"{tot_poids:,.0f}".replace(",", " ")]
    rows.append(tot_row)
    return {"title": "", "headers": headers, "rows": rows,
            "num_rows": len(rows), "num_cols": len(headers)}


def build_livraison_pivot_drill(df, region, tbl_key, cat_filter=None):
    reg_de = _col(df, "Region dernier E")
    bur_de = _col(df, "Bureau dernier E")
    de_col = _col(df, "Dernier E")
    crbt_col = _col(df, "CRBT/ORD")
    ca_col = _col(df, "CA")
    intv_col = _col(df, "Intervalle en jours")
    poids_col = _col(df, "poids")
    id_col = _col(df, "MAILITM_FID")
    if not (bur_de and id_col):
        return {}

    fdf = df[df[reg_de].str.strip() == region].copy() if reg_de else df.copy()
    active = set(cat_filter) if cat_filter else None
    de_vals = _de_values(fdf, de_col)
    headers = ["Bureau Dernier E"] + de_vals + ["Total IDs", "CRBT", "Ordinaire", "CA (DT)", "Poids"]
    flat = {}
    for _, row in fdf.iterrows():
        bur = str(row[bur_de]).strip()
        id_ = str(row[id_col]).strip()
        if not (bur and id_):
            continue
        if active and _bureau_category(bur) not in active:
            continue
        de_val = str(row[de_col]).strip() if de_col else ""
        crbt_ord = str(row[crbt_col]).strip().upper() if crbt_col else ""
        entry = {"id": id_, "Dernier E": de_val, "Type": crbt_ord.capitalize(),
                 "CA": str(row[ca_col]).strip() if ca_col else "",
                 "Intervalle (j)": str(row[intv_col]).strip() if intv_col else "",
                 "poids": str(row[poids_col]).strip() if poids_col else ""}
        bkt = flat.setdefault(bur, {"__all__": []})
        bkt["__all__"].append(entry)
        if de_val:
            bkt.setdefault(de_val, []).append(entry)
        bkt.setdefault("CRBT" if crbt_ord == "CRBT" else "Ordinaire", []).append(entry)
    return {tbl_key: {"cols": ["Dernier E", "Type", "CA", "Intervalle (j)", "poids"],
                      "dim_idx": 0, "headers": headers, "data": flat}}


def collect_livraison_slider_data(df, region, cat_filter=None):
    """Compact records for the livraison date-range slider: {b,d,e,t,c}."""
    reg_de = _col(df, "Region dernier E")
    bur_de = _col(df, "Bureau dernier E")
    date_de = _col(df, "Date dernier E")
    de_col = _col(df, "Dernier E")
    crbt_col = _col(df, "CRBT/ORD")
    ca_col = _col(df, "CA")
    if not bur_de:
        return []

    fdf = df[df[reg_de].str.strip() == region].copy() if reg_de else df.copy()
    active = set(cat_filter) if cat_filter else None
    records = []
    for _, row in fdf.iterrows():
        bur = str(row[bur_de]).strip()
        if not bur or (active and _bureau_category(bur) not in active):
            continue
        date_val = ""
        if date_de and str(row[date_de]).strip():
            try:
                date_val = pd.Timestamp(row[date_de]).strftime("%Y-%m-%d")
            except Exception:
                date_val = ""
        de_val = str(row[de_col]).strip() if de_col else ""
        crbt_ord = str(row[crbt_col]).strip().upper() if crbt_col else ""
        try:
            ca_val = float(str(row[ca_col]).replace(",", ".").replace(" ", "") or "0") if ca_col else 0.0
        except Exception:
            ca_val = 0.0
        records.append({"b": bur, "d": date_val, "e": de_val,
                        "t": crbt_ord, "c": round(ca_val, 2)})
    return records


# ── Export & Import drills (original main-branch logic) ───────────────────────

def build_export_drill(df, region, tbl_key):
    """Export dépôt drill: Bureau depot → IDs, cols [poids, CA], sub-keys CRBT/Ordinaire."""
    reg = _col(df, "Region Depot")
    bur = _col(df, "Bureau depot")
    crbt = _col(df, "CRBT/ORD")
    ca = _col(df, "CA")
    poids = _col(df, "poids")
    id_col = _col(df, "MAILITM_FID")
    if not (bur and id_col):
        return {}
    fdf = df[df[reg].str.strip() == region] if (reg and region) else df
    flat = {}
    for _, row in fdf.iterrows():
        bureau = str(row[bur]).strip()
        id_ = str(row[id_col]).strip()
        if not (bureau and id_):
            continue
        crbt_ord = str(row[crbt]).strip() if crbt else ""
        entry = {"id": id_, "poids": str(row[poids]).strip() if poids else "",
                 "CA": str(row[ca]).strip() if ca else ""}
        bkt = flat.setdefault(bureau, {"__all__": []})
        bkt["__all__"].append(entry)
        if crbt_ord in ("CRBT", "Ordinaire"):
            bkt.setdefault(crbt_ord, []).append(entry)
    return {tbl_key: {"cols": ["poids", "CA"], "dim_idx": 0, "headers": [], "data": flat}}


def build_import_drill(df, region, tbl_key):
    """Import livraison drill: Bureau Dernier E → IDs, cols [Dernier E, Intervalle, poids],
    sub-keys per Dernier E. import.xls has no CA / CRBT-ORD, so those are omitted."""
    reg_de = _col(df, "Region dernier E")
    bur_de = _col(df, "Bureau dernier E")
    de_col = _col(df, "Dernier E")
    intv_col = _col(df, "Intervalle en jours")
    poids = _col(df, "poids")
    id_col = _col(df, "MAILITM_FID")
    if not (bur_de and id_col):
        return {}
    fdf = df[df[reg_de].str.strip() == region] if (reg_de and region) else df
    flat = {}
    for _, row in fdf.iterrows():
        bureau = str(row[bur_de]).strip()
        id_ = str(row[id_col]).strip()
        if not (bureau and id_):
            continue
        evt = str(row[de_col]).strip() if de_col else ""
        entry = {"id": id_, "Dernier E": evt,
                 "Intervalle (j)": str(row[intv_col]).strip() if intv_col else "",
                 "poids": str(row[poids]).strip() if poids else ""}
        bkt = flat.setdefault(bureau, {"__all__": []})
        bkt["__all__"].append(entry)
        if evt:
            bkt.setdefault(evt, []).append(entry)
    return {tbl_key: {"cols": ["Dernier E", "Intervalle (j)", "poids"],
                      "dim_idx": 0, "headers": [], "data": flat}}
