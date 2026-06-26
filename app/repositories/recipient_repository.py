"""Data-access for per-region report recipients."""
from __future__ import annotations

from ..extensions import db
from ..models import RegionRecipient


def ensure_seeded(regions: list[str]) -> None:
    """Create an (empty) recipient row for every configured region if missing."""
    existing = {row[0] for row in db.session.query(RegionRecipient.region).all()}
    added = False
    for region in regions:
        if region not in existing:
            db.session.add(RegionRecipient(region=region, email=""))
            added = True
    if added:
        db.session.commit()


def email_map() -> dict[str, str]:
    return {r.region: (r.email or "")
            for r in db.session.query(RegionRecipient).order_by(RegionRecipient.region).all()}


def upsert_many(emails: dict[str, str]) -> None:
    """Update recipient emails from a {region: email} mapping."""
    rows = {r.region: r for r in db.session.query(RegionRecipient).all()}
    changed = False
    for region, email in emails.items():
        email = (email or "").strip()
        row = rows.get(region)
        if row is None:
            db.session.add(RegionRecipient(region=region, email=email))
            changed = True
        elif (row.email or "") != email:
            row.email = email
            changed = True
    if changed:
        db.session.commit()
