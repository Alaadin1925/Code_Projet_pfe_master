"""Business logic for the national dashboard: assembles KPIs and chart series
from the repository. No SQL here, no Flask here — just orchestration.

Optional filters (used by the dashboard and report generation):
  * region        — a single depot region
  * next_regions  — Region Next filter (list; "(VIDE)" = blank)
  * categories    — bureau categories ("agences"/"bureaux"/"centres")
"""
from __future__ import annotations

from ..repositories import shipment_repository as repo

LATE_THRESHOLD_DAYS = repo.LATE_THRESHOLD_DAYS


def kpi_summary(region=None, next_regions=None, categories=None) -> dict:
    """Headline KPI cards."""
    extra = repo.conditions(next_regions, categories)
    total = repo.total_shipments(region, extra)
    delivered = repo.delivered_count(region, extra)
    return {
        "total_shipments": total,
        "total_revenue": round(repo.total_revenue(region, extra), 2),
        "total_crbt_count": repo.total_crbt_count(region, extra),
        "total_crbt_amount": round(repo.total_crbt_amount(region, extra), 2),
        "delivered": delivered,
        "failed": total - delivered,
        "delivery_rate": round(delivered / total * 100, 1) if total else 0.0,
        "avg_interval_days": repo.average_interval(region, extra),
        "late_deliveries": repo.late_deliveries(LATE_THRESHOLD_DAYS, region, extra),
        "late_threshold": LATE_THRESHOLD_DAYS,
    }


def dashboard_data(region=None, next_regions=None, categories=None) -> dict:
    """Everything the dashboard / report templates need in one call."""
    extra = repo.conditions(next_regions, categories)
    return {
        "region": region,
        "regions": repo.distinct_regions(),
        "kpis": kpi_summary(region, next_regions, categories),
        "by_region": repo.count_by_depot_region(extra),
        "by_office": repo.count_by_depot_office(limit=15, region=region, extra=extra),
        "delivery_status": repo.delivery_status(region, extra),
        "failure_causes": repo.failure_causes(region, extra),
        "monthly": repo.monthly_evolution(region, extra),
        "weight_stats": repo.weight_stats(region, extra),
        "weight_buckets": repo.weight_buckets(region, extra),
        "revenue_by_region": repo.revenue_by_region(extra),
    }


def has_data() -> bool:
    return repo.total_shipments() > 0
