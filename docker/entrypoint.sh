#!/usr/bin/env bash
# Container entrypoint: wait for SQL Server, CREATE the target database if it does
# not exist, provision schema + admin + views, optionally import the national
# Excel, then start the WSGI server.
set -euo pipefail

echo "▶ Waiting for SQL Server and ensuring the database exists…"
# Connect to 'master' (always present), wait for readiness, then CREATE DATABASE
# if missing. The app DB (e.g. lp_national) does NOT exist on a fresh server.
START_BACKGROUND_WORKER=false python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"])
backend = url.get_backend_name()

# SQLite (local) needs no server/DB provisioning.
if backend.startswith("sqlite"):
    print("✔ SQLite backend — no server wait needed.")
    sys.exit(0)

target_db = url.database
if not target_db:
    print("✖ DATABASE_URL has no database name — set MSSQL_DB in .env.",
          file=sys.stderr)
    sys.exit(1)
master_url = url.set(database="master")

# 1. Wait for the server (connect to master).
engine = None
for attempt in range(1, 61):
    try:
        engine = create_engine(master_url, pool_pre_ping=True,
                               connect_args={"timeout": 5})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"✔ SQL Server reachable (attempt {attempt}).")
        break
    except Exception as exc:
        print(f"  …server not ready ({attempt}/60): {type(exc).__name__}")
        time.sleep(3)
else:
    print("✖ SQL Server never became reachable.", file=sys.stderr)
    sys.exit(1)

# 2. Create the target database if missing (autocommit — CREATE DATABASE cannot
#    run inside a transaction).
with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
    conn.execute(text(
        f"IF DB_ID(N'{target_db}') IS NULL CREATE DATABASE [{target_db}];"))
print(f"✔ Database '{target_db}' is ready.")
PY

echo "▶ Creating schema (idempotent)…"
START_BACKGROUND_WORKER=false flask init-db

echo "▶ Creating Power BI views (best effort)…"
START_BACKGROUND_WORKER=false flask create-views || echo "  (views skipped)"

if [ -n "${ADMIN_USERNAME:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  echo "▶ Ensuring admin user '${ADMIN_USERNAME}'…"
  START_BACKGROUND_WORKER=false flask create-admin || true
fi

if [ "${AUTO_IMPORT:-false}" = "true" ] && [ -f "${NATIONAL_XLSX_PATH:-/nonexistent}" ]; then
  echo "▶ Importing national + export + import…"
  START_BACKGROUND_WORKER=false flask import-all || echo "  (import failed — continue boot)"
fi

echo "▶ Starting web server on :${APP_PORT:-8000}"
exec python wsgi.py
