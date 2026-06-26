"""Table builders + drill-through mapping builders (national, export, import)."""
import pandas as pd

from . import config as cfg
from . import pbi_api
from .data_loaders import (
    norm, xlsx_filter, get_cat_cols, cell_matches, get_detail_cols,
    find_dim_col, has_mailitm_count, is_depot_table, is_livraison_table,
    put_totals_last,
)


# ── National drill-through (PBI DAX) ─────────────────────────────────────────

def build_national_drill_dax(token, dataset_id, tbl_name, table_meta, slicer_filters, fdf, log=print):
    """Exact 2D drill for national tables via DAX (includes column dimension)."""
    filters_str = (",\n    " + ",\n    ".join(slicer_filters)) if slicer_filters else ""
    de_col_xlsx = next((c for c in fdf.columns if norm(c) == norm("Dernier E")), None)
    de_vals = set(fdf[de_col_xlsx].str.strip()) if de_col_xlsx else set()
    mappings = {}

    for meta in table_meta:
        if not has_mailitm_count(meta["headers"]):
            continue
        dim_idx = find_dim_col(meta["headers"])
        if dim_idx is None:
            continue
        dim_col = meta["headers"][dim_idx]
        non_dim = [h for i, h in enumerate(meta["headers"])
                   if i != dim_idx and "total" not in h.lower()]
        is_categorical = bool(de_vals and any(h in de_vals for h in non_dim))
        is_crbt = any(norm(h) == "crbt" for h in non_dim)

        if is_categorical:
            dax = (
                f"EVALUATE CALCULATETABLE(\n"
                f"    SELECTCOLUMNS(\n"
                f"        '{tbl_name}',\n"
                f"        \"DimVal\", '{tbl_name}'[{dim_col}],\n"
                f"        \"ColVal\", '{tbl_name}'[Dernier E],\n"
                f"        \"poids\",  '{tbl_name}'[poids],\n"
                f"        \"CA\",     '{tbl_name}'[CA],\n"
                f"        \"ID\",     '{tbl_name}'[MAILITM_FID]\n"
                f"    ){filters_str}\n"
                f")"
            )
        elif is_crbt:
            dax = (
                f"EVALUATE CALCULATETABLE(\n"
                f"    SELECTCOLUMNS(\n"
                f"        '{tbl_name}',\n"
                f"        \"DimVal\", '{tbl_name}'[{dim_col}],\n"
                f"        \"CRBT\",   '{tbl_name}'[CRBT],\n"
                f"        \"poids\",  '{tbl_name}'[poids],\n"
                f"        \"CA\",     '{tbl_name}'[CA],\n"
                f"        \"ID\",     '{tbl_name}'[MAILITM_FID]\n"
                f"    ){filters_str}\n"
                f")"
            )
        else:
            continue

        rows = pbi_api.run_dax(token, dataset_id, dax, log=log)
        if rows is None:
            log(f"  ❌ DAX failed for national '{meta['key']}'")
            return {}

        flat_map, seen_all, seen_col = {}, {}, {}
        for row in rows:
            dv = str(row.get("[DimVal]") or row.get("DimVal") or "").strip()
            id_ = str(row.get("[ID]") or row.get("ID") or "").strip()
            pwd = str(row.get("[poids]") or row.get("poids") or "")
            if not (dv and id_):
                continue

            ca_v = str(row.get("[CA]") or row.get("CA") or "")
            if is_categorical:
                cv = str(row.get("[ColVal]") or row.get("ColVal") or "").strip()
                entry = {"id": id_, "poids": pwd, "CA": ca_v, "Dernier E": cv}
            else:
                try:
                    crbt_v = float(str(row.get("[CRBT]") or row.get("CRBT") or "0")
                                   .replace(",", ".").replace(" ", "") or "0")
                except Exception:
                    crbt_v = 0
                cv = "CRBT" if crbt_v > 0 else "Ordinaire"
                entry = {"id": id_, "poids": pwd, "CA": ca_v}

            if id_ not in seen_all.setdefault(dv, set()):
                seen_all[dv].add(id_)
                flat_map.setdefault(dv, {"__all__": []})["__all__"].append(entry)
            if cv and id_ not in seen_col.setdefault((dv, cv), set()):
                seen_col[(dv, cv)].add(id_)
                flat_map[dv].setdefault(cv, []).append(entry)

        total = sum(len(v["__all__"]) for v in flat_map.values())
        cols = ["poids", "CA", "Dernier E"] if is_categorical else ["poids", "CA"]
        log(f"  ↳ DAX national '{meta['key']}': {len(flat_map)} dims, {total} IDs")
        mappings[meta["key"]] = {
            "cols": cols, "dim_idx": dim_idx,
            "headers": meta["headers"], "data": flat_map
        }
    return mappings


