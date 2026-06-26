# La Poste Tunisienne — National Reporting Platform

A clean, professional Flask application for analyzing **national** postal shipments
(Tunisia → Tunisia) and serving the data to **Power BI** through **SQL Server**.

> Refactor of the original Power-BI-scraping prototype into a maintainable,
> SQL-first architecture suitable for a master/PFE defense.

---

## 🚀 Quick start with Docker Desktop (Windows)

Run the whole stack (Flask app + SQL Server) with one command — no Python or SQL
Server install needed, just **Docker Desktop**.

1. **Install Docker Desktop** for Windows and **start it** (wait until the whale
   icon says *Engine running*). Verify in a terminal:
   ```bash
   docker --version
   docker compose version
   ```

2. **Get the project** and enter the folder:
   ```bash
   git clone https://github.com/Alaadin1925/Code_Projet_pfe_master.git
   cd Code_Projet_pfe_master
   ```

3. **Create your `.env`** from the template and edit the values:
   ```bash
   cp .env.example .env
   ```
   At minimum set: `SECRET_KEY`, `MSSQL_SA_PASSWORD` (strong: upper+lower+digit+symbol),
   `ADMIN_PASSWORD`. For email, set `MAIL_ENABLED=true` + `MAIL_USERNAME` /
   `MAIL_PASSWORD` (Gmail **App Password**) / `MAIL_FROM`.

4. **Put the data files** in the `data/` folder (mounted into the container):
   ```
   data/depot2026_nettoye.xlsx     ← workbook with 'national' + 'export' sheets
   data/import.xls                 ← import shipments
   ```
   (Set `AUTO_IMPORT=true` in `.env` to load them automatically on first boot.)

5. **Build & start** (first run pulls the SQL Server image, ~1.5 GB):
   ```bash
   docker compose up -d --build
   docker compose logs -f app        # watch boot: DB created → schema → admin → server
   ```

6. **Load the data** into SQL Server (skip if `AUTO_IMPORT=true`):
   ```bash
   docker compose exec app flask import-all      # national + export + import
   docker compose exec app flask create-views    # Power BI views
   ```

7. **Open the app:** <http://localhost:8000> — log in with `admin` / your `ADMIN_PASSWORD`.

8. **Manage the stack:**
   ```bash
   docker compose ps          # status
   docker compose stop        # stop (keeps data)
   docker compose up -d       # start again
   docker compose down        # remove containers (keeps the DB volume)
   docker compose down -v     # remove containers + WIPE the database volume
   ```

> **Port already in use?** Set `APP_HOST_PORT=8080` (or any free port) in `.env`,
> then `docker compose up -d`. SQL Server is on `localhost,1433` (connect with SSMS:
> login `sa`, your `MSSQL_SA_PASSWORD`, *Trust server certificate* = yes).

---

## 1. Overview

- **Data sources:** the parcel workbook (`national` + `export` sheets) and
  `import.xls`, loaded into SQL Server. Reports compare **National vs Export**
  (Dépôt) and **National vs Import** (Livraison).
- **Database:** **SQL Server** (single source of truth), accessed via SQLAlchemy.
- **Web app:** Flask (application-factory + blueprints), with
  - a **KPI dashboard** (shipments, revenue/CA, CRBT, delivery rate, intervals,
    by region/office, failures, monthly evolution, weight, late deliveries),
  - **ML clustering** analytics (5 unsupervised analyses, scikit-learn),
  - **report generation** (downloadable HTML, optional email),
  - **auth** (hashed passwords, CSRF, secure sessions).
- **BI:** Power BI connects **directly to SQL Server** via ready-made `vw_*` views.
- **Deployment:** Docker Compose (Flask app + SQL Server + persistent volume).

The old approach scraped a live Power BI report with Playwright. That fragile path
was **removed**: SQL Server is now the source, and Power BI consumes it. See
[`SECURITY.md`](SECURITY.md) for the leaked-credential rotation you must perform.

---

## 2. Architecture

