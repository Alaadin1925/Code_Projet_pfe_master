"""region_recipients — editable per-region report email recipient.

Blank email → the report for that region falls back to MAIL_DEFAULT_RECIPIENT.
"""
from __future__ import annotations

from ..extensions import db


class RegionRecipient(db.Model):
    __tablename__ = "region_recipients"

    id = db.Column(db.Integer, primary_key=True)
    region = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), default="", nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RegionRecipient {self.region} -> {self.email or '(default)'}>"
