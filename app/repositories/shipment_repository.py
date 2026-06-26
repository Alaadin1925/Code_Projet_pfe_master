"""Data-access for national_shipments. Pure queries — no business interpretation.

Every aggregation runs in the database (works on both SQL Server and SQLite),
so the dashboard never loads 24k rows into Python. Optional filters:
  * region        — depot_region == region
  * next_regions  — Region Next filter (list; "(VIDE)" matches blank/NULL)
  * categories    — bureau categories derived from the office name
                    ("agences" / "bureaux" / "centres")
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import and_, func, or_

from ..extensions import db
from ..models import NationalShipment as S

# Default SLA threshold (days) above which a delivery is considered "late".
LATE_THRESHOLD_DAYS = 3

VIDE = "(VIDE)"


# ── Filter helpers ────────────────────────────────────────────────────────────

def _category_condition(categories):
    """Build an OR condition over bureau categories derived from depot_office."""
    if not categories:
        return None
    cats = set(categories)
    parts = []
    if "agences" in cats:
        parts.append(S.depot_office.ilike("%agence%"))
    if "centres" in cats:
        parts.append(or_(S.depot_office.ilike("%centre%"), S.depot_office.ilike("%cdc%")))
    if "bureaux" in cats:
        parts.append(and_(~S.depot_office.ilike("%agence%"),
                          ~S.depot_office.ilike("%centre%"),
                          ~S.depot_office.ilike("%cdc%")))
    return or_(*parts) if parts else None


def conditions(next_regions=None, categories=None):
    """Return a list of SQLAlchemy conditions for the optional filters."""
    conds = []
    if next_regions:
        reals = [r for r in next_regions if r != VIDE]
        ors = []
        if reals:
            ors.append(S.next_region.in_(reals))
        if VIDE in next_regions:
            ors.append(or_(S.next_region.is_(None), S.next_region == ""))
        if ors:
            conds.append(or_(*ors))
    cat = _category_condition(categories)
    if cat is not None:
        conds.append(cat)
    return conds


def _scoped(query, region=None, extra=None):
    if region:
        query = query.filter(S.depot_region == region)
    if extra:
        query = query.filter(*extra)
    return query


# ── Scalars ───────────────────────────────────────────────────────────────────

def total_shipments(region=None, extra=None) -> int:
    return _scoped(db.session.query(func.count(S.id)), region, extra).scalar() or 0


def total_revenue(region=None, extra=None) -> float:
    q = db.session.query(func.coalesce(func.sum(S.revenue_ca), 0))
    return float(_scoped(q, region, extra).scalar() or 0)


def total_crbt_amount(region=None, extra=None) -> float:
    q = db.session.query(func.coalesce(func.sum(S.crbt_amount), 0))
    return float(_scoped(q, region, extra).scalar() or 0)


def total_crbt_count(region=None, extra=None) -> int:
    q = db.session.query(func.count(S.id)).filter(S.is_crbt == True)  # noqa: E712
    return _scoped(q, region, extra).scalar() or 0


def delivered_count(region=None, extra=None) -> int:
    q = db.session.query(func.count(S.id)).filter(S.is_delivered == True)  # noqa: E712
    return _scoped(q, region, extra).scalar() or 0


def average_interval(region=None, extra=None) -> float | None:
    """Average delivery interval (days) over delivered parcels with a sane
    (non-negative) interval. Cast to Float so SQL Server's AVG does float math."""
    q = (db.session.query(func.avg(func.cast(S.interval_days, db.Float)))
         .filter(S.is_delivered == True, S.interval_days >= 0))  # noqa: E712
    val = _scoped(q, region, extra).scalar()
    return round(float(val), 2) if val is not None else None


def late_deliveries(threshold: int = LATE_THRESHOLD_DAYS, region=None, extra=None) -> int:
    q = db.session.query(func.count(S.id)).filter(S.interval_days > threshold)
    return _scoped(q, region, extra).scalar() or 0