def build_drill_mappings(token, dataset_id, tables, table_meta, slicers, df, log=print):
    tbl_name = pbi_api.find_pbi_table(token, dataset_id, log=log) if token and dataset_id else None
    slicers = pbi_api.fix_slicer_titles(slicers, df, token, dataset_id, tbl_name, log=log)

    # ── Apply slicer filters to xlsx ──────────────────────────────────────────
    fdf = df.copy()
    for s in slicers:
        if not s["title"] or not s["selected"]:
            continue
        col = next((c for c in fdf.columns if norm(c) == norm(s["title"])), None)
        if col:
            before = len(fdf)
            fdf = xlsx_filter(fdf, col, s["selected"])
            log(f"  ↳ xlsx filter: [{col}] = {s['selected']} → {len(fdf)} rows (was {before})")
        else:
            log(f"  ⚠ [{s['title']}] not in xlsx — skipped")

    if "MAILITM_FID" in fdf.columns:
        valid_ids = set(fdf["MAILITM_FID"].str.strip())
    else:
        valid_ids = None

    # ── Build DAX slicer filters list ─────────────────────────────────────────
    slicer_filters = []
    if tbl_name:
        for s in slicers:
            if not s["title"] or not s["selected"]:
                continue
            if not s.get("dax_filterable", True):
                continue
            real_vals = [v for v in s["selected"] if v.lower().strip() not in cfg._BLANK_TOKENS]
            if not real_vals:
                continue
            vals, col = real_vals, s["title"]
            if len(vals) == 1:
                slicer_filters.append(f"'{tbl_name}'[{col}] = \"{vals[0]}\"")
            else:
                slicer_filters.append(
                    f"'{tbl_name}'[{col}] IN {{{', '.join(chr(34) + v + chr(34) for v in vals)}}}")
            log(f"  ↳ DAX filter: [{col}] = {vals}")

    # ── Detect national context ───────────────────────────────────────────────
    national_ctx = any(
        any(norm(h) == norm(d) for h in meta["headers"] for d in cfg._NATIONAL_DIMS)
        for meta in table_meta
    )

    # ── National: dedicated DAX with column dimension (exact IDs) ────────────
    if tbl_name and national_ctx:
        nat = build_national_drill_dax(token, dataset_id, tbl_name, table_meta, slicer_filters, fdf, log=log)
        if nat:
            return nat

    # ── Non-national: existing row-level DAX ─────────────────────────────────
    if tbl_name and not national_ctx:
        mappings, all_ok = {}, True
        for meta, t in zip(table_meta, tables):
            if not has_mailitm_count(meta["headers"]):
                continue
            dim_idx = find_dim_col(meta["headers"])
            if dim_idx is None:
                continue
            dim_col = meta["headers"][dim_idx]
            detail_cols = get_detail_cols(meta["headers"], fdf)
            log(f"\n  ↳ DAX query '{meta['key']}' (dim: [{dim_col}], detail: {[b for b, _ in detail_cols]})...")
            filters_str = ((",\n    " + ",\n    ".join(slicer_filters)) if slicer_filters else "")
            dax = (
                f"EVALUATE\nCALCULATETABLE(\n"
                f"    SELECTCOLUMNS(\n"
                f"        '{tbl_name}',\n"
                f"        \"DimVal\", '{tbl_name}'[{dim_col}],\n"
                f"        \"ID\",     '{tbl_name}'[MAILITM_FID]\n"
                f"    ){filters_str}\n)"
            )
            rows = pbi_api.run_dax(token, dataset_id, dax, log=log)
            if rows is None:
                all_ok = False; break

            lookup = {}
            for _, xrow in fdf.iterrows():
                xid = str(xrow["MAILITM_FID"]).strip()
                if xid and xid not in lookup:
                    entry = {b: str(xrow[xc]).strip() for b, xc in detail_cols}
                    lookup[xid] = entry

            flat_map, skipped, seen_per_dv = {}, 0, {}
            for row in rows:
                dv = row.get("[DimVal]") or row.get("DimVal") or ""
                id_ = row.get("[ID]") or row.get("ID") or ""
                if not (dv and id_):
                    continue
                if valid_ids is not None and id_ not in valid_ids:
                    skipped += 1; continue
                if id_ in seen_per_dv.setdefault(dv, set()):
                    continue
                seen_per_dv[dv].add(id_)
                flat_map.setdefault(dv, []).append(
                    {"id": id_, **lookup.get(id_, {b: "" for b, _ in detail_cols})})

            total = sum(len(v) for v in flat_map.values())
            note = f" ({skipped} post-filtered)" if skipped else ""
            log(f"    ✓ {len(flat_map)} dim vals, {total} unique IDs{note}")
            mappings[meta["key"]] = {"cols": [b for b, _ in detail_cols], "data": flat_map}

        if all_ok and mappings:
            return mappings

    # ── xlsx fallback (national 2D cell_matches) ──────────────────────────────
    log("\n  ↳ Using xlsx fallback (2D cell_matches)...")
    mappings = {}
    cat_cols = get_cat_cols(fdf)
    for meta, t in zip(table_meta, tables):
        if not has_mailitm_count(meta["headers"]):
            continue
        dim_idx = find_dim_col(meta["headers"])
        if dim_idx is None:
            continue
        disp = meta["headers"][dim_idx]
        col = next((c for c in fdf.columns if norm(c) == norm(disp)), None)
        if not col:
            log(f"  Warning: '{disp}' not found in xlsx"); continue
        detail_cols = get_detail_cols(meta["headers"], fdf)
        non_dim_hdrs = [h for i, h in enumerate(meta["headers"])
                        if i != dim_idx and "total" not in h.lower()]
        flat_map, seen_all, seen_cell = {}, {}, {}
        for _, row in fdf.iterrows():
            dv = str(row[col]).strip()
            id_ = str(row["MAILITM_FID"]).strip()
            if not (dv and id_):
                continue
            entry = {"id": id_, **{b: str(row[xc]).strip() for b, xc in detail_cols}}
            if id_ not in seen_all.setdefault(dv, set()):
                seen_all[dv].add(id_)
                flat_map.setdefault(dv, {"__all__": []})["__all__"].append(entry)
            for col_h in non_dim_hdrs:
                if cell_matches(row, col_h, cat_cols):
                    if id_ not in seen_cell.setdefault((dv, col_h), set()):
                        seen_cell[(dv, col_h)].add(id_)
                        flat_map[dv].setdefault(col_h, []).append(entry)
        total = sum(len(v["__all__"]) for v in flat_map.values())
        cols_list = [b for b, _ in detail_cols]
        log(f"  ↳ '{meta['key']}': {len(flat_map)} dims, {total} IDs")
        mappings[meta["key"]] = {
            "cols": cols_list, "headers": meta["headers"],
            "dim_idx": dim_idx, "data": flat_map}
    return mappings


