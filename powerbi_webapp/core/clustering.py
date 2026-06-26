"""Five clustering analyses on La Poste Tunisienne postal data."""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (silhouette_score, davies_bouldin_score,
                             calinski_harabasz_score)
from scipy.cluster.hierarchy import cophenet, linkage as sp_linkage
from scipy.spatial.distance import pdist

from .data_loaders import norm


# ─── palette ─────────────────────────────────────────────────────────────────

COLORS      = ["#2ecc71", "#f39c12", "#e74c3c", "#3498db", "#9b59b6"]
COLORS_LITE = ["#d5f5e3", "#fef9e7", "#fce4e4", "#d6eaf8", "#e8daef"]


# ─── internal helpers ─────────────────────────────────────────────────────────

def _col(df, name):
    """Find a column by normalized name; return None if missing."""
    return next((c for c in df.columns if norm(c) == norm(name)), None)


def _num(series):
    """Parse a string Series to float, handling comma decimal separators."""
    return pd.to_numeric(series.str.replace(",", ".", regex=False), errors="coerce")


def _scale(arr):
    sc = StandardScaler()
    return sc.fit_transform(arr), sc


def _eval_metrics(Xs, labels):
    unique = set(labels) - {-1}
    if len(unique) < 2:
        return {"silhouette": None, "davies_bouldin": None, "calinski_harabasz": None}
    m = {}
    try:
        m["silhouette"] = round(float(silhouette_score(Xs, labels)), 4)
    except Exception:
        m["silhouette"] = None
    try:
        m["davies_bouldin"] = round(float(davies_bouldin_score(Xs, labels)), 4)
    except Exception:
        m["davies_bouldin"] = None
    try:
        m["calinski_harabasz"] = round(float(calinski_harabasz_score(Xs, labels)), 2)
    except Exception:
        m["calinski_harabasz"] = None
    return m


def _kmeans(Xs, k, seed=42):
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    return km.fit_predict(Xs).tolist(), km


def _remap(labels, sort_values, ascending=False):
    """
    Remap cluster integers so that cluster 0 corresponds to the highest
    (or lowest if ascending=True) mean of sort_values.
    """
    tmp = pd.Series(labels, name="c")
    sv  = pd.Series(sort_values)
    means = sv.groupby(tmp).mean().sort_values(ascending=ascending)
    mapping = {old: new for new, old in enumerate(means.index)}
    return [mapping[v] for v in labels]


def _ok(**kw):
    return {"ok": True, "error": None, **kw}


def _err(msg):
    return {
        "ok": False, "error": msg,
        "n_clusters": 0, "n_samples": 0,
        "features_used": [], "metrics": {},
        "rows": [], "cluster_labels": {},
        "cluster_colors": {}, "cluster_colors_light": {},
    }


# ─── Clustering 1 — Bureau / Depot Performance ───────────────────────────────