```
                 ┌──────────────────────────────────────────────┐
 national.xlsx ─▶│  import pipeline (clean + upsert by FID)      │
                 └───────────────────────┬──────────────────────┘
                                         ▼
                          ┌───────────────────────────┐         ┌────────────┐
                          │        SQL Server          │◀────────│  Power BI  │
                          │  national_shipments + vw_* │  views  │  Desktop   │
                          └─────────────▲──────────────┘         └────────────┘
                                        │ SQLAlchemy
   HTTP        ┌───────────┐   service  │  repository
 ─────────────▶│ blueprint │──────────▶ service ──────▶ repository ──▶ models
   (browser)   │  (routes) │   layer            (business)     (DB access)
               └───────────┘
                     │
                     ├─ dashboard  (KPIs, charts)
                     ├─ analytics  (ML clustering)
                     ├─ reports    (jobs → HTML, optional email)
                     └─ auth / health
```

**Layering rule:** `route → service → repository → model`.
No SQL in routes, no business logic in repositories, no Flask in services.

---

## 3. Folder structure

```
.
├── app/
│   ├── __init__.py            # application factory
│   ├── config.py              # env-based config (no secrets in code)
│   ├── extensions.py          # db, migrate, login_manager, csrf
│   ├── cli.py                 # flask init-db / create-admin / import-national / create-views
│   ├── models/                # users, profiles, national_shipments, report_jobs,
│   │                          #   generated_reports, import_logs
│   ├── repositories/          # DB access only (queries)
│   ├── services/              # analytics, clustering, report, mail (business logic)
│   ├── data_import/           # column_mapping, cleaners, importer (Excel → SQL)
│   ├── blueprints/            # auth, dashboard, reports, analytics, health (thin routes)
│   ├── reports/               # HTML report builder
│   ├── jobs/                  # background worker (report queue)
│   ├── templates/  static/    # Jinja templates + CSS
├── sql/
│   ├── 01_schema.sql          # SSMS-manageable schema (mirrors the ORM)
│   └── 02_views.sql           # Power BI views (vw_*)
├── docker/entrypoint.sh       # wait-for-db → migrate → admin → (import) → serve
├── Dockerfile  docker-compose.yml  .dockerignore
├── requirements.txt  wsgi.py
├── .env.example  .gitignore  .gitattributes
└── README.md  SECURITY.md
```

---

## 4. Environment variables (`.env`)

Copy `.env.example` → `.env` and fill in. Key variables:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask secret (**required**). `python -c "import secrets;print(secrets.token_hex(32))"` |
| `FLASK_ENV` | `production` / `development` / `testing` |
| `APP_PORT` | Port the app listens on (default 8000). On a local run, auto-falls back to the next free port if busy (set `APP_PORT_STRICT=true` to fail instead). |
| `APP_HOST_PORT` | Docker host port mapped to the container's 8000 (default 8000). Change it if 8000 is taken on your host. |
| `DATABASE_URL` | SQLAlchemy URL (SQL Server via pyodbc, or `sqlite:///local_dev.db` for dev) |
| `MSSQL_SA_PASSWORD`, `MSSQL_DB` | Used by the docker-compose `db` service |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | First admin (used by `flask create-admin`) |
| `NATIONAL_XLSX_PATH` | Path to the national `.xlsx` (host path or `/data/...` in Docker) |
| `NATIONAL_SHEET_NAME` / `NATIONAL_HEADER_ROW` | `national` / `2` (header on 3rd row) |
| `REPORTS_DIR`, `UPLOADS_DIR` | Output / upload folders |
| `MAIL_ENABLED` + `MAIL_*` | Optional per-region emailing (off by default) |
| `AUTO_IMPORT` | If `true`, the container imports the mounted Excel on first boot |

---

## 5. Run locally (without Docker)

Quick dev run against SQLite (no SQL Server needed):

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows  (source .venv/bin/activate on Linux/macOS)
pip install -r requirements.txt