# ── National tables built purely from xlsx (Plan B / no PBI) ────────────────

def build_tables_from_xlsx(fdf, table_meta_template):
    """Build national tables (Bureau depot, Region dernier E, ...) purely from xlsx."""
    tables = []
    de_col = next((c for c in fdf.columns if norm(c) == norm("Dernier E")), None)
    crbt_col = next((c for c in fdf.columns if norm(c) == "crbt"), None)

    for meta in table_meta_template:
        headers = meta["headers"]
        dim_idx = find_dim_col(headers)
        if dim_idx is None:
            tables.append({"title": meta.get("title", ""), "headers": headers,
                            "rows": [], "num_rows": 0, "num_cols": len(headers)})
            continue
        dim_col_name = headers[dim_idx]
        xlsx_dim = next((c for c in fdf.columns if norm(c) == norm(dim_col_name)), None)
        if not xlsx_dim:
            tables.append({"title": meta.get("title", ""), "headers": headers,
                            "rows": [], "num_rows": 0, "num_cols": len(headers)})
            continue

        non_dim_hdrs = [h for i, h in enumerate(headers)
                        if i != dim_idx and "total" not in h.lower()]
        is_categorical = de_col and any(h in set(fdf[de_col].str.strip().unique())
                                         for h in non_dim_hdrs)
        dim_vals = sorted([v for v in fdf[xlsx_dim].unique() if str(v).strip()])
        col_totals = [0] * len(headers)
        rows_out = []
        for dv in dim_vals:
            sub = fdf[fdf[xlsx_dim] == dv]
            row = [''] * len(headers)
            row[dim_idx] = str(dv)
            for ci, h in enumerate(headers):
                if ci == dim_idx:
                    continue
                h_norm = h.lower()
                if "total" in h_norm:
                    cnt = len(sub); row[ci] = str(cnt) if cnt else ''; col_totals[ci] += cnt
                elif is_categorical and de_col and h in set(fdf[de_col].str.strip().unique()):
                    cnt = int((sub[de_col].str.strip() == h).sum()); row[ci] = str(cnt) if cnt else ''; col_totals[ci] += cnt
                elif crbt_col and h_norm in ("crbt",):
                    vals = pd.to_numeric(sub[crbt_col], errors="coerce").fillna(0)
                    cnt = int((vals > 0).sum()); row[ci] = str(cnt) if cnt else ''; col_totals[ci] += cnt
                elif crbt_col and h_norm in ("ordinaire",):
                    vals = pd.to_numeric(sub[crbt_col], errors="coerce").fillna(0)
                    cnt = int((vals == 0).sum()); row[ci] = str(cnt) if cnt else ''; col_totals[ci] += cnt
            rows_out.append(row)
        tot_row = [''] * len(headers)
        for ci, tot in enumerate(col_totals):
            if tot:
                tot_row[ci] = str(tot)
        rows_out.append(tot_row)
        tables.append({"title": meta.get("title", ""), "headers": headers,
                        "rows": rows_out, "num_rows": len(rows_out), "num_cols": len(headers)})
    return tables