def cluster_bureau_performance(df, k=3):
    """
    Aggregate by Bureau depot then cluster on:
      taux_livraison, avg_intervalle, total_colis, total_ca, taux_crbt.

    Cluster 0 = Performant (highest delivery rate)
    Cluster 1 = Standard
    Cluster 2 = À améliorer (lowest delivery rate)
    """
    bur_c  = _col(df, "Bureau depot")
    if bur_c is None:
        return _err("Colonne 'Bureau depot' introuvable.")

    de_c   = _col(df, "Dernier E")
    itv_c  = _col(df, "Intervalle en jours")
    ca_c   = _col(df, "CA")
    crbt_c = _col(df, "CRBT/ORD")

    grp_key = df[bur_c].str.strip()
    agg = pd.DataFrame({"total_colis": grp_key.value_counts()})

    if de_c:
        delivered = df[de_c].str.strip().str.lower().str.startswith("envoi liv")
        agg["taux_livraison"] = delivered.groupby(grp_key).mean() * 100
    if itv_c:
        agg["avg_intervalle"] = _num(df[itv_c]).groupby(grp_key).mean()
    if ca_c:
        agg["total_ca"] = _num(df[ca_c]).groupby(grp_key).sum()
    if crbt_c:
        is_crbt = (df[crbt_c].str.strip().str.upper() == "CRBT")
        agg["taux_crbt"] = is_crbt.groupby(grp_key).mean() * 100

    agg = agg[agg["total_colis"] >= 5].reset_index()
    agg.rename(columns={"index": "bureau"}, inplace=True)
    if "Bureau depot" in agg.columns:
        agg.rename(columns={"Bureau depot": "bureau"}, inplace=True)
    # handle groupby key column name
    if bur_c in agg.columns:
        agg.rename(columns={bur_c: "bureau"}, inplace=True)

    feat = [c for c in ["taux_livraison", "avg_intervalle", "total_colis",
                         "total_ca", "taux_crbt"] if c in agg.columns]
    if len(feat) < 2 or len(agg) < k:
        return _err(f"Pas assez de bureaux ({len(agg)}) ou de features ({len(feat)}).")

    X  = agg[feat].fillna(agg[feat].median()).values
    Xs, _ = _scale(X)
    raw, _ = _kmeans(Xs, k)

    sort_col = "taux_livraison" if "taux_livraison" in feat else "total_colis"
    labels = _remap(raw, agg[sort_col].values, ascending=False)

    cluster_names = {0: "Performant", 1: "Standard", 2: "À améliorer", 3: "Critique"}
    agg["cluster"] = labels

    rows = []
    for _, r in agg.iterrows():
        row = {
            "name":          str(r.get("bureau", "")),
            "cluster":       int(r["cluster"]),
            "cluster_label": cluster_names.get(int(r["cluster"]), f"C{r['cluster']}"),
        }
        for c in feat:
            row[c] = round(float(r[c]), 2) if pd.notnull(r[c]) else None
        rows.append(row)

    rows.sort(key=lambda x: (x["cluster"], x["name"]))

    return _ok(
        n_clusters=k, n_samples=len(agg), features_used=feat,
        metrics=_eval_metrics(Xs, labels),
        rows=rows,
        cluster_labels={i: cluster_names[i] for i in range(k) if i in cluster_names},
        cluster_colors={i: COLORS[i] for i in range(k)},
        cluster_colors_light={i: COLORS_LITE[i] for i in range(k)},
    )


# ─── Clustering 2 — Shipment Profile (row-level) ─────────────────────────────

def cluster_shipment_profile(df, k=4, max_rows=10_000):
    """
    Cluster individual parcels on numeric features.
    Returns cluster-level summary (not one row per parcel).

    Cluster 0 = Rapide & léger (shortest interval)
    Cluster 3 = Hors norme / lent
    """
    de_c    = _col(df, "Dernier E")
    itv_c   = _col(df, "Intervalle en jours")
    ca_c    = _col(df, "CA")
    poids_c = _col(df, "poids")
    crbt_c  = _col(df, "CRBT/ORD")

    sub = pd.DataFrame(index=df.index)
    feat_map = {}  # internal_col -> display label

    if itv_c:
        sub["_itv"]   = _num(df[itv_c]);   feat_map["_itv"]   = "Intervalle (j)"
    if ca_c:
        sub["_ca"]    = _num(df[ca_c]);    feat_map["_ca"]    = "CA (DT)"
    if poids_c:
        sub["_poids"] = _num(df[poids_c]); feat_map["_poids"] = "Poids"
    if crbt_c:
        sub["_crbt"]  = (df[crbt_c].str.strip().str.upper() == "CRBT").astype(float)
        feat_map["_crbt"] = "CRBT"
    if de_c:
        sub["_del"] = (df[de_c].str.strip().str.lower()
                        .str.startswith("envoi liv")).astype(float)
        feat_map["_del"] = "Livré"

    fcols = list(feat_map.keys())
    if len(fcols) < 2:
        return _err("Pas assez de colonnes numériques disponibles.")

    sub = sub[fcols].dropna()
    if len(sub) < k:
        return _err("Pas assez de colis valides après nettoyage.")
    if len(sub) > max_rows:
        sub = sub.sample(max_rows, random_state=42)

    Xs, _ = _scale(sub.values)
    raw, _ = _kmeans(Xs, k)

    sort_col = "_itv" if "_itv" in fcols else fcols[0]
    labels = _remap(raw, sub[sort_col].values, ascending=True)  # 0 = fastest
    sub["cluster"] = labels

    cluster_names = {
        0: "Rapide & léger",
        1: "Standard",
        2: "Lent / problématique",
        3: "Hors norme",
    }

    rows = []
    for ci in range(k):
        mask = sub["cluster"] == ci
        stat = {
            "name":          cluster_names.get(ci, f"Cluster {ci}"),
            "cluster":       ci,
            "cluster_label": cluster_names.get(ci, f"C{ci}"),
            "n":             int(mask.sum()),
        }
        for fc, flabel in feat_map.items():
            v = sub.loc[mask, fc].mean()
            stat[flabel] = round(float(v), 2) if pd.notnull(v) else None
        rows.append(stat)

    return _ok(
        n_clusters=k, n_samples=len(sub), features_used=list(feat_map.values()),
        metrics=_eval_metrics(Xs, labels),
        rows=rows,
        cluster_labels={i: cluster_names.get(i, f"C{i}") for i in range(k)},
        cluster_colors={i: COLORS[i] for i in range(k)},
        cluster_colors_light={i: COLORS_LITE[i] for i in range(k)},
    )


