"""Reporting job models: report_jobs (the queue) and generated_reports (outputs)."""
from __future__ import annotations

import json
from datetime import datetime

from ..extensions import db

JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"


class ReportJob(db.Model):
    """A queued/running/finished report job.

    The row itself is the queue: the background worker polls for status='pending'.
    `params_json` holds the request options (selected regions, sections, filters).
    """

    __tablename__ = "report_jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    job_type = db.Column(db.String(40), default="national_report", nullable=False)
    params_json = db.Column(db.Text, default="{}", nullable=False)

    status = db.Column(db.String(20), default=JOB_PENDING, nullable=False, index=True)
    log_text = db.Column(db.Text, default="")
    success_count = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref="report_jobs")
    reports = db.relationship("GeneratedReport", back_populates="job",
                              cascade="all, delete-orphan")

    @property
    def params(self) -> dict:
        try:
            return json.loads(self.params_json or "{}")
        except (ValueError, TypeError):
            return {}

    @params.setter
    def params(self, value: dict) -> None:
        self.params_json = json.dumps(value or {})

    def append_log(self, line: str) -> None:
        self.log_text = (self.log_text or "") + str(line) + "\n"


class GeneratedReport(db.Model):
    """A single artifact produced by a ReportJob (HTML report file)."""

    __tablename__ = "generated_reports"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("report_jobs.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    region = db.Column(db.String(80), nullable=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_format = db.Column(db.String(20), default="html", nullable=False)
    emailed_to = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    job = db.relationship("ReportJob", back_populates="reports")
