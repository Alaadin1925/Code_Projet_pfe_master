"""Playwright-based Power BI scraping + per-region report/email pipeline.

Primary path: live Power BI scraping via a persistent browser profile (SSO).
Fallback (Plan B): if Power BI navigation/session fails (e.g. expired license)
or any per-region PBI step raises, that region's national tables are rebuilt
purely from the xlsx files (`tables.build_tables_from_xlsx`). The job never
aborts because of a PBI failure — it always falls through to xlsx.
"""
import asyncio
import os
import sys
from datetime import datetime

import pandas as pd
from playwright.async_api import async_playwright

from . import config as cfg
from . import pbi_api
from .data_loaders import (
    norm, load_xlsx_df, load_export_df, load_import_df,
    compute_kpis, compute_depot_kpis, compute_livraison_kpis, xlsx_filter,
    is_mailitm_table, is_depot_table, is_livraison_table,
)
from .html_builder import build_interactive_html, get_logo_b64
from .mailer import send_region_email
from .tables import (
    build_drill_mappings, build_tables_from_xlsx,
    build_depot_kpi_table, build_livraison_kpi_table,
    build_livraison_pivot_table, build_livraison_pivot_drill,
    build_depot_kpi_drill, build_livraison_kpi_drill,
    build_export_drill, build_import_drill,
    collect_livraison_slider_data,
    put_totals_last,
)


# ── JS snippets (DOM scraping) ───────────────────────────────────────────────

JS_CLASSIFY = """() => {
    const c = Array.from(document.querySelectorAll('[data-testid="visual-container"]'));
    return c.map((v, i) => {
        const isTable = !!v.querySelector('[role="columnheader"]');
        const t = v.querySelector('[data-testid="unselectable sidePaneTitle"]')
               || v.querySelector('[class*="visualTitle"] span')
               || v.querySelector('[class*="title"] span');
        return { index: i, type: isTable ? 'table' : 'other',
                 title: t ? t.textContent.trim() : '' };
    });
}"""

JS_SLICERS_GLOBAL = r"""() => {
    const groups = new Map();
    let cbs = Array.from(document.querySelectorAll('[data-testid="slicerCheckbox selected"]'));
    if (!cbs.length)
        cbs = Array.from(document.querySelectorAll('[role="checkbox"][aria-checked="true"]'));
    for (const cb of cbs) {
        const cont = cb.closest('[class*="visualContainer"]')
                  || cb.closest('[class*="visual-container"]')
                  || cb.closest('[data-testid="visual-container"]');
        if (!cont) continue;
        if (!groups.has(cont)) {
            const titleEl =
                cont.querySelector('[data-testid="unselectable sidePaneTitle"]')
             || cont.querySelector('[class*="visualTitle"] span')
             || cont.querySelector('[class*="title"] span')
             || cont.querySelector('[class*="slicerHeader"] .slicer-header-text')
             || cont.querySelector('[class*="slicerHeader"]')
             || cont.querySelector('[aria-label]');
            let title = titleEl
                ? (titleEl.getAttribute('aria-label') || titleEl.textContent || '').trim()
                : '';
            title = title.replace(/clear\s+selections?/gi, '').trim();
            groups.set(cont, { title, selected: [] });
        }
        let text = cb.getAttribute('aria-label') || '';
        if (!text) {
            const row = cb.parentElement;
            const te  = row && row.querySelector('[data-testid="slicerText"]');
            text = te ? te.textContent.trim()
                      : (row ? row.textContent.trim() : cb.textContent.trim());
        }
        if (text === '') text = '(Blank)';
        groups.get(cont).selected.push(text);
    }
    return Array.from(groups.values())
        .filter(g => g.selected.length)
        .map(g => ({ title: g.title, selected: [...new Set(g.selected)] }));
}"""

