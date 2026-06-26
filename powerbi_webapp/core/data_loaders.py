"""xlsx/xls loaders, normalization helpers, filtering and KPI computation."""
import re
import pandas as pd

from . import config as cfg


def norm(s):
    return re.sub(r'[\s_\-]+', '', str(s).lower())


def has_blank_selection(vals):
    return any(v.lower().strip() in cfg._BLANK_TOKENS for v in vals)


def xlsx_filter(df, col, selected_vals):
    real = [v for v in selected_vals if v.lower().strip() not in cfg._BLANK_TOKENS]
    has_blank = has_blank_selection(selected_vals)
    if has_blank and real:
        return df[df[col].str.strip().isin([""] + real)]
    if has_blank:
        return df[df[col].str.strip() == ""]
    return df[df[col].isin(real)]


def load_xlsx_df(log=print):
    """Load the national sheet of the main xlsx, computing the
    Categorie_Bureau_Dernier_E_nle helper column."""
    df = pd.read_excel(cfg.XLSX_PATH, sheet_name="national", header=2, dtype=str).fillna("")
    _cat = lambda v: ("Agences" if "agence" in str(v).lower()
                      else "Centres de distribution" if "centre" in str(v).lower()
                      else "Bureaux")
    bde_col = next((c for c in df.columns
                    if norm(c) in {norm("Bureau dernier E"), norm("Bureau next")}), None)
    if bde_col:
        df["Categorie_Bureau_Dernier_E_nle"] = df[bde_col].apply(_cat)
        log(f"  ↳ Categorie_Bureau_Dernier_E_nle computed from [{bde_col}]")
    else:
        log("  ⚠ Bureau dernier E column not found in xlsx")
    return df


def load_export_df(log=print):
    return pd.read_excel(cfg.XLSX_PATH, sheet_name="export", header=2, dtype=str).fillna("")


def load_import_df(log=print):
    df = pd.read_excel(cfg.IMPORT_XLS_PATH, dtype=str).fillna("")
    events = sorted(set(e.strip() for e in df["Dernier E"].dropna().unique() if e.strip()))
    return df, events


def compute_kpis(fdf):
    total = len(fdf)
    kpis  = {"livres": 0, "total": total, "taux": 0.0, "avg_intervalle": None, "total_ids": total}

    de  = next((c for c in fdf.columns if norm(c) == norm("Dernier E")), None)
    itv = next((c for c in fdf.columns if norm(c) == norm("Intervalle en jours")), None)

    # Taux livraison = % colis où Dernier E commence par "envoi liv"
    if de and total > 0:
        livres = int(fdf[de].dropna().str.strip().str.lower().str.startswith("envoi liv").sum())
        kpis["livres"] = livres
        kpis["taux"]   = round(livres / total * 100, 1)

    if itv:
        try:
            vals = pd.to_numeric(fdf[itv], errors="coerce").dropna()
            kpis["avg_intervalle"] = round(float(vals.mean()), 1) if len(vals) > 0 else None
        except Exception:
            pass

    ca_col   = next((c for c in fdf.columns if norm(c) == "ca"), None)
    crbt_col = next((c for c in fdf.columns if norm(c) == norm("CRBT/ORD")), None)

    if ca_col:
        try:
            kpis["total_ca"] = round(float(pd.to_numeric(fdf[ca_col], errors="coerce").sum()), 2)
        except Exception:
            pass
    if crbt_col:
        kpis["crbt"] = int((fdf[crbt_col].str.strip().str.upper() == "CRBT").sum())

    return kpis


