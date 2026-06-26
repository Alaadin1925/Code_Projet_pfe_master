"""Power BI REST API helpers (executeQueries / schema discovery). No Playwright dependency."""
import requests as req_lib

from . import config as cfg
from .data_loaders import norm, has_blank_selection, find_col_for_values

_schema_cache = {}


def reset_schema_cache():
    _schema_cache.clear()


def pbi_get(token, path):
    return req_lib.get(f"{cfg.API_BASE}{path}",
                        headers={"Authorization": f"Bearer {token}"}).json()


def get_dataset_id(token, log=print):
    for path in [f"/reports/{cfg.REPORT_ID}", f"/groups/me/reports/{cfg.REPORT_ID}"]:
        data = pbi_get(token, path)
        if "datasetId" in data:
            log(f"  ↳ Dataset ID: {data['datasetId']}")
            return data["datasetId"]
    return None


def run_dax(token, dataset_id, dax, silent=False, log=print):
    resp = req_lib.post(
        f"{cfg.API_BASE}/datasets/{dataset_id}/executeQueries",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}}
    )
    data = resp.json()
    if "error" in data:
        if not silent:
            log(f"  ❌ DAX error: {data.get('error', {}).get('code', '')}")
        return None
    try:
        return data["results"][0]["tables"][0].get("rows", [])
    except (KeyError, IndexError):
        return []


def find_pbi_table(token, dataset_id, log=print):
    cache = _schema_cache.setdefault(dataset_id, {})
    if "tbl" in cache:
        return cache["tbl"]
    rows = run_dax(token, dataset_id,
                    "EVALUATE SELECTCOLUMNS(INFO.TABLES(), \"n\", [Name])", silent=True)
    if rows:
        skip = {"dateautotable", "localdatetable"}
        candidates = [r.get("[n]") or r.get("n") or "" for r in rows]
        candidates = [n for n in candidates
                       if n and not n.startswith("$") and n.lower() not in skip]
        for name in candidates:
            if run_dax(token, dataset_id,
                       f"EVALUATE SELECTCOLUMNS(TOPN(1,'{name}'),\"x\","
                       f"'{name}'[MAILITM_FID])", silent=True) is not None:
                log(f"  ↳ Power BI table auto-discovered: '{name}'")
                cache["tbl"] = name
                return name
    for name in ["export", "Export", "dépôt2026_nettoyé"]:
        if run_dax(token, dataset_id, f"EVALUATE TOPN(1,'{name}')", silent=True) is not None:
            log(f"  ↳ Power BI table (fallback): '{name}'")
            cache["tbl"] = name
            return name
    return None


def get_pbi_columns(token, dataset_id, tbl_name):
    cache = _schema_cache.setdefault(dataset_id, {})
    key = f"cols_{tbl_name}"
    if key in cache:
        return cache[key]
    rows = run_dax(token, dataset_id,
                    f"EVALUATE SELECTCOLUMNS("
                    f"FILTER(INFO.COLUMNS(), [TableName] = \"{tbl_name}\"),"
                    f"\"c\", [ExplicitName])", silent=True)
    cols = [r.get("[c]") or r.get("c") or "" for r in (rows or [])]
    cols = [c for c in cols if c]
    cache[key] = cols
    return cols


def is_dax_filterable(token, dataset_id, tbl_name, col):
    return run_dax(token, dataset_id,
                    f"EVALUATE SELECTCOLUMNS(TOPN(1,'{tbl_name}'),\"t\","
                    f"'{tbl_name}'[{col}])", silent=True) is not None


def auto_resolve_slicer_dax(token, dataset_id, tbl_name, selected_values):
    if not (token and dataset_id and tbl_name):
        return None, None
    all_cols = get_pbi_columns(token, dataset_id, tbl_name)
    if not all_cols:
        return None, None
    SKIP_KW = ('ID', 'FID', 'NUM', 'DATE', 'TIME', 'AMOUNT', 'QTY',
               'COUNT', 'SUM', 'AVG', 'YEAR', 'MONTH', 'WEEK')
    candidates = [c for c in all_cols
                   if not any(k in c.upper() for k in SKIP_KW)][:20]
    real_vals = [v for v in selected_values if v.lower().strip() not in cfg._BLANK_TOKENS]
    if not real_vals:
        return None, None
    val_list = ", ".join(f'"{v}"' for v in real_vals)
    n_vals = len(set(real_vals))
    for col in candidates:
        try:
            rows = run_dax(token, dataset_id,
                            f"EVALUATE FILTER(VALUES('{tbl_name}'[{col}]),"
                            f"'{tbl_name}'[{col}] IN {{{val_list}}})", silent=True)
            if rows is not None and len(rows) >= n_vals:
                return col, is_dax_filterable(token, dataset_id, tbl_name, col)
        except Exception:
            continue
    return None, None


def fix_slicer_titles(slicers, df, token=None, dataset_id=None, tbl_name=None, log=print):
    BAD = {"clear selections", "clear selection", ""}
    for s in slicers:
        raw = s["title"].lower().strip()
        if raw not in BAD and "clear" not in raw:
            if has_blank_selection(s.get("selected", [])):
                s["dax_filterable"] = True
            elif token and dataset_id and tbl_name:
                s["dax_filterable"] = is_dax_filterable(token, dataset_id, tbl_name, s["title"])
            else:
                s["dax_filterable"] = True
            continue
        # 1. Manual map
        for val in s["selected"]:
            if val in cfg.MANUAL_SLICER_MAP:
                s["title"] = cfg.MANUAL_SLICER_MAP[val]
                s["dax_filterable"] = True
                log(f"  ↳ Slicer resolved (manual map): '{s['title']}' ← {s['selected']}")
                break
        if s["title"] and s["title"].lower() not in BAD:
            continue
        # 2. Computed DAX columns
        sel_set = frozenset(s["selected"])
        for val_set, (col_name, _) in cfg._COMPUTED_COLS.items():
            if sel_set <= val_set:
                s["title"] = col_name
                s["dax_filterable"] = False
                log(f"  ↳ Slicer resolved (computed DAX col): '{col_name}' ← {s['selected']}")
                break
        if s["title"] and s["title"].lower() not in BAD:
            continue
        # 3. DAX auto-discovery
        if token and dataset_id and tbl_name:
            col, filterable = auto_resolve_slicer_dax(token, dataset_id, tbl_name, s["selected"])
            if col:
                filterable = filterable and not has_blank_selection(s["selected"])
                s["title"] = col
                s["dax_filterable"] = filterable
                mode = "DAX+xlsx" if filterable else "xlsx only"
                log(f"  ↳ Slicer resolved (DAX auto, {mode}): '{col}' ← {s['selected']}")
                continue
        # 4. xlsx auto-detect
        col = find_col_for_values(df, s["selected"])
        if col:
            s["title"] = col
            s["dax_filterable"] = not has_blank_selection(s["selected"])
            log(f"  ↳ Slicer resolved (xlsx auto): '{col}' ← {s['selected']}")
            continue
        s["title"] = ""
        log(f"  ⚠ Slicer {s['selected']} unresolved — filter skipped")
    return slicers