# Standard table templates used when no PBI template is available (pure xlsx mode)
NATIONAL_TABLE_TEMPLATES = [
    {"key": "t0", "idx": -1, "headers": ["Bureau depot", "CRBT", "Ordinaire", "Total"], "title": ""},
    {"key": "t1", "idx": -1, "headers": ["Region dernier E", "Envoi Livré", "Total"], "title": ""},
]


def build_national_tables_xlsx(fdf, table_meta_template=None):
    """Standalone helper: build national tables from xlsx, auto-detecting the
    'Region dernier E' table's event columns (Dernier E unique values)."""
    de_col = next((c for c in fdf.columns if norm(c) == norm("Dernier E")), None)
    de_vals = sorted(set(v for v in fdf[de_col].str.strip().unique() if v)) if de_col else []

    if table_meta_template:
        tpl = table_meta_template
    else:
        livraison_headers = ["Region dernier E"] + de_vals + ["Total"]
        tpl = [
            {"key": "t0", "idx": -1, "headers": ["Bureau depot", "CRBT", "Ordinaire", "Total"], "title": ""},
            {"key": "t1", "idx": -1, "headers": livraison_headers, "title": ""},
        ]
    return build_tables_from_xlsx(fdf, tpl)


# ── KPI table builders (new format) ──────────────────────────────────────────

def _bureau_category(name):
    """Détermine la catégorie d'un bureau dépôt à partir de son nom."""
    n = str(name).lower()
    if "agence" in n:
        return "agences"
    if "centre" in n or "cdc" in n:
        return "centres"
    return "bureaux"


def build_depot_kpi_table(df, region, col_keys=None, cat_filter=None):
    """Tableau Dépôt KPI : Bureau dépôt × CRBT × CA × Nb IDs.
    Nb IDs = total colis du bureau (CRBT + Ordinaire) = somme de la ligne.
    TOTAL row = somme de chaque colonne."""
    reg_col  = next((c for c in df.columns if norm(c) == norm("Region Depot")), None)
    bur_col  = next((c for c in df.columns if norm(c) == norm("Bureau depot")), None)
    crbt_col = next((c for c in df.columns if norm(c) == norm("CRBT/ORD")), None)
    ca_col   = next((c for c in df.columns if norm(c) == "ca"), None)

    headers = ["Bureau dépôt", "CRBT", "CA", "Nb IDs"]
    empty = {"title": "", "headers": headers, "rows": [], "num_rows": 0, "num_cols": len(headers)}
    if not bur_col:
        return empty

    fdf = df[df[reg_col].str.strip() == region].copy() if reg_col else df.copy()
    if fdf.empty:
        return empty

    active_cats = set(cat_filter) if cat_filter else None
    bureaux = put_totals_last(sorted(fdf[bur_col].dropna().str.strip().unique()))
    rows = []
    tot_crbt = 0
    tot_ca   = 0.0
    tot_ids  = 0

    for b in bureaux:
        if active_cats and _bureau_category(b) not in active_cats:
            continue
        sub     = fdf[fdf[bur_col].str.strip() == b]
        nb_crbt = int((sub[crbt_col].str.strip().str.upper() == "CRBT").sum()) if crbt_col else 0
        ca_val  = float(pd.to_numeric(sub[ca_col], errors="coerce").fillna(0).sum()) if ca_col else 0.0
        nb_ids  = len(sub)
        tot_crbt += nb_crbt
        tot_ca   += ca_val
        tot_ids  += nb_ids
        rows.append([b,
                     str(nb_crbt) if nb_crbt else "",
                     f"{ca_val:,.0f}"  if ca_val  else "",
                     str(nb_ids)])

    # Ligne TOTAL : somme de chaque colonne
    rows.append(["TOTAL", str(tot_crbt), f"{tot_ca:,.0f}", str(tot_ids)])

    return {"title": "", "headers": headers, "rows": rows,
            "num_rows": len(rows), "num_cols": len(headers)}


