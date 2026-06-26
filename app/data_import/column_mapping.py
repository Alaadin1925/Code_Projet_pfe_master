"""Mapping between the original French Excel headers and the clean English model
columns. This is the single source of truth used by:
  * the import pipeline (to read + convert each column),
  * the SQL schema documentation,
  * the README data dictionary.

Each entry: (excel_header, model_attribute, kind)
  kind ∈ {"str", "int", "float", "datetime"}
Derived columns (is_crbt, is_delivered) are computed in the importer, not here.
"""
from __future__ import annotations

import unicodedata

# Order matches the national sheet's 33 columns (left → right).
COLUMN_MAP: list[tuple[str, str, str]] = [
    ("MAILITM_FID", "mailitm_fid", "str"),
    ("poids", "weight_kg", "float"),
    ("Nom_exp", "sender_name", "str"),
    ("Pre_exp", "sender_firstname", "str"),
    ("Exp_adresse", "sender_address", "str"),
    ("Exp_cité", "sender_city", "str"),
    ("Exp_code_postale", "sender_postal_code", "str"),
    ("Exp_phone", "sender_phone", "str"),
    ("Pays origine", "origin_country", "str"),
    ("Pays Destination", "destination_country", "str"),
    ("CRBT", "crbt_amount", "float"),
    ("Date depot", "deposit_date", "datetime"),
    ("Mois_depot", "deposit_month", "int"),
    ("Annee_depot", "deposit_year", "int"),
    ("Bureau depot", "depot_office", "str"),
    ("Region Depot", "depot_region", "str"),
    ("Dernier E", "last_event", "str"),
    ("Date dernier E", "last_event_date", "datetime"),
    ("Bureau dernier E", "last_event_office", "str"),
    ("Region dernier E", "last_event_region", "str"),
    ("Bureau next", "next_office", "str"),
    ("Region Next", "next_region", "str"),
    ("Intervalle en jours", "interval_days", "int"),
    ("EDI_Event", "edi_event", "str"),
    ("EDI_Date", "edi_date", "str"),
    ("EDI_Cause", "edi_cause", "str"),
    ("EDI_action", "edi_action", "str"),
    ("date echec ou livraison", "failure_or_delivery_date", "datetime"),
    ("sup à 2 kg jusquà 3 kg", "weight_tier_2_3kg", "float"),
    ("Pour chaque kg supp ou fractionnement de 1 kg", "weight_extra_per_kg", "float"),
    ("CA", "revenue_ca", "float"),
    ("CRBT/ORD", "shipment_type", "str"),
    ("intervalle liv EDI/dépôt", "interval_edi_deposit", "float"),
]

# EDI columns hold the sentinel "X" for national data — keep verbatim (no blank→None).
EDI_VERBATIM_ATTRS = {"edi_event", "edi_date", "edi_cause", "edi_action"}


def norm(text: object) -> str:
    """Normalize a header for tolerant matching: fold accents, drop spaces/_/-,
    lowercase. So 'Exp_cité', 'EXP CITE ' and 'exp-cite' all collapse equal."""
    s = unicodedata.normalize("NFKD", str(text))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return "".join(ch for ch in s.lower() if ch.isalnum())


def build_header_lookup(df_columns) -> dict[str, str]:
    """Map each expected Excel header to the ACTUAL column name in the DataFrame
    (handles trailing spaces / accent / case differences). Missing → absent."""
    by_norm = {norm(c): c for c in df_columns}
    lookup: dict[str, str] = {}
    for excel_header, _attr, _kind in COLUMN_MAP:
        actual = by_norm.get(norm(excel_header))
        if actual is not None:
            lookup[excel_header] = actual
    return lookup