# ─── Clustering 3 — Region Demand (hierarchical) ─────────────────────────────

def cluster_region_demand(df, k=3):
    """
    Aggregate by Region Depot and apply Ward hierarchical clustering.
    Also computes the cophenetic correlation coefficient.

    Cluster 0 = Forte demande (highest volume)
    """
    reg_c  = _col(df, "Region Depot")
    if reg_c is None:
        return _err("Colonne 'Region Depot' introuvable.")

    de_c   = _col(df, "Dernier E")
    itv_c  = _col(df, "Intervalle en jours")
    ca_c   = _col(df, "CA")
    crbt_c = _col(df, "CRBT/ORD")

    grp_key = df[reg_c].str.strip()
    agg = pd.DataFrame({"total_colis": grp_key.value_counts()})

    if de_c:
        delivered = df[de_c].str.strip().str.lower().str.startswith("envoi liv")
        agg["taux_livraison"] = delivered.groupby(grp_key).mean() * 100
    if ca_c:
        agg["avg_ca"] = _num(df[ca_c]).groupby(grp_key).mean()
    if crbt_c:
        is_crbt = (df[crbt_c].str.strip().str.upper() == "CRBT")
        agg["taux_crbt"] = is_crbt.groupby(grp_key).mean() * 100
    if itv_c:
        agg["avg_intervalle"] = _num(df[itv_c]).groupby(grp_key).mean()

    agg = agg.dropna(how="all").reset_index()
    if reg_c in agg.columns:
        agg.rename(columns={reg_c: "region"}, inplace=True)
    elif "index" in agg.columns:
        agg.rename(columns={"index": "region"}, inplace=True)

    agg = agg[agg["region"].str.strip() != ""].reset_index(drop=True)

    feat = [c for c in ["total_colis", "taux_livraison", "avg_ca",
                         "taux_crbt", "avg_intervalle"] if c in agg.columns]
    if len(feat) < 2 or len(agg) < k:
        return _err(f"Pas assez de régions ({len(agg)}) ou de features ({len(feat)}).")

    X  = agg[feat].fillna(agg[feat].median()).values
    Xs, _ = _scale(X)

    hc  = AgglomerativeClustering(n_clusters=k, linkage="ward")
    raw = hc.fit_predict(Xs).tolist()
    labels = _remap(raw, agg["total_colis"].values, ascending=False)

    # Cophenetic correlation
    cophenetic_r = None
    try:
        Z = sp_linkage(Xs, method="ward")
        c_val, _ = cophenet(Z, pdist(Xs))
        cophenetic_r = round(float(c_val), 4)
    except Exception:
        pass

    cluster_names = {0: "Forte demande", 1: "Demande moyenne", 2: "Faible demande"}
    agg["cluster"] = labels

    rows = []
    for _, r in agg.iterrows():
        ci = int(r["cluster"])
        row = {
            "name":          str(r.get("region", "")),
            "cluster":       ci,
            "cluster_label": cluster_names.get(ci, f"C{ci}"),
        }
        for c in feat:
            row[c] = round(float(r[c]), 2) if pd.notnull(r[c]) else None
        rows.append(row)

    rows.sort(key=lambda x: (x["cluster"], -(x.get("total_colis") or 0)))

    metrics = _eval_metrics(Xs, labels)
    if cophenetic_r is not None:
        metrics["cophenetic"] = cophenetic_r

    return _ok(
        n_clusters=k, n_samples=len(agg), features_used=feat,
        metrics=metrics,
        rows=rows,
        cluster_labels={i: cluster_names[i] for i in range(k) if i in cluster_names},
        cluster_colors={i: COLORS[i] for i in range(k)},
        cluster_colors_light={i: COLORS_LITE[i] for i in range(k)},
    )