JS_HEADERS = """(idx) => {
    const c = document.querySelectorAll('[data-testid="visual-container"]')[idx];
    return Array.from(c.querySelectorAll('[role="columnheader"]'))
        .map(el => el.textContent.trim()).filter(t => t && t !== 'Row Selection');
}"""

JS_VISIBLE_ROWS = """([idx, n]) => {
    const c = document.querySelectorAll('[data-testid="visual-container"]')[idx];
    const cells = Array.from(c.querySelectorAll('[role="gridcell"], [role="rowheader"]'))
        .map(el => el.textContent.trim()).filter(t => t !== 'Select Row' && t !== 'Row Selection');
    const rows = [];
    for (let i = 0; i + n <= cells.length; i += n) rows.push(cells.slice(i, i + n));
    return rows;
}"""

JS_SCROLL = """([idx, d]) => {
    const c = document.querySelectorAll('[data-testid="visual-container"]')[idx];
    let el = c.querySelector('[role="grid"]');
    if (!el || el.scrollHeight <= el.clientHeight + 5)
        el = Array.from(c.querySelectorAll('div')).find(d => {
            const s = window.getComputedStyle(d);
            return (s.overflowY==='auto'||s.overflowY==='scroll') && d.scrollHeight>d.clientHeight+5;
        });
    if (!el) return { done: true };
    el.scrollTop += d;
    return { done: el.scrollTop + el.clientHeight >= el.scrollHeight - 5 };
}"""

JS_RESET_SCROLL = """(idx) => {
    const c = document.querySelectorAll('[data-testid="visual-container"]')[idx];
    let el = c.querySelector('[role="grid"]');
    if (!el || el.scrollHeight <= el.clientHeight + 5)
        el = Array.from(c.querySelectorAll('div')).find(d => {
            const s = window.getComputedStyle(d);
            return (s.overflowY==='auto'||s.overflowY==='scroll') && d.scrollHeight>d.clientHeight+5;
        });
    if (el) el.scrollTop = 0;
}"""

JS_FIND_REGION_SLICER = """(regionNames) => {
    const root = document.body;

    function matchesRegionSlicer(el) {
        const texts1 = Array.from(el.querySelectorAll('[data-testid="slicerText"]'))
            .map(e => e.textContent.trim().toUpperCase());
        if (texts1.some(t => regionNames.includes(t))) return true;

        const leaves = Array.from(el.querySelectorAll('*')).filter(e =>
            e.children.length === 0 && regionNames.includes(e.textContent.trim().toUpperCase()));
        if (leaves.length > 0) return true;

        const ariaOk = Array.from(el.querySelectorAll('[aria-label]')).some(e =>
            regionNames.includes((e.getAttribute('aria-label') || '').trim().toUpperCase()));
        if (ariaOk) return true;

        const checked = Array.from(el.querySelectorAll('[aria-checked]'));
        for (const cb of checked) {
            const label = cb.getAttribute('aria-label') || cb.textContent || '';
            if (regionNames.includes(label.trim().toUpperCase())) return true;
        }
        return false;
    }

    const containers = Array.from(root.querySelectorAll('[data-testid="visual-container"]'));
    if (containers.length > 0) {
        for (let i = 0; i < containers.length; i++) {
            if (matchesRegionSlicer(containers[i])) return i;
        }
        return -1;
    }

    for (const sel of [
        '[data-element-type="visual"]',
        '.visual-container',
        '[class*="visual-container"]',
        '[class*="visualContainer"]',
    ]) {
        const cs = Array.from(root.querySelectorAll(sel));
        if (cs.length > 0) {
            for (let i = 0; i < cs.length; i++) {
                if (matchesRegionSlicer(cs[i])) return i;
            }
        }
    }
    return -1;
}"""

