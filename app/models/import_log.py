"""import_logs — audit trail for every national Excel import run."""
from __future__ import annotations

from datetime import datetime

from ..extensions import db

IMPORT_RUNNING = "running"
IMPORT_SUCCESS = "success"
IMPORT_FAILED = "failed"


class ImportLog(db.Model):
    __tablename__ = "import_logs"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.String(64), nullable=False, index=True)
    source_file = db.Column(db.String(512), nullable=True)
    sheet_name = db.Column(db.String(120), nullable=True)

    status = db.Column(db.String(20), default=IMPORT_RUNNING, nullable=False)
    rows_read = db.Column(db.Integer, default=0)
    rows_inserted = db.Column(db.Integer, default=0)
    rows_updated = db.Column(db.Integer, default=0)
    rows_skipped = db.Column(db.Integer, default=0)
    message = db.Column(db.Text, nullable=True)

    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ImportLog {self.batch_id} {self.status} +{self.rows_inserted}/~{self.rows_updated}>"
