"""SQLite models: users (auth), per-region email recipients, and report job runs."""
import json
from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class RegionEmail(db.Model):
    """Editable per-region recipient address (falls back to DEFAULT_EMAIL if blank)."""
    id = db.Column(db.Integer, primary_key=True)
    region = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), default="")


class JobRun(db.Model):
    """A queued/running/finished report job. Acts as the job queue row itself —
    the worker thread polls for status == 'pending'."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    regions_json = db.Column(db.Text, nullable=False)       # JSON list of region names
    include_depot = db.Column(db.Boolean, default=True, nullable=False)
    include_livraison = db.Column(db.Boolean, default=True, nullable=False)
    col_depot_json     = db.Column(db.Text, default="[]")   # selected depot column keys
    col_livraison_json = db.Column(db.Text, default="[]")   # selected livraison column keys
    cat_depot_json      = db.Column(db.Text, default="[]")   # selected depot bureau categories
    cat_livraison_json  = db.Column(db.Text, default="[]")   # selected livraison bureau categories
    region_next_json    = db.Column(db.Text, default="[]")   # Region Next filter ([] = all)

    status = db.Column(db.String(20), default="pending", nullable=False)  # pending|running|done|failed
    log_text = db.Column(db.Text, default="")
    success_count = db.Column(db.Integer, default=0)
    failed_regions_json = db.Column(db.Text, default="[]")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)

    user = db.relationship("User", backref="jobs")

    @property
    def regions(self):
        return json.loads(self.regions_json)

    @regions.setter
    def regions(self, value):
        self.regions_json = json.dumps(value)

    @property
    def failed_regions(self):
        return json.loads(self.failed_regions_json or "[]")

    @failed_regions.setter
    def failed_regions(self, value):
        self.failed_regions_json = json.dumps(value)

    @property
    def col_depot(self):
        v = json.loads(self.col_depot_json or "[]")
        if not v:
            from core.config import DEPOT_COL_KEYS_DEFAULT
            return DEPOT_COL_KEYS_DEFAULT
        return v

    @col_depot.setter
    def col_depot(self, value):
        self.col_depot_json = json.dumps(value)

    @property
    def col_livraison(self):
        v = json.loads(self.col_livraison_json or "[]")
        if not v:
            from core.config import LIVRAISON_COL_KEYS_DEFAULT
            return LIVRAISON_COL_KEYS_DEFAULT
        return v

    @col_livraison.setter
    def col_livraison(self, value):
        self.col_livraison_json = json.dumps(value)

    @property
    def cat_depot(self):
        v = json.loads(self.cat_depot_json or "[]")
        if not v:
            from core.config import DEPOT_CAT_KEYS_DEFAULT
            return DEPOT_CAT_KEYS_DEFAULT
        return v

    @cat_depot.setter
    def cat_depot(self, value):
        self.cat_depot_json = json.dumps(value)

    @property
    def region_next(self):
        return json.loads(self.region_next_json or "[]")

    @region_next.setter
    def region_next(self, value):
        self.region_next_json = json.dumps(value)

    @property
    def cat_livraison(self):
        v = json.loads(self.cat_livraison_json or "[]")
        if not v:
            from core.config import LIVRAISON_CAT_KEYS_DEFAULT
            return LIVRAISON_CAT_KEYS_DEFAULT
        return v

    @cat_livraison.setter
    def cat_livraison(self, value):
        self.cat_livraison_json = json.dumps(value)

    def append_log(self, line):
        self.log_text = (self.log_text or "") + line + "\n"


def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()
        # Ensure a RegionEmail row exists for every configured region
        from core import config as cfg  # local import to avoid import-order issues
        existing = {r.region for r in RegionEmail.query.all()}
        for region in cfg.REGIONS:
            if region not in existing:
                db.session.add(RegionEmail(region=region, email=""))
        db.session.commit()