JS_CLEAR_SLICER = """(idx) => {
    const c = Array.from(document.querySelectorAll('[data-testid="visual-container"]'))[idx];
    if (!c) return false;
    const btn = c.querySelector('[aria-label="Clear selections"]')
             || c.querySelector('[aria-label="Effacer les sélections"]')
             || c.querySelector('[title="Clear selections"]')
             || Array.from(c.querySelectorAll('button,[role="button"]')).find(b =>
                    (b.getAttribute('aria-label')||b.title||'').toLowerCase().includes('clear') ||
                    (b.getAttribute('aria-label')||b.title||'').toLowerCase().includes('effacer'));
    if (btn) { btn.click(); return true; }
    return false;
}"""

JS_SLICER_SCROLL_TOP = """(idx) => {
    const c = Array.from(document.querySelectorAll('[data-testid="visual-container"]'))[idx];
    if (!c) return;
    const el = Array.from(c.querySelectorAll('div')).find(d => {
        const s = window.getComputedStyle(d);
        return (s.overflowY==='auto'||s.overflowY==='scroll') && d.scrollHeight>d.clientHeight+5;
    });
    if (el) el.scrollTop = 0;
}"""

JS_TRY_SELECT_IN_SLICER = """([idx, value]) => {
    const c = Array.from(document.querySelectorAll('[data-testid="visual-container"]'))[idx];
    if (!c) return false;
    const upper = value.toUpperCase();
    for (const item of c.querySelectorAll('[data-testid="slicerText"]')) {
        if (item.textContent.trim().toUpperCase() === upper) {
            const row = item.closest('[role="option"]')
                     || item.closest('[class*="row"]')
                     || item.parentElement;
            if (row) { row.click(); return true; }
            item.click(); return true;
        }
    }
    for (const el of c.querySelectorAll('*')) {
        if (el.children.length === 0 && el.textContent.trim().toUpperCase() === upper) {
            const row = el.closest('[role="option"]') || el.closest('[role="listitem"]')
                     || el.closest('[class*="row"]') || el.parentElement;
            if (row) { row.click(); return true; }
            el.click(); return true;
        }
    }
    for (const el of c.querySelectorAll('[aria-label]')) {
        if ((el.getAttribute('aria-label')||'').trim().toUpperCase() === upper) {
            el.click(); return true;
        }
    }
    return false;
}"""

JS_SCROLL_SLICER = """([idx, amount]) => {
    const c = Array.from(document.querySelectorAll('[data-testid="visual-container"]'))[idx];
    if (!c) return { done: true };
    const el = Array.from(c.querySelectorAll('div')).find(d => {
        const s = window.getComputedStyle(d);
        return (s.overflowY==='auto'||s.overflowY==='scroll') && d.scrollHeight>d.clientHeight+5;
    });
    if (!el) return { done: true };
    el.scrollTop += amount;
    return { done: el.scrollTop + el.clientHeight >= el.scrollHeight - 5 };
}"""

JS_DUMP_CONTAINERS = """() => {
    const cs = Array.from(document.querySelectorAll('[data-testid="visual-container"]'));
    return cs.map((c, i) => ({
        idx: i,
        slicerTexts: Array.from(c.querySelectorAll('[data-testid="slicerText"]'))
                         .map(e => e.textContent.trim()).slice(0, 5),
        leafTexts: Array.from(c.querySelectorAll('*'))
                       .filter(e => e.children.length === 0 && e.textContent.trim().length > 0
                                 && e.textContent.trim().length < 40)
                       .map(e => e.textContent.trim()).slice(0, 5),
        ariaLabels: Array.from(c.querySelectorAll('[aria-label]'))
                        .map(e => e.getAttribute('aria-label')).slice(0, 3),
    }));
}"""


# ── DOM extraction helpers ────────────────────────────────────────────────────

