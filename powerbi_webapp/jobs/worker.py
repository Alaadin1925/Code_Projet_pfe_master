"""Single background worker thread that processes queued JobRun rows one at a time.

Only one PBI browser session can run at a time, so a single worker (no Celery/Redis)
is intentional: it's simpler and matches the real concurrency limit.
"""
import threading
import time
from datetime import datetime

from models import JobRun, RegionEmail, db
from core import config as cfg
from core.pbi_scraper import run_regions_job

_POLL_INTERVAL = 3  # seconds


def _process_job(app, job_id):
    with app.app_context():
        job = db.session.get(JobRun, job_id)
        if job is None:
            return
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.session.commit()

        def log(msg):
            with app.app_context():
                j = db.session.get(JobRun, job_id)
                j.append_log(str(msg))
                db.session.commit()

        region_emails = {r.region: r.email for r in RegionEmail.query.all()}

        try:
            success, failed, _files = run_regions_job(
                regions=job.regions,
                region_emails=region_emails,
                include_depot=job.include_depot,
                include_livraison=job.include_livraison,
                output_dir=cfg.REPORTS_DIR,
                col_depot=job.col_depot,
                col_livraison=job.col_livraison,
                cat_depot=job.cat_depot,
                cat_livraison=job.cat_livraison,
                region_next=job.region_next or None,
                log=log,
            )
            job = db.session.get(JobRun, job_id)
            job.success_count = success
            job.failed_regions = failed
            job.status = "done"
        except Exception as e:
            job = db.session.get(JobRun, job_id)
            job.append_log(f"❌ Erreur fatale du job : {e}")
            job.status = "failed"
        finally:
            job.finished_at = datetime.utcnow()
            db.session.commit()


def _worker_loop(app):
    while True:
        with app.app_context():
            job = JobRun.query.filter_by(status="pending").order_by(JobRun.created_at).first()
            job_id = job.id if job else None
        if job_id is not None:
            _process_job(app, job_id)
        else:
            time.sleep(_POLL_INTERVAL)


def start_worker(app):
    thread = threading.Thread(target=_worker_loop, args=(app,), daemon=True, name="pbi-job-worker")
    thread.start()
    return thread