def compute_depot_kpis(nat_df, export_df, region):
    """KPIs dépôt ventilés : national / export / global."""
    def _kpis_for(df):
        if df is None or df.empty:
            return {"total": 0, "crbt": 0, "ordinaire": 0, "ca": 0.0, "taux": None, "avg_intervalle": None}
        total    = len(df)
        crbt_col = next((c for c in df.columns if norm(c) == norm("CRBT/ORD")), None)
        ca_col   = next((c for c in df.columns if norm(c) == "ca"), None)
        de_col   = next((c for c in df.columns if norm(c) == norm("Dernier E")), None)
        itv_col  = next((c for c in df.columns if norm(c) == norm("Intervalle en jours")), None)
        crbt      = int((df[crbt_col].str.strip().str.upper() == "CRBT").sum()) if crbt_col else 0
        ordinaire = total - crbt
        ca        = round(float(pd.to_numeric(df[ca_col], errors="coerce").fillna(0).sum()), 2) if ca_col else 0.0
        taux      = None
        if de_col and total > 0:
            livres = int(df[de_col].dropna().str.strip().str.lower().str.startswith("envoi liv").sum())
            taux   = round(livres / total * 100, 1)
        avg_intervalle = None
        if itv_col:
            try:
                vals = pd.to_numeric(df[itv_col], errors="coerce").dropna()
                avg_intervalle = round(float(vals.mean()), 1) if len(vals) > 0 else None
            except Exception:
                pass
        return {"total": total, "crbt": crbt, "ordinaire": ordinaire,
                "ca": ca, "taux": taux, "avg_intervalle": avg_intervalle}

    reg_col_nat = next((c for c in (nat_df.columns if nat_df is not None else [])
                        if norm(c) == norm("Region Depot")), None)
    reg_col_exp = next((c for c in (export_df.columns if export_df is not None else [])
                        if norm(c) == norm("Region Depot")), None)

    nat_fdf = nat_df[nat_df[reg_col_nat].str.strip() == region].copy() \
              if (nat_df is not None and reg_col_nat) else nat_df
    exp_fdf = export_df[export_df[reg_col_exp].str.strip() == region].copy() \
              if (export_df is not None and reg_col_exp) else export_df

    nat_k = _kpis_for(nat_fdf)
    exp_k = _kpis_for(exp_fdf)

    gtotal     = nat_k["total"]    + exp_k["total"]
    gcrbt      = nat_k["crbt"]     + exp_k["crbt"]
    gordinaire = nat_k["ordinaire"] + exp_k["ordinaire"]
    gca        = round(nat_k["ca"] + exp_k["ca"], 2)
    gtaux      = None
    if gtotal > 0:
        nat_livres = round(nat_k["taux"] / 100 * nat_k["total"]) if nat_k["taux"] is not None else 0
        exp_livres = round(exp_k["taux"] / 100 * exp_k["total"]) if exp_k["taux"] is not None else 0
        gtaux = round((nat_livres + exp_livres) / gtotal * 100, 1)

    return {
        "national": nat_k,
        "export":   exp_k,
        "global":   {"total": gtotal, "crbt": gcrbt, "ordinaire": gordinaire,
                     "ca": gca, "taux": gtaux, "avg_intervalle": None},
    }


def compute_livraison_kpis(nat_df, import_df, region):
    """KPIs livraison ventilés : national / import / global.
    Filtre par Region Dernier E == region pour chaque source."""
    def _kpis_for(df):
        if df is None or df.empty:
            return {"total": 0, "crbt": 0, "ordinaire": 0, "ca": 0.0, "taux": None, "avg_intervalle": None}
        reg_de_col = next((c for c in df.columns if norm(c) == norm("Region dernier E")), None)
        fdf = df[df[reg_de_col].str.strip() == region].copy() if reg_de_col else df.copy()
        if fdf.empty:
            return {"total": 0, "crbt": 0, "ordinaire": 0, "ca": 0.0, "taux": None, "avg_intervalle": None}
        total    = len(fdf)
        crbt_col = next((c for c in fdf.columns if norm(c) == norm("CRBT/ORD")), None)
        ca_col   = next((c for c in fdf.columns if norm(c) == "ca"), None)
        de_col   = next((c for c in fdf.columns if norm(c) == norm("Dernier E")), None)
        itv_col  = next((c for c in fdf.columns if norm(c) == norm("Intervalle en jours")), None)
        crbt      = int((fdf[crbt_col].str.strip().str.upper() == "CRBT").sum()) if crbt_col else 0
        ordinaire = total - crbt
        ca        = round(float(pd.to_numeric(fdf[ca_col], errors="coerce").fillna(0).sum()), 2) if ca_col else 0.0
        taux      = None
        if de_col and total > 0:
            livres = int(fdf[de_col].dropna().str.strip().str.lower().str.startswith("envoi liv").sum())
            taux   = round(livres / total * 100, 1)
        avg_intervalle = None
        if itv_col:
            try:
                vals = pd.to_numeric(fdf[itv_col], errors="coerce").dropna()
                avg_intervalle = round(float(vals.mean()), 1) if len(vals) > 0 else None
            except Exception:
                pass
        return {"total": total, "crbt": crbt, "ordinaire": ordinaire,
                "ca": ca, "taux": taux, "avg_intervalle": avg_intervalle}

    nat_k = _kpis_for(nat_df)
    imp_k = _kpis_for(import_df)

    gtotal     = nat_k["total"]     + imp_k["total"]
    gcrbt      = nat_k["crbt"]      + imp_k["crbt"]
    gordinaire = nat_k["ordinaire"] + imp_k["ordinaire"]
    gca        = round(nat_k["ca"]  + imp_k["ca"], 2)
    gtaux      = None
    if gtotal > 0:
        nat_livres = round((nat_k["taux"] or 0) / 100 * nat_k["total"])
        imp_livres = round((imp_k["taux"] or 0) / 100 * imp_k["total"])
        gtaux = round((nat_livres + imp_livres) / gtotal * 100, 1)

    return {
        "national": nat_k,
        "import":   imp_k,
        "global":   {"total": gtotal, "crbt": gcrbt, "ordinaire": gordinaire,
                     "ca": gca, "taux": gtaux, "avg_intervalle": None},
    }