def build_livraison_pivot_table(df, region, cat_filter=None):
    """Tableau Livraison pivot : Bureau Dernier E × valeurs Dernier E + Total + CRBT + Ordinaire + CA.
    Filtré par Region Dernier E == region (pas Region Depot).
    cat_filter: liste de catégories actives (agences/bureaux/centres) ou None = toutes."""
    reg_de_col  = next((c for c in df.columns if norm(c) == norm("Region dernier E")),   None)
    bur_de_col  = next((c for c in df.columns if norm(c) == norm("Bureau dernier E")),   None)
    de_col      = next((c for c in df.columns if norm(c) == norm("Dernier E")),          None)
    crbt_col    = next((c for c in df.columns if norm(c) == norm("CRBT/ORD")),           None)
    ca_col      = next((c for c in df.columns if norm(c) == "ca"),                       None)

    fdf = df[df[reg_de_col].str.strip() == region].copy() if reg_de_col else df.copy()
    empty = {"title": "", "headers": [], "rows": [], "num_rows": 0, "num_cols": 0}
    if fdf.empty or not bur_de_col:
        return empty

    active_cats = set(cat_filter) if cat_filter else None

    # Distinct Dernier E values — "Envoi Livré" first
    if de_col:
        all_de  = sorted(fdf[de_col].str.strip().unique())
        envoi   = [v for v in all_de if str(v).lower().startswith("envoi liv")]
        rest    = [v for v in all_de if v not in envoi and v]
        de_vals = envoi + rest
    else:
        de_vals = []

    headers   = ["Bureau Dernier E"] + de_vals + ["Total IDs", "CRBT", "Ordinaire", "CA (DT)"]
    bureaux   = sorted(fdf[bur_de_col].str.strip().unique())
    rows      = []
    tot_by_de = {v: 0 for v in de_vals}
    tot_ids = tot_crbt = tot_ord = 0
    tot_ca  = 0.0

    for bur in bureaux:
        if active_cats and _bureau_category(bur) not in active_cats:
            continue
        sub    = fdf[fdf[bur_de_col].str.strip() == bur]
        nb_ids = len(sub)
        crbt   = int((sub[crbt_col].str.strip().str.upper() == "CRBT").sum()) if crbt_col else 0
        ord_   = nb_ids - crbt
        ca     = float(pd.to_numeric(sub[ca_col], errors="coerce").fillna(0).sum()) if ca_col else 0.0
        ca_s   = f"{ca:,.0f}".replace(",", " ")
        tot_ids += nb_ids; tot_crbt += crbt; tot_ord += ord_; tot_ca += ca

        row = [bur]
        if de_col:
            vc = sub[de_col].str.strip().value_counts()
            for v in de_vals:
                c = int(vc.get(v, 0))
                tot_by_de[v] += c
                row.append(str(c) if c else "—")
        row += [str(nb_ids), str(crbt), str(ord_), ca_s]
        rows.append(row)

    tot_row = ["TOTAL"]
    for v in de_vals:
        tot_row.append(str(tot_by_de[v]) if tot_by_de[v] else "—")
    tot_row += [str(tot_ids), str(tot_crbt), str(tot_ord),
                f"{tot_ca:,.0f}".replace(",", " ")]
    rows.append(tot_row)

    return {"title": "", "headers": headers, "rows": rows,
            "num_rows": len(rows), "num_cols": len(headers)}


def build_livraison_pivot_drill(df, region, tbl_key, cat_filter=None):
    """Drill mapping for livraison pivot : dim_idx=0 (Bureau Dernier E).
    Filtré par Region Dernier E == region.
    Sous-clés = valeurs Dernier E + 'CRBT' + 'Ordinaire'."""
    reg_de_col  = next((c for c in df.columns if norm(c) == norm("Region dernier E")),    None)
    bur_de_col  = next((c for c in df.columns if norm(c) == norm("Bureau dernier E")),    None)
    de_col      = next((c for c in df.columns if norm(c) == norm("Dernier E")),           None)
    crbt_col    = next((c for c in df.columns if norm(c) == norm("CRBT/ORD")),            None)
    ca_col      = next((c for c in df.columns if norm(c) == "ca"),                        None)
    intv_col    = next((c for c in df.columns if norm(c) == norm("Intervalle en jours")), None)
    id_col      = next((c for c in df.columns if "mailitm" in norm(c)),                   None)

    if not (bur_de_col and id_col):
        return {}

    fdf = df[df[reg_de_col].str.strip() == region].copy() if reg_de_col else df.copy()
    active_cats = set(cat_filter) if cat_filter else None

    if de_col:
        all_de  = sorted(fdf[de_col].str.strip().unique())
        envoi   = [v for v in all_de if str(v).lower().startswith("envoi liv")]
        rest    = [v for v in all_de if v not in envoi and v]
        de_vals = envoi + rest
    else:
        de_vals = []

    headers  = ["Bureau Dernier E"] + de_vals + ["Total IDs", "CRBT", "Ordinaire", "CA (DT)"]
    flat_map = {}

    for _, row in fdf.iterrows():
        bur_de   = str(row[bur_de_col]).strip()
        id_      = str(row[id_col]).strip()
        if not (bur_de and id_):
            continue
        if active_cats and _bureau_category(bur_de) not in active_cats:
            continue
        de_val   = str(row[de_col]).strip()           if de_col   else ""
        crbt_ord = str(row[crbt_col]).strip().upper() if crbt_col else ""
        ca_v     = str(row[ca_col]).strip()           if ca_col   else ""
        intv_v   = str(row[intv_col]).strip()         if intv_col else ""
        entry = {"id": id_, "Dernier E": de_val, "Type": crbt_ord.capitalize(),
                 "CA": ca_v, "Intervalle (j)": intv_v}

        bkt = flat_map.setdefault(bur_de, {"__all__": []})
        bkt["__all__"].append(entry)
        if de_val:
            bkt.setdefault(de_val, []).append(entry)
        if crbt_ord == "CRBT":
            bkt.setdefault("CRBT", []).append(entry)
        else:
            bkt.setdefault("Ordinaire", []).append(entry)

    return {tbl_key: {
        "cols": ["Dernier E", "Type", "CA", "Intervalle (j)"],
        "dim_idx": 0,
        "headers": headers,
        "data": flat_map,
    }}


