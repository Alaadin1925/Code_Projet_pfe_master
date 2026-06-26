"""Pytest fixtures — isolated app on a throwaway SQLite file."""
import os
import tempfile

import pytest

# Configure the test DB BEFORE the app/config modules are imported.
_TMP_DB = os.path.join(tempfile.gettempdir(), "lp_test_db.sqlite")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["TEST_DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["FLASK_ENV"] = "testing"

from app import create_app                       # noqa: E402
from app.config import TestingConfig             # noqa: E402
from app.extensions import db                    # noqa: E402
from app.models import NationalShipment, User    # noqa: E402


@pytest.fixture(scope="session")
def app():
    application = create_app(TestingConfig)
    with application.app_context():
        db.create_all()
        _seed()
    yield application
    with application.app_context():
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _seed():
    admin = User(username="admin", is_admin=True)
    admin.set_password("Admin123!")
    db.session.add(admin)
    db.session.add_all([
        NationalShipment(mailitm_fid="A1", depot_region="SFAX", depot_office="Agence Sfax",
                         last_event="Envoi Livré", is_delivered=True, shipment_type="Ordinaire",
                         revenue_ca=7, weight_kg=5, interval_days=2, deposit_year=2026, deposit_month=1),
        NationalShipment(mailitm_fid="A2", depot_region="SFAX", depot_office="Agence Sfax",
                         last_event="Recevoir envoi", is_delivered=False, shipment_type="CRBT",
                         is_crbt=True, crbt_amount=50, revenue_ca=5, weight_kg=12,
                         interval_days=9, deposit_year=2026, deposit_month=2),
        NationalShipment(mailitm_fid="A3", depot_region="TUNIS", depot_office="Bureau Tunis",
                         last_event="Envoi Livré", is_delivered=True, shipment_type="Ordinaire",
                         revenue_ca=6, weight_kg=1, interval_days=1, deposit_year=2026, deposit_month=2),
    ])
    db.session.commit()
