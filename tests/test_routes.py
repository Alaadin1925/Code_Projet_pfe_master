"""Route + analytics integration tests against the seeded test DB."""


def login(client):
    return client.post("/login", data={"username": "admin", "password": "Admin123!"},
                       follow_redirects=False)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_dashboard_requires_login(client):
    assert client.get("/").status_code == 302


def test_login_and_dashboard(client):
    assert login(client).status_code == 302
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Tableau de bord" in resp.get_data(as_text=True)


def test_kpis(app):
    from app.services import analytics_service
    with app.app_context():
        k = analytics_service.kpi_summary()
        assert k["total_shipments"] == 3
        assert k["delivered"] == 2
        assert k["delivery_rate"] == 66.7
        assert k["total_crbt_count"] == 1
        assert k["late_deliveries"] == 1   # interval_days 9 > 3


def test_region_scope(app):
    from app.services import analytics_service
    with app.app_context():
        assert analytics_service.kpi_summary("SFAX")["total_shipments"] == 2
        assert analytics_service.kpi_summary("TUNIS")["total_shipments"] == 1


def test_report_generation(app):
    import os
    from app.services import report_service
    with app.app_context():
        path = report_service.generate_region_report("SFAX")
        assert os.path.exists(path)
        assert os.path.getsize(path) > 500


def test_report_download_serves_generated_file(client, app):
    """Regression: a generated report must be downloadable — write and serve
    paths must resolve to the same folder (absolute REPORTS_DIR)."""
    import os
    login(client)
    with app.app_context():
        from app.services import report_service
        fname = os.path.basename(report_service.generate_region_report("SFAX"))
    resp = client.get(f"/reports/download/{fname}")
    assert resp.status_code == 200
    assert b"POSTE" in resp.data