async def extract_all_rows(page, idx, num_cols):
    all_rows, seen = [], set()
    await page.evaluate(JS_RESET_SCROLL, idx)
    await page.wait_for_timeout(400)
    while True:
        rows = await page.evaluate(JS_VISIBLE_ROWS, [idx, num_cols])
        nf = False
        for row in rows:
            k = "|||".join(row)
            if k not in seen:
                seen.add(k); all_rows.append(row); nf = True
        result = await page.evaluate(JS_SCROLL, [idx, 120])
        await page.wait_for_timeout(300)
        if result.get("done"):
            for row in await page.evaluate(JS_VISIBLE_ROWS, [idx, num_cols]):
                k = "|||".join(row)
                if k not in seen:
                    seen.add(k); all_rows.append(row)
            break
        if not nf:
            break
    return put_totals_last(all_rows)


async def set_region_slicer(page, slicer_idx, region, log=print):
    cleared = await page.evaluate(JS_CLEAR_SLICER, slicer_idx)
    if not cleared:
        log(f"    ⚠ Clear slicer failed — trying anyway")
    await page.wait_for_timeout(700)
    await page.evaluate(JS_SLICER_SCROLL_TOP, slicer_idx)
    await page.wait_for_timeout(200)
    for _ in range(40):
        if await page.evaluate(JS_TRY_SELECT_IN_SLICER, [slicer_idx, region]):
            return True
        r = await page.evaluate(JS_SCROLL_SLICER, [slicer_idx, 60])
        await page.wait_for_timeout(80)
        if r.get("done"):
            break
    await page.evaluate(JS_SLICER_SCROLL_TOP, slicer_idx)
    await page.wait_for_timeout(200)
    return await page.evaluate(JS_TRY_SELECT_IN_SLICER, [slicer_idx, region])


def build_region_slicers(fixed_template, region):
    result = []
    has_region = False
    for s in fixed_template:
        sc = dict(s)
        if norm(sc.get("title", "")) == norm("Region Depot"):
            sc["selected"] = [region]
            sc["dax_filterable"] = True
            has_region = True
        result.append(sc)
    if not has_region:
        result.append({"title": "Region Depot", "selected": [region], "dax_filterable": True})
    return result


# ── Helpers ──────────────────────────────────────────────────────────────────

def _apply_region_next(df, region_next):
    """Filter df by Region Next selection. '(VIDE)' matches blank/empty values.
    Empty selection → no filter (return df unchanged)."""
    if not region_next:
        return df
    rn_col = next((c for c in df.columns if norm(c) == norm("Region Next")), None)
    if not rn_col:
        return df
    selected      = set(region_next)
    include_blank = "(VIDE)" in selected
    real_vals     = [v for v in selected if v != "(VIDE)"]
    mask_real     = df[rn_col].str.strip().isin(real_vals) if real_vals else False
    mask_blank    = df[rn_col].str.strip() == ""            if include_blank else False
    return df[mask_real | mask_blank]


# ── Main job entry point ──────────────────────────────────────────────────────

