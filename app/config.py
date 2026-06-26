"""Application configuration — everything comes from the environment (.env).

No secrets, connection strings, paths or credentials are hardcoded here.
Three named configs are provided; `get_config()` picks one from FLASK_ENV.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

# Load .env once, at import time. Real env vars always win over the file.
load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _engine_options(uri: str) -> dict:
    """Engine options. fast_executemany batches inserts/updates on SQL Server
    (pyodbc) — a huge speedup for the import — but is invalid for other dialects."""
    opts: dict = {"pool_pre_ping": True}
    if uri.startswith("mssql"):
        opts["fast_executemany"] = True
    return opts


class BaseConfig:
    """Shared configuration read from environment variables."""

    # ── Flask core ────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    APP_PORT = int(os.environ.get("APP_PORT", 8000))

    # ── Database ──────────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///local_dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)

    # ── Session / cookie security ─────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("SESSION_LIFETIME_SECONDS", 8 * 3600))
    WTF_CSRF_TIME_LIMIT = None  # CSRF token valid for the whole session

    # ── National Excel import ─────────────────────────────────────────────────
    NATIONAL_XLSX_PATH = os.environ.get("NATIONAL_XLSX_PATH", "")
    NATIONAL_SHEET_NAME = os.environ.get("NATIONAL_SHEET_NAME", "national")
    NATIONAL_HEADER_ROW = int(os.environ.get("NATIONAL_HEADER_ROW", 2))

    # Export lives in the same workbook (sheet 'export'); import is a separate .xls.
    EXPORT_SHEET_NAME = os.environ.get("EXPORT_SHEET_NAME", "export")
    EXPORT_HEADER_ROW = int(os.environ.get("EXPORT_HEADER_ROW", 2))
    IMPORT_XLS_PATH = os.environ.get("IMPORT_XLS_PATH", "")
    IMPORT_HEADER_ROW = int(os.environ.get("IMPORT_HEADER_ROW", 0))

    # ── Filesystem ────────────────────────────────────────────────────────────
    # Normalized to ABSOLUTE paths: open() resolves relative paths against the
    # working dir, but Flask's send_from_directory resolves them against the app
    # root_path — a relative value would write and serve from different folders.
    REPORTS_DIR = os.path.abspath(os.environ.get("REPORTS_DIR", os.path.join(os.getcwd(), "reports")))
    UPLOADS_DIR = os.path.abspath(os.environ.get("UPLOADS_DIR", os.path.join(os.getcwd(), "uploads")))

    # ── Background worker ─────────────────────────────────────────────────────
    START_BACKGROUND_WORKER = _bool("START_BACKGROUND_WORKER", True)

    # ── Email (optional) ──────────────────────────────────────────────────────
    MAIL_ENABLED = _bool("MAIL_ENABLED", False)
    MAIL_SMTP_HOST = os.environ.get("MAIL_SMTP_HOST", "smtp.gmail.com")
    MAIL_SMTP_PORT = int(os.environ.get("MAIL_SMTP_PORT", 465))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_FROM = os.environ.get("MAIL_FROM", "")
    MAIL_DEFAULT_RECIPIENT = os.environ.get("MAIL_DEFAULT_RECIPIENT", "")

    # ── First admin (used by CLI / entrypoint) ────────────────────────────────
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

    # ── Tunisian regions (recipients are seeded for these) ────────────────────
    REGIONS = [
        "ARIANA", "BEJA", "BEN AROUS", "BIZERTE", "GABES", "GAFSA", "JENDOUBA",
        "KAIROUAN", "KASSERINE", "KEBILI", "KEF", "MAHDIA", "MANOUBA", "MEDENINE",
        "MONASTIR", "NABEUL", "SFAX", "SIDI BOUZID", "SILIANA", "SOUSSE",
        "TATAOUINE", "TOZEUR", "TUNIS", "ZAGHOUAN",
    ]

    # Bureau categories (derived from office name) for the depot/livraison filter.
    BUREAU_CATEGORIES = [
        ("agences", "Agences"),
        ("bureaux", "Bureaux"),
        ("centres", "Centres de distribution"),
    ]
    # (key, label, default-checked) — used by the Nouveau-rapport form.
    DEPOT_CATEGORIES = [("agences", "Agences", True), ("bureaux", "Bureaux", True),
                        ("centres", "Centres de distribution", True)]
    LIVRAISON_CATEGORIES = DEPOT_CATEGORIES
    DEPOT_COLUMNS = [("crbt", "CRBT", True), ("ca", "CA", True)]
    LIVRAISON_COLUMNS = [("dernier_e", "Dernier E", True),
                         ("taux_liv", "Taux livraison (%)", True),
                         ("intervalle", "Intervalle moyen (j)", True)]

    TESTING = False
    DEBUG = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)
    START_BACKGROUND_WORKER = False
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test-secret-key"


_CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None) -> type[BaseConfig]:
    """Resolve a config class from an explicit name or FLASK_ENV (default prod)."""
    name = (name or os.environ.get("FLASK_ENV", "production")).strip().lower()
    return _CONFIGS.get(name, ProductionConfig)