# ── Grouped aggregations ──────────────────────────────────────────────────────

def count_by_depot_region(extra=None) -> list[tuple[str, int]]:
    q = db.session.query(S.depot_region, func.count(S.id))
    if extra:
        q = q.filter(*extra)
    rows = q.group_by(S.depot_region).order_by(func.count(S.id).desc()).all()
    return [(r or "—", c) for r, c in rows]


def count_by_depot_office(limit: int = 15, region=None, extra=None) -> list[tuple[str, int]]:
    q = db.session.query(S.depot_office, func.count(S.id))
    q = _scoped(q, region, extra)
    rows = (q.group_by(S.depot_office)
            .order_by(func.count(S.id).desc()).limit(limit).all())
    return [(r or "—", c) for r, c in rows]


def revenue_by_region(extra=None) -> list[tuple[str, float]]:
    q = db.session.query(S.depot_region, func.coalesce(func.sum(S.revenue_ca), 0))
    if extra:
        q = q.filter(*extra)
    rows = (q.group_by(S.depot_region)
            .order_by(func.coalesce(func.sum(S.revenue_ca), 0).desc()).all())
    return [(r or "—", float(v)) for r, v in rows]


def delivery_status(region=None, extra=None) -> dict[str, int]:
    total = total_shipments(region, extra)
    delivered = delivered_count(region, extra)
    return {"delivered": delivered, "failed": total - delivered, "total": total}


def failure_causes(region=None, extra=None, limit: int = 12) -> list[tuple[str, int]]:
    """For national data, failure 'cause' = the last delivery event (Dernier E)
    of non-delivered parcels — EDI_Cause is the placeholder 'X' for national."""
    q = (db.session.query(S.last_event, func.count(S.id))
         .filter(S.is_delivered == False))  # noqa: E712
    q = _scoped(q, region, extra)
    q = q.group_by(S.last_event).order_by(func.count(S.id).desc())
    return [(r or "—", c) for r, c in q.limit(limit).all()]


def monthly_evolution(region=None, extra=None) -> list[dict]:
    q = db.session.query(
            S.deposit_year, S.deposit_month,
            func.count(S.id),
            func.coalesce(func.sum(S.revenue_ca), 0),
            func.sum(func.cast(S.is_delivered, db.Integer)))
    q = _scoped(q, region, extra)
    rows = q.group_by(S.deposit_year, S.deposit_month).order_by(
        S.deposit_year, S.deposit_month).all()
    out = []
    for year, month, count, revenue, delivered in rows:
        if year is None and month is None:
            continue
        out.append({
            "year": int(year) if year is not None else None,
            "month": int(month) if month is not None else None,
            "label": f"{int(year)}-{int(month):02d}" if year and month else "—",
            "count": int(count),
            "revenue": float(revenue),
            "delivered": int(delivered or 0),
        })
    return out


def weight_stats(region=None, extra=None) -> dict:
    q = db.session.query(
        func.avg(S.weight_kg), func.min(S.weight_kg),
        func.max(S.weight_kg), func.coalesce(func.sum(S.weight_kg), 0))
    avg, mn, mx, tot = _scoped(q, region, extra).first()
    return {
        "avg": round(float(avg), 2) if avg is not None else None,
        "min": float(mn) if mn is not None else None,
        "max": float(mx) if mx is not None else None,
        "total": round(float(tot), 1) if tot is not None else 0.0,
    }


def weight_buckets(region=None, extra=None) -> list[tuple[str, int]]:
    """Distribution of parcels across weight bands (kg)."""
    bands = [(0, 2, "0–2"), (2, 5, "2–5"), (5, 10, "5–10"),
             (10, 20, "10–20"), (20, 9999, "20+")]
    out = []
    for lo, hi, label in bands:
        q = db.session.query(func.count(S.id)).filter(S.weight_kg >= lo, S.weight_kg < hi)
        out.append((label, _scoped(q, region, extra).scalar() or 0))
    return out


