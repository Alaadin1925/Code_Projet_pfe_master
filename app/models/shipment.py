"""Shipment tables — one row per parcel, three sources:
  * national_shipments  (Tunisia → Tunisia)        — sheet 'national'
  * export_shipments    (Tunisia → abroad)         — sheet 'export'
  * import_shipments    (abroad → Tunisia)         — import.xls

All three share the same column set (a declarative mixin); import.xls simply
leaves the columns it doesn't provide (CA, CRBT/ORD, …) NULL. Clean English
column names; the mapping to the original French headers lives in
``app/data_import/column_mapping.py``.
"""
from __future__ import annotations

from datetime import datetime

from ..extensions import db


class _ShipmentMixin:
    """Shared shipment columns (one physical copy per concrete table)."""

    id = db.Column(db.Integer, primary_key=True)

    # Indexed but NOT unique: a MAILITM_FID can legitimately repeat across rows
    # (e.g. the same parcel under different bureaux/events in import.xls). We
    # store every source row so report counts match the source exactly.
    mailitm_fid = db.Column(db.String(40), nullable=False, index=True)  # MAILITM_FID

    weight_kg = db.Column(db.Float, nullable=True)                 # poids
    crbt_amount = db.Column(db.Numeric(18, 3), nullable=True)      # CRBT (cash-on-delivery amount)
    shipment_type = db.Column(db.String(20), nullable=True, index=True)  # CRBT/ORD
    is_crbt = db.Column(db.Boolean, default=False, nullable=False)       # derived
    revenue_ca = db.Column(db.Numeric(18, 3), nullable=True)       # CA
    weight_tier_2_3kg = db.Column(db.Float, nullable=True)         # "sup à 2 kg jusquà 3 kg"
    weight_extra_per_kg = db.Column(db.Float, nullable=True)       # "Pour chaque kg supp …"

    sender_name = db.Column(db.String(255), nullable=True)         # Nom_exp
    sender_firstname = db.Column(db.String(255), nullable=True)    # Pre_exp
    sender_address = db.Column(db.String(512), nullable=True)      # Exp_adresse
    sender_city = db.Column(db.String(160), nullable=True)         # Exp_cité
    sender_postal_code = db.Column(db.String(20), nullable=True)   # Exp_code_postale
    sender_phone = db.Column(db.String(40), nullable=True)         # Exp_phone

    origin_country = db.Column(db.String(80), nullable=True)       # Pays origine
    destination_country = db.Column(db.String(80), nullable=True)  # Pays Destination

    deposit_date = db.Column(db.DateTime, nullable=True, index=True)  # Date depot
    deposit_month = db.Column(db.Integer, nullable=True, index=True)  # Mois_depot
    deposit_year = db.Column(db.Integer, nullable=True, index=True)   # Annee_depot
    depot_office = db.Column(db.String(255), nullable=True, index=True)  # Bureau depot
    depot_region = db.Column(db.String(80), nullable=True, index=True)   # Region Depot

    last_event = db.Column(db.String(255), nullable=True, index=True)    # Dernier E
    last_event_date = db.Column(db.DateTime, nullable=True)              # Date dernier E
    last_event_office = db.Column(db.String(255), nullable=True, index=True)  # Bureau dernier E
    last_event_region = db.Column(db.String(80), nullable=True, index=True)   # Region dernier E
    is_delivered = db.Column(db.Boolean, default=False, nullable=False, index=True)  # derived

    next_office = db.Column(db.String(255), nullable=True)         # Bureau next
    next_region = db.Column(db.String(80), nullable=True)          # Region Next

    interval_days = db.Column(db.Integer, nullable=True)          # Intervalle en jours
    interval_edi_deposit = db.Column(db.Float, nullable=True)     # intervalle liv EDI/dépôt
    failure_or_delivery_date = db.Column(db.DateTime, nullable=True)  # date echec ou livraison

    edi_event = db.Column(db.String(255), nullable=True)          # EDI_Event
    edi_date = db.Column(db.String(64), nullable=True)            # EDI_Date
    edi_cause = db.Column(db.String(255), nullable=True)          # EDI_Cause
    edi_action = db.Column(db.String(512), nullable=True)         # EDI_action

    import_batch = db.Column(db.String(64), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)


class NationalShipment(_ShipmentMixin, db.Model):
    __tablename__ = "national_shipments"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NationalShipment {self.mailitm_fid} {self.depot_region}→{self.last_event_region}>"


class ExportShipment(_ShipmentMixin, db.Model):
    __tablename__ = "export_shipments"


class ImportShipment(_ShipmentMixin, db.Model):
    __tablename__ = "import_shipments"