# ─── Clustering 4 — Temporal Patterns ────────────────────────────────────────

def cluster_temporal_patterns(df, k=3):
    """
    Aggregate shipments by calendar date and cluster days into
    Jour de pointe / Jour normal / Jour creux.
    Requires at least one column whose normalized name contains 'date'.
    """
    date_col = next(
        (c for c in df.columns
         if "date" in norm(c) and "bureau" not in norm(c) and "region" not in norm(c)),
        None,
    )
    if date_col is None:
        return _err("Aucune colonne de date trouvée dans le fichier Excel.")

    de_c = _col(df, "Dernier E")
    ca_c = _col(df, "CA")

    sub = df.copy()
    try:
        sub["_date"] = pd.to_datetime(sub[date_col], errors="coerce", dayfirst=True)
    except Exception:
        return _err(f"Impossible de convertir '{date_col}' en dates.")

    sub = sub.dropna(subset=["_date"])
    if sub.empty:
        return _err("Aucune date valide trouvée.")

    sub["_day"] = sub["_date"].dt.date
    sub["_dow"] = sub["_date"].dt.dayofweek.astype(float)  # 0=Mon

    g = sub.groupby("_day")
    agg = pd.DataFrame({
        "daily_volume":  g.size(),
        "day_of_week":   sub.groupby("_day")["_dow"].first(),
    })
    if de_c:
        agg["daily_taux_liv"] = (
            sub[de_c].str.strip().str.lower().str.startswith("envoi liv")
            .groupby(sub["_day"]).mean() * 100
        )
    if ca_c:
        agg["daily_ca"] = _num(sub[ca_c]).groupby(sub["_day"]).sum()

    agg = agg.dropna(how="all").reset_index()
    agg.rename(columns={"_day": "date"}, inplace=True)

    feat = [c for c in ["daily_volume", "daily_taux_liv", "daily_ca", "day_of_week"]
            if c in agg.columns]
    if len(feat) < 2 or len(agg) < k:
        return _err(f"Pas assez de jours ({len(agg)}) pour la clustérisation temporelle.")

    X  = agg[feat].fillna(agg[feat].median()).values
    Xs, _ = _scale(X)
    raw, _ = _kmeans(Xs, k)
    labels = _remap(raw, agg["daily_volume"].values, ascending=False)  # 0 = peak

    cluster_names = {0: "Jour de pointe", 1: "Jour normal", 2: "Jour creux"}
    agg["cluster"] = labels

    rows = []
    for _, r in agg.iterrows():
        ci = int(r["cluster"])
        row = {
            "name":          str(r["date"]),
            "cluster":       ci,
            "cluster_label": cluster_names.get(ci, f"C{ci}"),
        }
        for c in feat:
            row[c] = round(float(r[c]), 2) if pd.notnull(r[c]) else None
        rows.append(row)

    # Cluster summary for display
    cluster_summary = []
    for ci in range(k):
        mask = agg["cluster"] == ci
        stat = {
            "cluster": ci,
            "cluster_label": cluster_names.get(ci, f"C{ci}"),
            "n_jours": int(mask.sum()),
        }
        for c in feat:
            v = agg.loc[mask, c].mean()
            stat[f"avg_{c}"] = round(float(v), 2) if pd.notnull(v) else None
        cluster_summary.append(stat)

    return _ok(
        n_clusters=k, n_samples=len(agg), features_used=feat,
        metrics=_eval_metrics(Xs, labels),
        rows=rows,
        cluster_summary=cluster_summary,
        cluster_labels={i: cluster_names.get(i, f"C{i}") for i in range(k)},
        cluster_colors={i: COLORS[i] for i in range(k)},
        cluster_colors_light={i: COLORS_LITE[i] for i in range(k)},
    )


