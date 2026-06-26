"""Tests for per-region recipients, report filters, preview, and the send path."""


def login(client):
    return client.post("/login", data={"username": "admin", "password": "Admin123!"})


def test_new_report_page_lists_regions_and_recipient_inputs(client):
    login(client)
    body = client.get("/reports/new").get_data(as_text=True)
    assert "destinataire" in body.lower()
    assert 'name="email_SFAX"' in body
    assert 'name="regions" value="SFAX"' in body


def test_creating_job_persists_recipient_emails(client, app):
    login(client)
    resp = client.post("/reports/new", data={
        "regions": "SFAX", "include_depot": "on", "include_livraison": "on",
        "email_SFAX": "sfax-boss@laposte.tn",
    })
    assert resp.status_code == 302
    with app.app_context():
        from app.repositories import recipient_repository
        assert recipient_repository.email_map().get("SFAX") == "sfax-boss@laposte.tn"


def test_category_filter(app):
    from app.services import analytics_service
    with app.app_context():
        # Seeded: 2 "Agence Sfax" + 1 "Bureau Tunis"
        assert analytics_service.kpi_summary(categories=["agences"])["total_shipments"] == 2
        assert analytics_service.kpi_summary(categories=["bureaux"])["total_shipments"] == 1


def test_next_region_filter(app):
    from app.services import analytics_service
    with app.app_context():
        # All seeded rows have a blank next_region → "(VIDE)" matches all 3.
        assert analytics_service.kpi_summary(next_regions=["(VIDE)"])["total_shipments"] == 3
        assert analytics_service.kpi_summary(next_regions=["SFAX"])["total_shipments"] == 0


def test_preview_endpoint_returns_interactive_report(client):
    login(client)
    resp = client.post("/reports/preview", data={
        "regions": "SFAX", "include_depot": "on", "include_livraison": "on"})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "LA POSTE TUNISIENNE" in body
    assert "National — Dépôt" in body
    assert "National — Livraison" in body
    assert "MAILITM_FID" in body          # drill-down panel present
    assert "function drill" in body       # drill-down JS present


def test_depot_table_has_poids_and_ca_split(client):
    """The 'fixed tables' commit: Poids column + CA CRBT/Ordinaire KPI cards."""
    login(client)
    body = client.post("/reports/preview", data={
        "regions": "SFAX", "include_depot": "on"}).get_data(as_text=True)
    assert "Poids" in body          # new depot column
    assert "CA CRBT" in body        # depot KPI card
    assert "CA Ordinaire" in body   # depot KPI card


def test_report_has_export_and_import_sections(client):
    """National-vs-Export (Dépôt) and National-vs-Import (Livraison) comparison."""
    login(client)
    body = client.post("/reports/preview", data={
        "regions": "SFAX", "include_depot": "on", "include_livraison": "on"}).get_data(as_text=True)
    assert "National — Dépôt" in body
    assert "Export — Dépôt" in body
    assert "National — Livraison" in body
    assert "Import — Livraison" in body
    assert "KPIs Dépôt" in body
    assert "KPIs Livraison" in body


def test_no_duplicate_sections(client):
    """Each KPI block / table title must appear exactly once (no duplication)."""
    login(client)
    body = client.post("/reports/preview", data={
        "regions": "SFAX", "include_depot": "on", "include_livraison": "on"}).get_data(as_text=True)
    assert body.count("KPIs Dépôt") == 1
    assert body.count("KPIs Livraison") == 1
    assert body.count("National — Dépôt") == 1
    assert body.count("National — Livraison") == 1
    assert body.count("Export — Dépôt") == 1
    assert body.count("Import — Livraison") == 1


def test_section_toggle_excludes_block(client):
    login(client)
    # Depot only → Dépôt table present, Livraison table absent.
    body = client.post("/reports/preview", data={
        "regions": "SFAX", "include_depot": "on"}).get_data(as_text=True)
    assert "National — Dépôt" in body
    assert "National — Livraison" not in body
