"""Data-access for report jobs and generated reports."""
from __future__ import annotations

from datetime import datetime

from ..extensions import db
from ..models import GeneratedReport, ReportJob
from ..models.jobs import JOB_PENDING


def create_job(user_id: int, params: dict, job_type: str = "national_report") -> ReportJob:
    job = ReportJob(user_id=user_id, job_type=job_type)
    job.params = params
    db.session.add(job)
    db.session.commit()
    return job


def get(job_id: int) -> ReportJob | None:
    return db.session.get(ReportJob, job_id)


def recent(limit: int = 10) -> list[ReportJob]:
    return (db.session.query(ReportJob)
            .order_by(ReportJob.created_at.desc()).limit(limit).all())


def next_pending() -> ReportJob | None:
    return (db.session.query(ReportJob)
            .filter(ReportJob.status == JOB_PENDING)
            .order_by(ReportJob.created_at).first())


def add_generated_report(job_id: int, file_name: str, region: str | None = None,
                         file_format: str = "html", emailed_to: str | None = None) -> GeneratedReport:
    rep = GeneratedReport(job_id=job_id, file_name=file_name, region=region,
                          file_format=file_format, emailed_to=emailed_to)
    db.session.add(rep)
    db.session.commit()
    return rep


def mark(job: ReportJob, status: str, **fields) -> None:
    job.status = status
    for key, value in fields.items():
        setattr(job, key, value)
    if status in ("done", "failed"):
        job.finished_at = datetime.utcnow()
    db.session.commit()