def get_cat_cols(fdf, mx=60):
    return {c: set(fdf[c].str.strip()) for c in fdf.columns if 0 < fdf[c].nunique() <= mx}


def cell_matches(row, col_h, cat_cols):
    for xc, vals in cat_cols.items():
        if col_h in vals and str(row[xc]).strip() == col_h:
            return True
    cc = next((c for c in cat_cols if norm(c) == "crbt"), None)
    if norm(col_h) == "crbt" and cc:
        try: return float(str(row[cc]).replace(",", "") or "0") > 0
        except Exception: pass
    if norm(col_h) == "ordinaire" and cc:
        try: return float(str(row[cc]).replace(",", "") or "0") == 0
        except Exception: pass
    return False


def find_col_for_values(df, selected_values, max_unique=50):
    real_vals = [v for v in selected_values if v.lower().strip() not in cfg._BLANK_TOKENS]
    if not real_vals:
        return None
    candidates = []
    for col in df.columns:
        unique = set(df[col].str.strip())
        if len(unique) <= max_unique and all(v in unique for v in real_vals):
            candidates.append((len(unique), col))
    if candidates:
        candidates.sort()
        return candidates[0][1]
    return None


def extract_measure_base(h):
    for p in ['sum of ', 'average of ', 'avg of ', 'max of ', 'min of ']:
        if h.lower().startswith(p):
            return h[len(p):]
    return None


def get_detail_cols(headers, df):
    result, seen = [], set()
    for h in headers:
        if 'COUNT' in h.upper() and 'MAILITM' in h.upper():
            continue
        base = extract_measure_base(h)
        if base is None:
            base = h
        xlsx_col = next((c for c in df.columns if norm(c) == norm(base)), None)
        if xlsx_col and norm(base) not in seen:
            result.append((base, xlsx_col)); seen.add(norm(base))
    for extra in cfg._NATIONAL_EXTRA_COLS:
        if norm(extra) not in seen:
            xlsx_col = next((c for c in df.columns if norm(c) == norm(extra)), None)
            if xlsx_col:
                result.append((extra, xlsx_col)); seen.add(norm(extra))
    return result


def put_totals_last(rows):
    return [r for r in rows if all(c.strip() for c in r)] + \
           [r for r in rows if not all(c.strip() for c in r)]


def find_dim_col(headers):
    for i, h in enumerate(headers):
        if not any(kw in h.upper() for kw in ['SUM', 'COUNT', 'AVG', 'AVERAGE', 'MAX', 'MIN']):
            return i
    return None


def has_mailitm_count(headers):
    if any('COUNT' in h.upper() and 'MAILITM' in h.upper() for h in headers):
        return True
    dim_idx = find_dim_col(headers)
    return (dim_idx is not None and
            any(norm(headers[dim_idx]) == norm(d) for d in cfg._NATIONAL_DIMS))


def is_mailitm_table(headers):
    return len(headers) == 1 and 'MAILITM' in headers[0].upper()


def is_depot_table(headers):
    return any(norm(h) == norm("Bureau depot") for h in headers)


def is_livraison_table(headers):
    return any(norm(h) == norm("Region dernier E") for h in headers)