cp .env.example .env              # set SECRET_KEY; set DATABASE_URL=sqlite:///local_dev.db
export FLASK_APP=wsgi.py          # ($env:FLASK_APP="wsgi.py" in PowerShell)

flask init-db                     # create tables
flask create-admin                # uses ADMIN_USERNAME/ADMIN_PASSWORD from .env
flask import-national             # load the national Excel into the DB
python wsgi.py                    # serve on http://localhost:8000
```

To run against a real SQL Server locally, set `DATABASE_URL` to the `mssql+pyodbc://…`
form (requires the **ODBC Driver 18 for SQL Server** installed on your machine).

---

## 6. Run with Docker (recommended)

```bash
cp .env.example .env              # set SECRET_KEY, MSSQL_SA_PASSWORD, ADMIN_PASSWORD
cp /path/to/depot2026_nettoye.xlsx ./data/   # mounted read-only at /data

docker compose up -d --build      # starts SQL Server + the app
docker compose logs -f app        # watch boot (waits for DB, creates schema/admin/views)
```

App: <http://localhost:8000> · SQL Server: `localhost,1433` (sa / `MSSQL_SA_PASSWORD`).

Import the data (or set `AUTO_IMPORT=true` to do it on boot):

```bash
docker compose exec app flask import-national
docker compose exec app flask create-views   # (re)create Power BI views
```

Stop / reset:

```bash
docker compose down               # stop (keeps data volume)
docker compose down -v            # stop + delete the SQL Server volume
```

---

## 7. Import the national Excel

The importer reads **only** the `national` sheet (header on the 3rd row),
normalizes the 33 French columns to clean English names, converts dates/numbers,
handles blanks, and **upserts by `MAILITM_FID`** (re-running never duplicates).
Every run is logged in `import_logs`.

```bash
flask import-national     # national sheet  → national_shipments
flask import-export       # export sheet    → export_shipments
flask import-import       # import.xls      → import_shipments
flask import-all          # all three at once
```

The report is a **National-vs-Export** (Dépôt) and **National-vs-Import** (Livraison)
comparison, so all three sources are loaded into SQL Server (set `AUTO_IMPORT=true`
to import them on first container boot).

Original-header → clean-column mapping lives in
[`app/data_import/column_mapping.py`](app/data_import/column_mapping.py).

---

## 8. Connect with SSMS

1. **Server name:** `localhost,1433` (or your host) · **Login:** `sa` ·
   **Password:** your `MSSQL_SA_PASSWORD`.
2. If you get a certificate error, enable **Trust server certificate** in the
   connection options.
3. Database: **`lp_national`**. Browse `dbo.national_shipments` and the `dbo.vw_*` views.
4. To provision the schema manually instead of via the app, run
   [`sql/01_schema.sql`](sql/01_schema.sql) then [`sql/02_views.sql`](sql/02_views.sql).

---

## 9. Power BI → SQL Server

1. Power BI Desktop → **Get Data → SQL Server**.
2. Server `localhost,1433` (or host), Database `lp_national`.
3. Prefer **Import** mode; pick the reporting views:
   - `vw_national_shipments_clean` — flat fact table (one row per parcel)
   - `vw_kpi_national` — headline KPIs
   - `vw_shipments_by_region`, `vw_shipments_by_month`
   - `vw_delivery_status`, `vw_failure_causes`
4. Build visuals on the views (they already contain clean English columns and
   derived fields like `delivery_status`). Schedule refresh as needed.

> Note: for national data, **failure cause = last delivery event (`Dernier E`)** of
> non-delivered parcels — the `EDI_*` columns are the placeholder `'X'` and are not used.

---

## 9b. Reports & per-region email

The **Rapports → Nouveau rapport** page (original design) lets you:
- pick **Dépôt** / **Livraison** sections, the **bureau-category** filters + columns, and a **Region Next** filter;
- select regions and set a **recipient email per region** (saved in `region_recipients`; blank = `MAIL_DEFAULT_RECIPIENT`);
- **Aperçu** to preview the full interactive report, and **Lancer le rapport** to queue it.