# ─── Clustering 5 — Vehicle Sizing by Region ─────────────────────────────────

def cluster_vehicle_sizing(df, k=3):
    """
    Aggregate by Region Depot and cluster on total load and density.
    Cluster 0 = Camion  (heaviest / highest volume)
    Cluster 1 = Fourgon (medium)
    Cluster 2 = Voiture légère (lightest)
    """
    reg_c   = _col(df, "Region Depot")
    if reg_c is None:
        return _err("Colonne 'Region Depot' introuvable.")

    bur_c   = _col(df, "Bureau depot")
    crbt_c  = _col(df, "CRBT/ORD")
    poids_c = _col(df, "poids")

    grp_key = df[reg_c].str.strip()
    agg = pd.DataFrame({"total_colis": grp_key.value_counts()})

    if bur_c:
        agg["nb_bureaux"]    = df.groupby(grp_key)[bur_c].nunique()
        agg["densite_colis"] = agg["total_colis"] / agg["nb_bureaux"].replace(0, np.nan)
    if poids_c:
        p = _num(df[poids_c])
        agg["total_poids"] = p.groupby(grp_key).sum()
        agg["avg_poids"]   = p.groupby(grp_key).mean()
    if crbt_c:
        is_crbt = (df[crbt_c].str.strip().str.upper() == "CRBT")
        agg["taux_crbt"] = is_crbt.groupby(grp_key).mean() * 100

    agg = agg.dropna(how="all").reset_index()
    if reg_c in agg.columns:
        agg.rename(columns={reg_c: "region"}, inplace=True)
    elif "index" in agg.columns:
        agg.rename(columns={"index": "region"}, inplace=True)

    agg = agg[agg["region"].str.strip() != ""].reset_index(drop=True)

    feat = [c for c in ["total_colis", "total_poids", "avg_poids",
                         "nb_bureaux", "densite_colis", "taux_crbt"]
            if c in agg.columns]
    if len(feat) < 2 or len(agg) < k:
        return _err(f"Pas assez de données ({len(agg)} régions, {len(feat)} features).")

    X  = agg[feat].fillna(agg[feat].median()).values
    Xs, _ = _scale(X)
    raw, _ = _kmeans(Xs, k)

    sort_col = "total_poids" if "total_poids" in feat else "total_colis"
    labels = _remap(raw, agg[sort_col].values, ascending=False)  # 0 = heaviest = camion

    vehicle_names  = {0: "Camion",        1: "Fourgon",  2: "Voiture légère"}
    vehicle_icons  = {0: "Camion",        1: "Fourgon",  2: "Voiture légère"}
    vehicle_colors = {0: COLORS[2],       1: COLORS[1],  2: COLORS[0]}   # red / orange / green
    vehicle_colors_lite = {0: COLORS_LITE[2], 1: COLORS_LITE[1], 2: COLORS_LITE[0]}

    agg["cluster"] = labels

    rows = []
    for _, r in agg.iterrows():
        ci = int(r["cluster"])
        row = {
            "name":          str(r.get("region", "")),
            "cluster":       ci,
            "cluster_label": vehicle_names.get(ci, f"C{ci}"),
        }
        for c in feat:
            row[c] = round(float(r[c]), 2) if pd.notnull(r[c]) else None
        rows.append(row)

    rows.sort(key=lambda x: (x["cluster"], x["name"]))

    return _ok(
        n_clusters=k, n_samples=len(agg), features_used=feat,
        metrics=_eval_metrics(Xs, labels),
        rows=rows,
        cluster_labels=vehicle_names,
        cluster_colors=vehicle_colors,
        cluster_colors_light=vehicle_colors_lite,
    )


# ─── public entry point ───────────────────────────────────────────────────────

def run_all(df):
    """Run all five clustering analyses and return a dict of results."""
    return {
        "bureau_perf":   cluster_bureau_performance(df),
        "shipment":      cluster_shipment_profile(df),
        "region_demand": cluster_region_demand(df),
        "temporal":      cluster_temporal_patterns(df),
        "vehicle":       cluster_vehicle_sizing(df),
    }
