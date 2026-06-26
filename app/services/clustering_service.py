"""Five clustering analyses on the national postal data, loaded from SQL Server.

Refactored from the original notebook/scraper logic to read clean English
columns from ``national_shipments`` (no Excel re-reads, no French-header guessing).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import cophenet
from scipy.cluster.hierarchy import linkage as sp_linkage
from scipy.spatial.distance import pdist
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import (calinski_harabasz_score, davies_bouldin_score,
                             silhouette_score)
from sklearn.preprocessing import StandardScaler

from ..repositories import shipment_repository as repo

COLORS = ["#2ecc71", "#f39c12", "#e74c3c", "#3498db", "#9b59b6"]
COLORS_LITE = ["#d5f5e3", "#fef9e7", "#fce4e4", "#d6eaf8", "#e8daef"]


# ── helpers ───────────────────────────────────────────────────────────────────

def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _scale(arr):
    sc = StandardScaler()
    return sc.fit_transform(arr), sc


def _kmeans(xs, k, seed=42):
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    return km.fit_predict(xs).tolist(), km


def _remap(labels, sort_values, ascending=False):
    tmp = pd.Series(labels, name="c")
    means = pd.Series(sort_values).groupby(tmp).mean().sort_values(ascending=ascending)
    mapping = {old: new for new, old in enumerate(means.index)}
    return [mapping[v] for v in labels]


def _eval_metrics(xs, labels):
    if len(set(labels) - {-1}) < 2:
        return {"silhouette": None, "davies_bouldin": None, "calinski_harabasz": None}
    out = {}
    for key, fn, nd in (("silhouette", silhouette_score, 4),
                        ("davies_bouldin", davies_bouldin_score, 4),
                        ("calinski_harabasz", calinski_harabasz_score, 2)):
        try:
            out[key] = round(float(fn(xs, labels)), nd)
        except Exception:
            out[key] = None
    return out


def _ok(**kw):
    return {"ok": True, "error": None, **kw}


def _err(msg):
    return {"ok": False, "error": msg, "n_clusters": 0, "n_samples": 0,
            "features_used": [], "metrics": {}, "rows": [],
            "cluster_labels": {}, "cluster_colors": {}, "cluster_colors_light": {}}


def _colors(k):
    return {i: COLORS[i % len(COLORS)] for i in range(k)}, \
           {i: COLORS_LITE[i % len(COLORS_LITE)] for i in range(k)}


# ── 1. Bureau / depot performance ─────────────────────────────────────────────

def cluster_bureau_performance(df, k=3):
    if "depot_office" not in df.columns:
        return _err("Colonne dépôt introuvable.")
    grp = df["depot_office"].astype(str).str.strip()
    agg = pd.DataFrame({"total_colis": grp.value_counts()})
    agg["taux_livraison"] = df["is_delivered"].astype(float).groupby(grp).mean() * 100
    agg["avg_intervalle"] = _num(df["interval_days"]).groupby(grp).mean()
    agg["total_ca"] = _num(df["revenue_ca"]).groupby(grp).sum()
    agg["taux_crbt"] = df["is_crbt"].astype(float).groupby(grp).mean() * 100

    agg = agg[agg["total_colis"] >= 5].reset_index().rename(columns={"index": "bureau", "depot_office": "bureau"})
    feat = [c for c in ["taux_livraison", "avg_intervalle", "total_colis", "total_ca", "taux_crbt"]
            if c in agg.columns]
    if len(feat) < 2 or len(agg) < k:
        return _err(f"Pas assez de bureaux ({len(agg)}).")

    xs, _ = _scale(agg[feat].fillna(agg[feat].median()).values)
    labels = _remap(_kmeans(xs, k)[0], agg["taux_livraison"].values, ascending=False)
    names = {0: "Performant", 1: "Standard", 2: "À améliorer", 3: "Critique"}
    return _assemble(agg, "bureau", feat, labels, k, xs, names)


# ── 2. Shipment profile (parcel-level) ────────────────────────────────────────

def cluster_shipment_profile(df, k=4, max_rows=10_000):
    sub = pd.DataFrame(index=df.index)
    fmap = {}
    sub["_itv"] = _num(df["interval_days"]); fmap["_itv"] = "Intervalle (j)"
    sub["_ca"] = _num(df["revenue_ca"]); fmap["_ca"] = "CA (DT)"
    sub["_poids"] = _num(df["weight_kg"]); fmap["_poids"] = "Poids"
    sub["_crbt"] = df["is_crbt"].astype(float); fmap["_crbt"] = "CRBT"
    sub["_del"] = df["is_delivered"].astype(float); fmap["_del"] = "Livré"

    cols = list(fmap)
    sub = sub[cols].dropna()
    if len(sub) < k:
        return _err("Pas assez de colis valides.")
    if len(sub) > max_rows:
        sub = sub.sample(max_rows, random_state=42)

    xs, _ = _scale(sub.values)
    labels = _remap(_kmeans(xs, k)[0], sub["_itv"].values, ascending=True)
    sub["cluster"] = labels
    names = {0: "Rapide & léger", 1: "Standard", 2: "Lent / problématique", 3: "Hors norme"}

    rows = []
    for ci in range(k):
        mask = sub["cluster"] == ci
        stat = {"name": names.get(ci, f"C{ci}"), "cluster": ci,
                "cluster_label": names.get(ci, f"C{ci}"), "n": int(mask.sum())}
        for fc, label in fmap.items():
            v = sub.loc[mask, fc].mean()
            stat[label] = round(float(v), 2) if pd.notnull(v) else None
        rows.append(stat)

    cc, ccl = _colors(k)
    return _ok(n_clusters=k, n_samples=len(sub), features_used=list(fmap.values()),
               metrics=_eval_metrics(xs, labels), rows=rows,
               cluster_labels={i: names.get(i, f"C{i}") for i in range(k)},
               cluster_colors=cc, cluster_colors_light=ccl)


# ── 3. Region demand (hierarchical) ───────────────────────────────────────────

def cluster_region_demand(df, k=3):
    if "depot_region" not in df.columns:
        return _err("Colonne région introuvable.")
    grp = df["depot_region"].astype(str).str.strip()
    agg = pd.DataFrame({"total_colis": grp.value_counts()})
    agg["taux_livraison"] = df["is_delivered"].astype(float).groupby(grp).mean() * 100
    agg["avg_ca"] = _num(df["revenue_ca"]).groupby(grp).mean()
    agg["taux_crbt"] = df["is_crbt"].astype(float).groupby(grp).mean() * 100
    agg["avg_intervalle"] = _num(df["interval_days"]).groupby(grp).mean()

    agg = agg.dropna(how="all").reset_index().rename(columns={"index": "region", "depot_region": "region"})
    agg = agg[agg["region"].astype(str).str.strip() != ""].reset_index(drop=True)
    feat = [c for c in ["total_colis", "taux_livraison", "avg_ca", "taux_crbt", "avg_intervalle"]
            if c in agg.columns]
    if len(feat) < 2 or len(agg) < k:
        return _err(f"Pas assez de régions ({len(agg)}).")

    xs, _ = _scale(agg[feat].fillna(agg[feat].median()).values)
    raw = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(xs).tolist()
    labels = _remap(raw, agg["total_colis"].values, ascending=False)

    metrics = _eval_metrics(xs, labels)
    try:
        z = sp_linkage(xs, method="ward")
        metrics["cophenetic"] = round(float(cophenet(z, pdist(xs))[0]), 4)
    except Exception:
        pass
    names = {0: "Forte demande", 1: "Demande moyenne", 2: "Faible demande"}
    return _assemble(agg, "region", feat, labels, k, xs, names, metrics=metrics,
                     sort_key=lambda x: (x["cluster"], -(x.get("total_colis") or 0)))


# ── 4. Temporal patterns ──────────────────────────────────────────────────────

def cluster_temporal_patterns(df, k=3):
    if "deposit_date" not in df.columns:
        return _err("Aucune colonne de date.")
    sub = df.copy()
    sub["_date"] = pd.to_datetime(sub["deposit_date"], errors="coerce")
    sub = sub.dropna(subset=["_date"])
    if sub.empty:
        return _err("Aucune date valide.")
    sub["_day"] = sub["_date"].dt.date
    sub["_dow"] = sub["_date"].dt.dayofweek.astype(float)

    agg = pd.DataFrame({
        "daily_volume": sub.groupby("_day").size(),
        "day_of_week": sub.groupby("_day")["_dow"].first(),
        "daily_taux_liv": sub["is_delivered"].astype(float).groupby(sub["_day"]).mean() * 100,
        "daily_ca": _num(sub["revenue_ca"]).groupby(sub["_day"]).sum(),
    }).dropna(how="all").reset_index().rename(columns={"_day": "date"})

    feat = [c for c in ["daily_volume", "daily_taux_liv", "daily_ca", "day_of_week"]
            if c in agg.columns]
    if len(feat) < 2 or len(agg) < k:
        return _err(f"Pas assez de jours ({len(agg)}).")

    xs, _ = _scale(agg[feat].fillna(agg[feat].median()).values)
    labels = _remap(_kmeans(xs, k)[0], agg["daily_volume"].values, ascending=False)
    names = {0: "Jour de pointe", 1: "Jour normal", 2: "Jour creux"}
    agg["date"] = agg["date"].astype(str)
    return _assemble(agg, "date", feat, labels, k, xs, names)


# ── 5. Vehicle sizing by region ───────────────────────────────────────────────

def cluster_vehicle_sizing(df, k=3):
    if "depot_region" not in df.columns:
        return _err("Colonne région introuvable.")
    grp = df["depot_region"].astype(str).str.strip()
    agg = pd.DataFrame({"total_colis": grp.value_counts()})
    agg["nb_bureaux"] = df.groupby(grp)["depot_office"].nunique()
    agg["densite_colis"] = agg["total_colis"] / agg["nb_bureaux"].replace(0, np.nan)
    p = _num(df["weight_kg"])
    agg["total_poids"] = p.groupby(grp).sum()
    agg["avg_poids"] = p.groupby(grp).mean()
    agg["taux_crbt"] = df["is_crbt"].astype(float).groupby(grp).mean() * 100

    agg = agg.dropna(how="all").reset_index().rename(columns={"index": "region", "depot_region": "region"})
    agg = agg[agg["region"].astype(str).str.strip() != ""].reset_index(drop=True)
    feat = [c for c in ["total_colis", "total_poids", "avg_poids", "nb_bureaux", "densite_colis", "taux_crbt"]
            if c in agg.columns]
    if len(feat) < 2 or len(agg) < k:
        return _err(f"Pas assez de données ({len(agg)} régions).")

    xs, _ = _scale(agg[feat].fillna(agg[feat].median()).values)
    labels = _remap(_kmeans(xs, k)[0], agg["total_poids"].values, ascending=False)
    names = {0: "Camion", 1: "Fourgon", 2: "Voiture légère"}
    colors = {0: COLORS[2], 1: COLORS[1], 2: COLORS[0]}
    colors_lite = {0: COLORS_LITE[2], 1: COLORS_LITE[1], 2: COLORS_LITE[0]}
    return _assemble(agg, "region", feat, labels, k, xs, names,
                     colors=colors, colors_lite=colors_lite)


# ── assembly helper ───────────────────────────────────────────────────────────

def _assemble(agg, name_col, feat, labels, k, xs, names,
              metrics=None, sort_key=None, colors=None, colors_lite=None):
    agg = agg.copy()
    agg["cluster"] = labels
    rows = []
    for _, r in agg.iterrows():
        ci = int(r["cluster"])
        row = {"name": str(r.get(name_col, "")), "cluster": ci,
               "cluster_label": names.get(ci, f"C{ci}")}
        for c in feat:
            row[c] = round(float(r[c]), 2) if pd.notnull(r[c]) else None
        rows.append(row)
    rows.sort(key=sort_key or (lambda x: (x["cluster"], x["name"])))

    if colors is None:
        colors, colors_lite = _colors(k)
    return _ok(n_clusters=k, n_samples=len(agg), features_used=feat,
               metrics=metrics or _eval_metrics(xs, labels), rows=rows,
               cluster_labels={i: names.get(i, f"C{i}") for i in range(k) if i in names or True},
               cluster_colors=colors, cluster_colors_light=colors_lite)


# ── public entry point ────────────────────────────────────────────────────────

def run_all() -> dict:
    """Load national data from SQL and run all five analyses."""
    df = repo.fetch_dataframe()
    if df.empty:
        empty = _err("Aucune donnée nationale importée.")
        return {k: empty for k in ("bureau_perf", "shipment", "region_demand", "temporal", "vehicle")}
    return {
        "bureau_perf": cluster_bureau_performance(df),
        "shipment": cluster_shipment_profile(df),
        "region_demand": cluster_region_demand(df),
        "temporal": cluster_temporal_patterns(df),
        "vehicle": cluster_vehicle_sizing(df),
    }