def collect_livraison_slider_data(df, region, cat_filter=None):
    """Collect compact raw records for the livraison date-range slider embedded in the HTML report.
    Returns list of {b, d, e, t, c} dicts (bureau, date YYYY-MM-DD, dernier_e, CRBT/ORD, ca)."""
    reg_de_col  = next((c for c in df.columns if norm(c) == norm("Region dernier E")), None)
    bur_de_col  = next((c for c in df.columns if norm(c) == norm("Bureau dernier E")), None)
    date_de_col = next((c for c in df.columns if norm(c) == norm("Date dernier E")), None)
    de_col      = next((c for c in df.columns if norm(c) == norm("Dernier E")), None)
    crbt_col    = next((c for c in df.columns if norm(c) == norm("CRBT/ORD")), None)
    ca_col      = next((c for c in df.columns if norm(c) == "ca"), None)

    if not bur_de_col:
        return []

    fdf = df[df[reg_de_col].str.strip() == region].copy() if reg_de_col else df.copy()
    active_cats = set(cat_filter) if cat_filter else None

    records = []
    for _, row in fdf.iterrows():
        bur_de = str(row[bur_de_col]).strip() if pd.notna(row[bur_de_col]) else ""
        if not bur_de:
            continue
        if active_cats and _bureau_category(bur_de) not in active_cats:
            continue
        date_val = ""
        if date_de_col and pd.notna(row[date_de_col]):
            try:
                date_val = pd.Timestamp(row[date_de_col]).strftime("%Y-%m-%d")
            except Exception:
                pass
        de_val   = str(row[de_col]).strip()            if de_col   and pd.notna(row[de_col])   else ""
        crbt_ord = str(row[crbt_col]).strip().upper()  if crbt_col and pd.notna(row[crbt_col]) else ""
        ca_val   = 0.0
        if ca_col and pd.notna(row[ca_col]):
            try:
                ca_val = float(str(row[ca_col]).replace(",", ".").replace(" ", "") or "0")
            except Exception:
                ca_val = 0.0
        records.append({"b": bur_de, "d": date_val, "e": de_val,
                        "t": crbt_ord, "c": round(ca_val, 2)})
    return records


def build_livraison_kpi_table(df, region, col_keys=None):
    """Tableau Livraison KPI : Region DE × Bureau DE × Nb IDs × Taux × Intervalle.
    Nb IDs = count colis par (Region DE, Bureau DE) = somme de la ligne.
    TOTAL row = somme de chaque colonne."""
    from . import config as cfg
    active = set(col_keys) if col_keys is not None else set(cfg.LIVRAISON_COL_KEYS_DEFAULT)

    headers = ["Region Dernier E", "Bureau Dernier E", "Nb IDs"]
    if "taux_liv"   in active: headers.append("Taux livraison (%)")
    if "intervalle" in active: headers.append("Intervalle moyen (j)")

    reg_dep_col = next((c for c in df.columns if norm(c) == norm("Region Depot")),    None)
    reg_de_col  = next((c for c in df.columns if norm(c) == norm("Region dernier E")), None)
    bur_de_col  = next((c for c in df.columns if norm(c) == norm("Bureau dernier E")), None)
    de_col      = next((c for c in df.columns if norm(c) == norm("Dernier E")),        None)
    intv_col    = next((c for c in df.columns if norm(c) == norm("Intervalle en jours")), None)

    empty = {"title": "", "headers": headers, "rows": [], "num_rows": 0, "num_cols": len(headers)}
    if not (reg_de_col and bur_de_col):
        return empty

    fdf = df[df[reg_dep_col].str.strip() == region].copy() if reg_dep_col else df.copy()
    if fdf.empty:
        return empty

    groups = fdf.groupby([reg_de_col, bur_de_col], sort=True)
    rows = []
    tot_count = tot_livres = 0
    all_intv = []

    for (reg_de, bur_de), sub in groups:
        reg_de = str(reg_de).strip(); bur_de = str(bur_de).strip()
        if not (reg_de and bur_de):
            continue
        count = len(sub)           # Nb IDs = somme de la ligne
        tot_count += count

        n_livres = 0
        if de_col:
            de_vals  = sub[de_col].dropna().str.strip()
            n_livres = int(de_vals.str.lower().str.startswith("livr").sum())
        tot_livres += n_livres
        taux = round(n_livres / count * 100, 1) if count > 0 else 0.0

        avg_intv = None
        if intv_col:
            intv_vals = pd.to_numeric(sub[intv_col], errors="coerce").dropna()
            if not intv_vals.empty:
                avg_intv = round(float(intv_vals.mean()), 1)
                all_intv.extend(intv_vals.tolist())

        row = [reg_de, bur_de, str(count)]
        if "taux_liv"   in active: row.append(f"{taux}%")
        if "intervalle" in active: row.append(str(avg_intv) if avg_intv is not None else "")
        rows.append(row)

    # Ligne TOTAL : somme de chaque colonne
    taux_global = round(tot_livres / tot_count * 100, 1) if tot_count > 0 else 0.0
    avg_global  = round(sum(all_intv) / len(all_intv), 1) if all_intv else None
    tot_row = ["TOTAL", "", str(tot_count)]
    if "taux_liv"   in active: tot_row.append(f"{taux_global}%")
    if "intervalle" in active: tot_row.append(str(avg_global) if avg_global is not None else "")
    rows.append(tot_row)

    return {"title": "", "headers": headers, "rows": rows,
            "num_rows": len(rows), "num_cols": len(headers)}


