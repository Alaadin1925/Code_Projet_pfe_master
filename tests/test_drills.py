"""Drill-column logic must match the original main-branch report:
  * Import livraison drill → poids only (no Type/CA — import.xls lacks them)
  * Export depot drill     → poids + CA
And every source row is kept (no MAILITM_FID dedup)."""
import pandas as pd

from app.services import table_builder as tb


def test_import_drill_is_poids_only_and_keeps_all_rows():
    df = pd.DataFrame([
        {"MAILITM_FID": "A", "Bureau dernier E": "KA", "Region dernier E": "ARIANA",
         "Dernier E": "Envoi Livré", "poids": "3.4"},
        {"MAILITM_FID": "B", "Bureau dernier E": "KA", "Region dernier E": "ARIANA",
         "Dernier E": "Envoi Livré", "poids": "5.0"},
        {"MAILITM_FID": "A", "Bureau dernier E": "KA", "Region dernier E": "ARIANA",
         "Dernier E": "Tenir", "poids": "1.0"},  # repeated FID — must NOT be dropped
    ])
    d = tb.build_import_drill(df, "ARIANA", "t3")["t3"]
    assert d["cols"] == ["Dernier E", "Intervalle (j)", "poids"]   # Dernier E + poids, no Type/CA
    entries = d["data"]["KA"]["__all__"]
    assert len(entries) == 3                       # all rows kept (no dedup)
    assert all("Type" not in e and "CA" not in e for e in entries)
    assert all("poids" in e and "Dernier E" in e for e in entries)


def test_export_drill_is_poids_and_ca():
    df = pd.DataFrame([
        {"MAILITM_FID": "X", "Bureau depot": "AG", "Region Depot": "ARIANA",
         "CRBT/ORD": "CRBT", "CA": "7", "poids": "3.4"},
        {"MAILITM_FID": "Y", "Bureau depot": "AG", "Region Depot": "ARIANA",
         "CRBT/ORD": "Ordinaire", "CA": "5", "poids": "2.0"},
    ])
    d = tb.build_export_drill(df, "ARIANA", "t1")["t1"]
    assert d["cols"] == ["poids", "CA"]
    assert len(d["data"]["AG"]["__all__"]) == 2
    assert "CRBT" in d["data"]["AG"] and "Ordinaire" in d["data"]["AG"]