async def _run_regions_async(regions, region_emails, include_depot, include_livraison,
                               output_dir, col_depot=None, col_livraison=None,
                               cat_depot=None, cat_livraison=None, region_next=None, log=print):
    """Generate + send the report for each region. Returns (success_count, failed_list, files)."""
    os.makedirs(output_dir, exist_ok=True)
    has_logo = os.path.exists(cfg.LOGO_PATH)
    logo_b64 = get_logo_b64()
    files = []

    # ── Load data sources (xlsx/xls) — always needed for KPIs + xlsx fallback ──
    try:
        df = load_xlsx_df(log=log)
        log(f"✅ National xlsx chargé : {len(df)} lignes")
    except Exception as e:
        log(f"❌ National xlsx : {e}")
        return 0, list(regions), files

    try:
        export_df = load_export_df(log=log)
        log(f"✅ Export xlsx chargé  : {len(export_df)} lignes")
    except Exception as e:
        log(f"❌ Export xlsx : {e}")
        export_df = None

    try:
        import_df, import_events = load_import_df(log=log)
        log(f"✅ Import xls chargé   : {len(import_df)} lignes, {len(import_events)} événements")
    except Exception as e:
        log(f"❌ Import xls : {e}")
        import_df, import_events = None, []

    # ── Try to establish a live Power BI session (Plan A) ──────────────────────
    pbi_ready = False
    bearer_token = dataset_id = tbl_name = None
    fixed_slicers_template, table_meta_tpl = [], []
    slicer_idx = -1
    context = page = None
    playwright_cm = None

    try:
        playwright_cm = async_playwright()
        p = await playwright_cm.__aenter__()
        context = await p.chromium.launch_persistent_context(
            user_data_dir=cfg.PROFILE_DIR, headless=True,
            viewport={"width": 1920, "height": 1080}, device_scale_factor=2,
        )
        page = await context.new_page()

        token_holder = []
        def on_request(request):
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer ") and not token_holder:
                token_holder.append(auth[7:])
        page.on("request", on_request)

        await page.goto(cfg.REPORT_URL, timeout=60000)
        try:
            await page.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass

        if "app.powerbi.com" not in page.url:
            raise RuntimeError(f"Session Power BI expirée (url={page.url})")

        try:
            await page.wait_for_selector('[data-testid="visual-container"]', timeout=30000)
        except Exception:
            raise RuntimeError("Aucun visual Power BI chargé (timeout 30s)")

        await page.wait_for_timeout(2000)

        bearer_token = token_holder[0] if token_holder else None
        log(f"  {'✅ Bearer token capturé' if bearer_token else '⚠ Bearer token absent'}")

        dataset_id = pbi_api.get_dataset_id(bearer_token, log=log) if bearer_token else None
        tbl_name = pbi_api.find_pbi_table(bearer_token, dataset_id, log=log) if dataset_id else None
        log(f"  ↳ Dataset : {dataset_id} | Table : {tbl_name}")

        current_slicers = await page.evaluate(JS_SLICERS_GLOBAL)
        has_agences = any(cfg.FIXED_CATEGORY in s.get("selected", []) for s in current_slicers)
        if not has_agences:
            raise RuntimeError(f"'{cfg.FIXED_CATEGORY}' n'est pas coché dans Power BI (sélection manuelle requise)")
        log(f"  ✅ Filtre '{cfg.FIXED_CATEGORY}' confirmé")

        fixed_slicers_template = pbi_api.fix_slicer_titles(
            current_slicers, df, bearer_token, dataset_id, tbl_name, log=log)

        slicer_idx = await page.evaluate(JS_FIND_REGION_SLICER, cfg.REGION_NAMES_UPPER)
        if slicer_idx < 0:
            log("  ⚠ Slicer Region Depot introuvable — tables nationales via xlsx pour toutes les régions")

        visuals_init = await page.evaluate(JS_CLASSIFY)
        for v in visuals_init:
            if v["type"] != "table":
                continue
            hdrs = await page.evaluate(JS_HEADERS, v["index"])
            if not hdrs or is_mailitm_table(hdrs):
                continue
            table_meta_tpl.append({"key": f"t{len(table_meta_tpl)}",
                                    "idx": v["index"], "headers": hdrs,
                                    "title": v.get("title", "")})
        log(f"  ↳ {len(table_meta_tpl)} tableau(x) national template (PBI)")
        pbi_ready = True

    except Exception as e:
        log(f"  ⚠ Power BI indisponible ({e}) — mode xlsx (Plan B) pour toutes les régions")
        if context:
            try:
                await context.close()
            except Exception:
                pass
            context = page = None
        if playwright_cm:
            try:
                await playwright_cm.__aexit__(None, None, None)
            except Exception:
                pass
            playwright_cm = None

    if not pbi_ready:
        de_col = next((c for c in df.columns if norm(c) == norm("Dernier E")), None)
        de_vals = sorted(set(v for v in df[de_col].str.strip().unique() if v)) if de_col else []
        table_meta_tpl = [
            {"key": "t0", "idx": -1, "headers": ["Bureau depot", "CRBT", "Ordinaire", "Total"], "title": ""},
            {"key": "t1", "idx": -1, "headers": ["Region dernier E"] + de_vals + ["Total"], "title": ""},
        ]
        fixed_slicers_template = []

    success, failed = 0, []

    try:
        for region in regions:
            recipient = (region_emails.get(region) or "").strip() or cfg.DEFAULT_EMAIL
            log(f"\n{'='*60}\n── {region} → {recipient} ──")

            slicers_reg = build_region_slicers(fixed_slicers_template, region)

            fdf = df.copy()
            for s in slicers_reg:
                if not s.get("title") or not s.get("selected"):
                    continue
                col = next((c for c in fdf.columns if norm(c) == norm(s["title"])), None)
                if col:
                    fdf = xlsx_filter(fdf, col, s["selected"])
            fdf = _apply_region_next(fdf, region_next)
            if region_next:
                log(f"  ↳ Filtre Region Next : {region_next} → {len(fdf)} lignes")
            # df_rn = df filtered by Region Next only (no Region Depot) — for livraison
            df_rn = _apply_region_next(df.copy(), region_next)
            kpis            = compute_kpis(fdf)
            depot_kpis      = compute_depot_kpis(df, export_df, region)
            livraison_kpis  = compute_livraison_kpis(df_rn, import_df, region)
            log(f"  ↳ KPIs : taux={kpis['taux']}%, total={kpis.get('total_ids', kpis['total'])}, CA={kpis.get('total_ca')}")

            filename = None
            nat_tables, nat_meta = [], []

            # ── Per-region: try PBI, fall back to xlsx on ANY error ───────────
            try:
                if not pbi_ready:
                    raise RuntimeError("PBI non disponible")

                use_dom_for_this = False
                if slicer_idx >= 0:
                    ok = await set_region_slicer(page, slicer_idx, region, log=log)
                    if ok:
                        log(f"  ✅ Slicer → {region}")
                        await page.wait_for_timeout(5000)
                        use_dom_for_this = True
                    else:
                        log(f"  ⚠ Slicer '{region}' non sélectionné — tables xlsx")

                filename = os.path.join(output_dir, f"report_{region}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
                await page.screenshot(path=filename, full_page=False)

                if use_dom_for_this:
                    visuals = await page.evaluate(JS_CLASSIFY)
                    for v in visuals:
                        if v["type"] != "table":
                            continue
                        headers = await page.evaluate(JS_HEADERS, v["index"])
                        if not headers or is_mailitm_table(headers):
                            continue
                        rows = await extract_all_rows(page, v["index"], len(headers))
                        tkey = f"t{len(nat_tables)}"
                        nat_tables.append({"title": v["title"], "headers": headers,
                                            "rows": rows, "num_rows": len(rows), "num_cols": len(headers)})
                        nat_meta.append({"key": tkey, "idx": v["index"], "headers": headers})
                    log(f"  ↳ {len(nat_tables)} tableau(x) national extraits (PBI)")
                else:
                    nat_tables = build_tables_from_xlsx(fdf, table_meta_tpl)
                    nat_meta = [{"key": m["key"], "idx": m["idx"], "headers": m["headers"]} for m in table_meta_tpl]
                    log(f"  ↳ {len(nat_tables)} tableau(x) national construits (xlsx)")

                nat_drill = build_drill_mappings(
                    bearer_token, dataset_id, nat_tables, nat_meta, slicers_reg, df, log=log)

            except Exception as e:
                log(f"  ⚠ PBI a échoué pour {region} ({e}) — fallback xlsx")
                nat_tables = build_tables_from_xlsx(fdf, table_meta_tpl)
                nat_meta = [{"key": m["key"], "idx": m["idx"], "headers": m["headers"]} for m in table_meta_tpl]
                try:
                    nat_drill = build_drill_mappings(None, None, nat_tables, nat_meta, slicers_reg, df, log=log)
                except Exception:
                    nat_drill = {}

            nat_t1_drill_key, nat_t2_drill_key = None, None
            for key, dm in nat_drill.items():
                hdrs = dm.get("headers", []) if isinstance(dm, dict) else []
                if is_depot_table(hdrs):
                    nat_t1_drill_key = key
                elif is_livraison_table(hdrs):
                    nat_t2_drill_key = key

            # ── Build KPI tables (new format) from xlsx ────────────────────
            nat_depot_t = build_depot_kpi_table(fdf, region, col_depot, cat_filter=cat_depot)
            nat_depot_t["title"] = "National — Dépôt"
            nat_livraison_t = build_livraison_pivot_table(df_rn, region, cat_filter=cat_livraison)
            nat_livraison_t["title"] = "National — Livraison"
            liv_slider_data = collect_livraison_slider_data(df_rn, region, cat_filter=cat_livraison)

            if export_df is not None:
                export_t = build_depot_kpi_table(export_df, region, col_depot, cat_filter=cat_depot)
                export_t["title"] = "Export — Dépôt"
                export_drill = build_export_drill(export_df, region, "t1")
            else:
                export_t = {"title": "Export — Dépôt", "headers": ["Bureau dépôt"],
                             "rows": [], "num_rows": 0, "num_cols": 1}
                export_drill = {}

            if import_df is not None:
                import_t = build_livraison_pivot_table(import_df, region, cat_filter=cat_livraison)
                import_t["title"] = "Import — Livraison"
                import_drill = build_import_drill(import_df, region, import_events, "t3")
            else:
                import_t = {"title": "Import — Livraison", "headers": ["Region Dernier E", "Bureau Dernier E"],
                             "rows": [], "num_rows": 0, "num_cols": 2}
                import_drill = {}

            # ── Drill mappings alignés sur les nouvelles tables KPI ───────────
            nat_depot_drill   = build_depot_kpi_drill(fdf,       region, col_depot,     "t_nd", cat_filter=cat_depot)
            nat_liv_drill     = build_livraison_pivot_drill(df_rn, region, "t_nl", cat_filter=cat_livraison)
            exp_depot_drill   = build_depot_kpi_drill(export_df, region, col_depot,     "t_ed", cat_filter=cat_depot) \
                                if export_df is not None else {}
            imp_liv_drill     = build_livraison_pivot_drill(import_df, region, "t_il", cat_filter=cat_livraison) \
                                if import_df is not None else {}

            # ── Assemble selected sections only ────────────────────────────────
            all_tables, drill_mappings, section_labels = [], {}, {}
            idx = 0
            if include_depot:
                all_tables.append(nat_depot_t)
                section_labels[idx] = "DEPOT"
                drill_mappings[f"t{idx}"] = nat_depot_drill.get("t_nd", {})
                idx += 1
                all_tables.append(export_t)
                drill_mappings[f"t{idx}"] = exp_depot_drill.get("t_ed", {})
                idx += 1
            if include_livraison:
                all_tables.append(nat_livraison_t)
                section_labels[idx] = "LIVRAISON"
                drill_mappings[f"t{idx}"] = nat_liv_drill.get("t_nl", {})
                idx += 1
                all_tables.append(import_t)
                drill_mappings[f"t{idx}"] = imp_liv_drill.get("t_il", {})
                idx += 1

            for k, v in drill_mappings.items():
                data = v.get("data", {}) if isinstance(v, dict) else {}
                log(f"    [{k}] {len(data)} dim vals")

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            html_filename = os.path.join(
                output_dir, f"report_{region}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_interactif.html")
            with open(html_filename, "w", encoding="utf-8") as hf:
                hf.write(build_interactive_html(
                    slicers_reg, all_tables, drill_mappings, timestamp,
                    logo_b64, kpis, section_labels=section_labels,
                    depot_kpis=depot_kpis,
                    livraison_kpis=livraison_kpis,
                    liv_slider_data=liv_slider_data))
            log(f"  ✅ HTML : {html_filename}")
            files.append(html_filename)
            if filename:
                files.append(filename)

            try:
                send_region_email(filename, html_filename, slicers_reg,
                                  all_tables, timestamp, recipient, region,
                                  logo_b64, has_logo, kpis,
                                  section_labels=section_labels)
                log(f"  📧 Email envoyé → {recipient}")
                success += 1
            except Exception as e:
                log(f"  ❌ Échec envoi : {e}")
                failed.append(region)

    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if playwright_cm:
            try:
                await playwright_cm.__aexit__(None, None, None)
            except Exception:
                pass

    log(f"\n{'='*60}")
    log(f"✅ {success}/{len(regions)} emails envoyés")
    if failed:
        log(f"❌ Échecs : {failed}")
    return success, failed, files


def run_regions_job(regions, region_emails, include_depot=True, include_livraison=True,
                     output_dir=None, col_depot=None, col_livraison=None,
                     cat_depot=None, cat_livraison=None, region_next=None, log=print):
    """Synchronous entry point — runs the async pipeline in its own event loop."""
    output_dir = output_dir or cfg.REPORTS_DIR
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _run_regions_async(regions, region_emails, include_depot, include_livraison,
                               output_dir, col_depot=col_depot, col_livraison=col_livraison,
                               cat_depot=cat_depot, cat_livraison=cat_livraison,
                               region_next=region_next, log=log))
    finally:
        loop.close()