# ── Drill mappings pour les nouvelles tables KPI ─────────────────────────────

def build_depot_kpi_drill(df, region, col_keys, tbl_key, cat_filter=None):
    """Drill mapping aligné sur build_depot_kpi_table (Bureau dépôt × CRBT × CA).
    dim_idx=0; sous-clé 'CRBT' = IDs CRBT uniquement."""
    reg_col  = next((c for c in df.columns if norm(c) == norm("Region Depot")), None)
    bur_col  = next((c for c in df.columns if norm(c) == norm("Bureau depot")), None)
    crbt_col = next((c for c in df.columns if norm(c) == norm("CRBT/ORD")), None)
    ca_col   = next((c for c in df.columns if norm(c) == "ca"), None)
    id_col   = next((c for c in df.columns if "mailitm" in norm(c)), None)

    if not (bur_col and id_col):
        return {}

    fdf = df[df[reg_col].str.strip() == region].copy() if reg_col else df.copy()
    active_cats = set(cat_filter) if cat_filter else None
    headers = ["Bureau dépôt", "CRBT", "CA", "Nb IDs"]

    flat_map = {}
    for _, row in fdf.iterrows():
        bureau = str(row[bur_col]).strip()
        id_    = str(row[id_col]).strip()
        if not (bureau and id_):
            continue
        if active_cats and _bureau_category(bureau) not in active_cats:
            continue
        ca_v     = str(row[ca_col]).strip() if ca_col else ""
        crbt_ord = str(row[crbt_col]).strip().upper() if crbt_col else ""
        entry    = {"id": id_, "CA": ca_v, "Type": crbt_ord.capitalize()}

        bkt = flat_map.setdefault(bureau, {"__all__": []})
        bkt["__all__"].append(entry)
        if crbt_ord == "CRBT":
            bkt.setdefault("CRBT", []).append(entry)

    return {tbl_key: {"cols": ["CA", "Type"], "dim_idx": 0, "headers": headers, "data": flat_map}}


def build_livraison_kpi_drill(df, region, col_keys, tbl_key):
    """Drill mapping aligné sur build_livraison_kpi_table.
    dim_idx=1 (Bureau Dernier E); sous-clé 'Taux livraison (%)' = IDs livrés."""
    from . import config as cfg
    active = set(col_keys) if col_keys is not None else set(cfg.LIVRAISON_COL_KEYS_DEFAULT)

    reg_dep_col = next((c for c in df.columns if norm(c) == norm("Region Depot")), None)
    reg_de_col  = next((c for c in df.columns if norm(c) == norm("Region dernier E")), None)
    bur_de_col  = next((c for c in df.columns if norm(c) == norm("Bureau dernier E")), None)
    de_col      = next((c for c in df.columns if norm(c) == norm("Dernier E")), None)
    intv_col    = next((c for c in df.columns if norm(c) == norm("Intervalle en jours")), None)
    id_col      = next((c for c in df.columns if "mailitm" in norm(c)), None)

    if not (bur_de_col and id_col):
        return {}

    fdf = df[df[reg_dep_col].str.strip() == region].copy() if reg_dep_col else df.copy()

    headers = ["Region Dernier E", "Bureau Dernier E", "Nb IDs"]
    if "taux_liv"   in active: headers.append("Taux livraison (%)")
    if "intervalle" in active: headers.append("Intervalle moyen (j)")

    flat_map = {}
    for _, row in fdf.iterrows():
        bur_de = str(row[bur_de_col]).strip()
        id_    = str(row[id_col]).strip()
        if not (bur_de and id_):
            continue
        de_val   = str(row[de_col]).strip()   if de_col   else ""
        intv_val = str(row[intv_col]).strip() if intv_col else ""
        entry = {"id": id_, "Dernier E": de_val, "Intervalle (j)": intv_val}

        bkt = flat_map.setdefault(bur_de, {"__all__": []})
        bkt["__all__"].append(entry)
        bkt.setdefault("Intervalle moyen (j)", []).append(entry)

        if de_val.lower().startswith("livr"):
            bkt.setdefault("Taux livraison (%)", []).append(entry)

    return {tbl_key: {"cols": ["Dernier E", "Intervalle (j)"], "dim_idx": 1,
                      "headers": headers, "data": flat_map}}


