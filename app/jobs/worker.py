"""Single background worker thread that processes queued ReportJob rows.

One worker (no Celery/Redis) is intentional and sufficient for report generation
at this scale; it keeps the deployment to two containers (app + SQL Server).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from ..extensions import db
from ..models.jobs import JOB_DONE, JOB_FAILED, JOB_RUNNING
from ..repositories import job_repository
from ..services import report_service

log = logging.getLogger("worker")
_POLL_INTERVAL = 3  # seconds


def _process(app, job_id: int) -> None:
    with app.app_context():
        job = job_repository.get(job_id)
        if job is None:
            return
        job.status = JOB_RUNNING
        job.started_at = datetime.utcnow()
        db.session.commit()

        def _log(msg):
            job.append_log(str(msg))
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()  # recover a poisoned session, keep logging best-effort

        try:
            success, _files = report_service.run_report_job(job, log=_log)
            job_repository.mark(job, JOB_DONE, success_count=success)
            log.info("Job #%s done (%s reports)", job_id, success)
        except Exception as exc:
            log.exception("Job #%s failed", job_id)
            db.session.rollback()  # clear any failed/inactive transaction first
            try:
                job = job_repository.get(job_id)  # re-fetch after rollback
                if job is not None:
                    job.append_log(f"❌ Erreur fatale : {exc}")
                    job_repository.mark(job, JOB_FAILED, error_message=str(exc))
            except Exception:
                db.session.rollback()
                log.exception("Job #%s: could not record FAILED status", job_id)


def _loop(app) -> None:
    while True:
        job_id = None
        try:
            with app.app_context():
                job = job_repository.next_pending()
                job_id = job.id if job else None
        except Exception as exc:  # DB not ready yet, etc.
            log.warning("Worker poll error: %s", exc)
        if job_id is not None:
            try:
                _process(app, job_id)
            except Exception:  # a single job must never kill the worker thread
                log.exception("Worker crashed processing job #%s", job_id)
        else:
            time.sleep(_POLL_INTERVAL)


def start_worker(app):
    thread = threading.Thread(target=_loop, args=(app,), daemon=True, name="report-worker")
    thread.start()
    log.info("Background report worker started.")
    return thread