# ── Distinct lookups ──────────────────────────────────────────────────────────

def distinct_regions() -> list[str]:
    rows = (db.session.query(S.depot_region)
            .filter(S.depot_region.isnot(None))
            .distinct().order_by(S.depot_region).all())
    return [r[0] for r in rows if r[0]]


def distinct_next_regions() -> list[str]:
    """Distinct Region Next values; '(VIDE)' is prepended if blanks/NULLs exist."""
    rows = db.session.query(S.next_region).distinct().all()
    vals = sorted({r[0].strip() for r in rows if r[0] and r[0].strip()})
    has_blank = any((r[0] is None or not str(r[0]).strip()) for r in rows)
    return ([VIDE] if has_blank else []) + vals


# ── French-column DataFrame for the report engine (table_builder) ─────────────

# clean model attr → original French Excel header expected by table_builder
_FRENCH_MAP = {
    "mailitm_fid": "MAILITM_FID",
    "weight_kg": "poids",
    "crbt_amount": "CRBT",
    "shipment_type": "CRBT/ORD",
    "revenue_ca": "CA",
    "deposit_date": "Date depot",
    "depot_office": "Bureau depot",
    "depot_region": "Region Depot",
    "last_event": "Dernier E",
    "last_event_date": "Date dernier E",
    "last_event_office": "Bureau dernier E",
    "last_event_region": "Region dernier E",
    "next_region": "Region Next",
    "interval_days": "Intervalle en jours",
}


def _dataframe(model, next_regions=None) -> pd.DataFrame:
    """Load a shipment table as a DataFrame with ORIGINAL French column names,
    all values as strings (matching the old xlsx-based pipeline)."""
    attrs = list(_FRENCH_MAP.keys())
    cols = [getattr(model, a) for a in attrs]
    q = db.session.query(*cols)
    if next_regions:
        # Region Next filter, scoped to this model's next_region column.
        reals = [r for r in next_regions if r != VIDE]
        ors = []
        if reals:
            ors.append(model.next_region.in_(reals))
        if VIDE in next_regions:
            ors.append(or_(model.next_region.is_(None), model.next_region == ""))
        if ors:
            q = q.filter(or_(*ors))
    df = pd.DataFrame(q.all(), columns=[_FRENCH_MAP[a] for a in attrs])
    if df.empty:
        return df
    df = df.astype(object).where(pd.notna(df), "")
    for c in df.columns:
        df[c] = df[c].map(lambda v: "" if v == "" or v is None
                          else (v.strftime("%Y-%m-%d %H:%M:%S") if hasattr(v, "strftime")
                                else str(v)))
    return df


def national_dataframe(next_regions=None) -> pd.DataFrame:
    from ..models import NationalShipment
    return _dataframe(NationalShipment, next_regions)


def export_dataframe(next_regions=None) -> pd.DataFrame:
    from ..models import ExportShipment
    return _dataframe(ExportShipment, next_regions)


def import_dataframe(next_regions=None) -> pd.DataFrame:
    from ..models import ImportShipment
    return _dataframe(ImportShipment, next_regions)


# ── Bulk fetch for ML (clustering) ────────────────────────────────────────────

def fetch_dataframe(columns: list[str] | None = None, limit: int | None = None) -> pd.DataFrame:
    """Load shipments into a DataFrame with clean column names for analytics/ML."""
    columns = columns or [
        "depot_office", "depot_region", "last_event_office", "last_event_region",
        "is_delivered", "interval_days", "revenue_ca", "crbt_amount", "is_crbt",
        "weight_kg", "deposit_date", "shipment_type",
    ]
    cols = [getattr(S, c) for c in columns]
    q = db.session.query(*cols)
    if limit:
        q = q.limit(limit)
    return pd.DataFrame(q.all(), columns=columns)