def build_preview(region, include_depot, include_livraison,
                  col_depot=None, col_livraison=None, cat_depot=None, cat_livraison=None, region_next=None):
    """Build tables for a single region from xlsx only (no PBI) — used by the /preview endpoint.
    Returns (tables, section_labels, table_sources)."""
    from .data_loaders import load_xlsx_df, load_export_df, load_import_df
    from .tables import build_depot_kpi_table, build_livraison_pivot_table

    tables, section_labels, table_sources = [], {}, []
    idx = 0

    try:
        df  = load_xlsx_df(log=lambda _: None)
        fdf = _apply_region_next(df.copy(), region_next)   # depot: Region Next only
        df_rn = fdf                                         # livraison also uses Region Next only
    except Exception:
        fdf = df_rn = None

    try:
        export_df = load_export_df(log=lambda _: None)
    except Exception:
        export_df = None

    try:
        import_df, _ = load_import_df(log=lambda _: None)
    except Exception:
        import_df = None

    if include_depot:
        if fdf is not None:
            t = build_depot_kpi_table(fdf, region, col_depot, cat_filter=cat_depot)
            t["title"] = "National — Dépôt"
            tables.append(t); section_labels[idx] = "DEPOT"
            table_sources.append({"source": "national", "table_type": "depot"})
            idx += 1
        if export_df is not None:
            t = build_depot_kpi_table(export_df, region, col_depot, cat_filter=cat_depot)
            t["title"] = "Export — Dépôt"
            tables.append(t)
            table_sources.append({"source": "export", "table_type": "depot"})
            idx += 1

    if include_livraison:
        if df_rn is not None:
            t = build_livraison_pivot_table(df_rn, region, cat_filter=cat_livraison)
            t["title"] = "National — Livraison"
            tables.append(t); section_labels[idx] = "LIVRAISON"
            table_sources.append({"source": "national", "table_type": "livraison"})
            idx += 1
        if import_df is not None:
            t = build_livraison_pivot_table(import_df, region, cat_filter=cat_livraison)
            t["title"] = "Import — Livraison"
            tables.append(t)
            table_sources.append({"source": "import", "table_type": "livraison"})
            idx += 1

    return tables, section_labels, table_sources