A background worker generates one **interactive HTML report** per region (downloadable from the job page) and,
if email is enabled, sends each to its recipient (branded email + the report attached). Each report contains:
- KPI cards (taux de livraison, délai moyen, total colis, CA),
- a **Dépôt** table (Bureau dépôt × CRBT × CA × Nb IDs) and a **Livraison** pivot (Bureau Dernier E × événements × Total/CRBT/Ordinaire/CA),
- **click-to-drill**: click any cell to list the underlying `MAILITM_FID`s,
- a **Date Dernier E** range slider that rebuilds the livraison table client-side.

The **Clustering** page renders the 5 scikit-learn analyses with Chart.js charts (same as the original).

**Enable sending** — set in `.env`, then `docker compose up -d`:
```
MAIL_ENABLED=true
MAIL_SMTP_HOST=smtp.gmail.com
MAIL_SMTP_PORT=465
MAIL_USERNAME=you@gmail.com
MAIL_PASSWORD=your-gmail-app-password      # Google → Security → App passwords
MAIL_FROM=you@gmail.com
MAIL_DEFAULT_RECIPIENT=fallback@example.com
```
With `MAIL_ENABLED=false` (default), reports are still generated — the job log notes that email was skipped.

## 10. SSIS (optional, later)

You don't need SSIS today — `flask import-national` covers ingestion. When you want
a managed ETL or a data-warehouse split, SSIS fits naturally:

- **Excel → staging:** an *Excel Source* (national sheet, header row 3) → *Data
  Conversion* → *OLE DB Destination* into a `staging.national_shipments` table.
- **Idempotent load:** a *Lookup* on `MAILITM_FID` to split insert vs. update
  (or a `MERGE` in an *Execute SQL Task*) — mirrors the app's upsert.
- **Operational → warehouse:** schedule a package (SQL Agent) to move/transform
  `national_shipments` into a star schema (fact + date/region/office dimensions).

Keep packages minimal; the views in `sql/02_views.sql` already provide a clean
reporting layer for Power BI without a warehouse.

---

## 11. Create the first admin user

```bash
flask create-admin                                  # from ADMIN_USERNAME/ADMIN_PASSWORD
flask create-admin --username boss --password 'S3cret!'   # explicit
```

(Re-running updates the password and ensures the user is an admin.)

---

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| `SECRET_KEY is not set` on boot | Set `SECRET_KEY` in `.env`. |
| `Can't open lib 'ODBC Driver 18 for SQL Server'` | Install **msodbcsql18** (it's preinstalled in the Docker image; locally install the MS ODBC driver). |
| Login certificate / SSL error to SQL Server | Add `TrustServerCertificate=yes` to `DATABASE_URL` (already in the templates). |
| App starts before DB ready (Docker) | The entrypoint polls the DB for ~120s; check `docker compose logs db`. |
| `MSSQL_SA_PASSWORD` rejected by SQL Server | Use a strong password (≥8 chars, upper+lower+digit+symbol). |
| Dashboard shows "Aucune donnée" | Run `flask import-national`. |
| Unicode error in Windows console | Run with `set PYTHONUTF8=1` (the app/CLI output is ASCII-safe anyway). |
| `create-views` skipped on SQLite | Views are T-SQL; they apply only on SQL Server. |
| Port 8000 already in use (local) | The app auto-falls back to the next free port and logs it; or set `APP_PORT`. Set `APP_PORT_STRICT=true` to fail instead. |
| Port 8000 already in use (Docker) | Set `APP_HOST_PORT` (e.g. `8080`) in `.env` and `docker compose up -d`. |
| Dashboard 500 on SQL Server | Ensure you're on the current code (boolean filters use `= 1`, not `IS 1`) and views are created via `flask create-views`. |

---

## 13. Tech stack

Flask · Flask-SQLAlchemy · Flask-Migrate · Flask-Login · Flask-WTF ·
SQLAlchemy + pyodbc · SQL Server 2022 · pandas/openpyxl · scikit-learn/scipy ·
Waitress · Docker / Docker Compose · Power BI.