# ── Export & Import table builders ───────────────────────────────────────────

def build_depot_export_table(export_df, region):
    """Table DÉPÔT EXPORT: Bureau depot × CRBT|Ordinaire|Total (from export sheet)."""
    headers = ["Bureau depot", "CRBT", "Ordinaire", "Total"]
    fdf = export_df[export_df["Region Depot"].str.strip() == region].copy()
    if fdf.empty:
        return {"title": "Export", "headers": headers,
                "rows": [], "num_rows": 0, "num_cols": len(headers)}
    bureaux = sorted(fdf["Bureau depot"].str.strip().unique())
    rows = []
    tot_crbt = tot_ord = tot_all = 0
    for b in bureaux:
        sub = fdf[fdf["Bureau depot"].str.strip() == b]
        crbt_n = int((sub["CRBT/ORD"].str.strip() == "CRBT").sum())
        ord_n = int((sub["CRBT/ORD"].str.strip() == "Ordinaire").sum())
        tot = crbt_n + ord_n
        tot_crbt += crbt_n; tot_ord += ord_n; tot_all += tot
        rows.append([b,
                     str(crbt_n) if crbt_n else "",
                     str(ord_n) if ord_n else "",
                     str(tot) if tot else ""])
    rows.append(["", str(tot_crbt), str(tot_ord), str(tot_all)])
    return {"title": "Export", "headers": headers,
            "rows": rows, "num_rows": len(rows), "num_cols": len(headers)}


def build_livraison_import_table(import_df, region, events):
    """Table LIVRAISON IMPORT: Bureau dernier E × events|Total (from import.xls)."""
    headers = ["Bureau dernier E"] + events + ["Total"]
    fdf = import_df[import_df["Region dernier E"].str.strip() == region].copy()
    if fdf.empty:
        return {"title": "Import", "headers": headers,
                "rows": [], "num_rows": 0, "num_cols": len(headers)}
    bureaux = sorted(fdf["Bureau dernier E"].str.strip().unique())
    rows = []
    col_totals = [0] * len(headers)
    for b in bureaux:
        sub = fdf[fdf["Bureau dernier E"].str.strip() == b]
        row = [b]
        for j, evt in enumerate(events):
            cnt = int((sub["Dernier E"].str.strip() == evt).sum())
            row.append(str(cnt) if cnt else "")
            col_totals[j + 1] += cnt
        tot = len(sub)
        row.append(str(tot))
        col_totals[-1] += tot
        rows.append(row)
    tot_row = ([""] +
               [str(col_totals[j + 1]) if col_totals[j + 1] else "" for j in range(len(events))] +
               [str(col_totals[-1])])
    rows.append(tot_row)
    return {"title": "Import", "headers": headers,
            "rows": rows, "num_rows": len(rows), "num_cols": len(headers)}


# ── Drill mapping builders for xlsx-based tables (export/import) ────────────

def build_export_drill(export_df, region, tbl_key):
    """Drill mapping for export table: Bureau depot → MAILITM_FIDs with CA/CRBT split."""
    fdf = export_df[export_df["Region Depot"].str.strip() == region]
    flat_map = {}
    for _, row in fdf.iterrows():
        bureau = str(row.get("Bureau depot", "")).strip()
        id_ = str(row.get("MAILITM_FID", "")).strip()
        if not (bureau and id_):
            continue
        crbt_ord = str(row.get("CRBT/ORD", "")).strip()
        ca_v = str(row.get("CA", "")).strip()
        entry = {"id": id_, "poids": str(row.get("poids", "")).strip(), "CA": ca_v}
        bkt = flat_map.setdefault(bureau, {"__all__": []})
        bkt["__all__"].append(entry)
        if crbt_ord in ("CRBT", "Ordinaire"):
            bkt.setdefault(crbt_ord, []).append(entry)
    return {tbl_key: {"cols": ["poids", "CA"], "dim_idx": 0,
                      "headers": ["Bureau depot", "CRBT", "Ordinaire", "Total"],
                      "data": flat_map}}


def build_import_drill(import_df, region, events, tbl_key):
    """Drill mapping for import table: Bureau dernier E → MAILITM_FIDs per event."""
    fdf = import_df[import_df["Region dernier E"].str.strip() == region]
    flat_map = {}
    for _, row in fdf.iterrows():
        bureau = str(row.get("Bureau dernier E", "")).strip()
        id_ = str(row.get("MAILITM_FID", "")).strip()
        if not (bureau and id_):
            continue
        evt = str(row.get("Dernier E", "")).strip()
        entry = {"id": id_, "poids": str(row.get("poids", "")).strip()}
        bkt = flat_map.setdefault(bureau, {"__all__": []})
        bkt["__all__"].append(entry)
        if evt:
            bkt.setdefault(evt, []).append(entry)
    headers = ["Bureau dernier E"] + events + ["Total"]
    return {tbl_key: {"cols": ["poids"], "dim_idx": 0,
                      "headers": headers, "data": flat_map}}
