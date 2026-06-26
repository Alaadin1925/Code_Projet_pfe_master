"""Flask CLI commands.

    flask init-db                 # create tables (dev/quick start; prefer migrations in prod)
    flask create-admin            # create/update the first admin (from .env or flags)
    flask import-national         # load the national Excel file into SQL Server
    flask create-views            # (re)create the Power BI reporting views (SQL Server)
    flask db-stats                # quick row counts
"""
from __future__ import annotations

import os

import click
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy import text

from .extensions import db


def register_cli(app):
    app.cli.add_command(init_db)
    app.cli.add_command(create_admin)
    app.cli.add_command(import_national_cmd)
    app.cli.add_command(import_export_cmd)
    app.cli.add_command(import_import_cmd)
    app.cli.add_command(import_all_cmd)
    app.cli.add_command(create_views)
    app.cli.add_command(db_stats)


@click.command("init-db")
@with_appcontext
def init_db():
    """Create all tables (safe: only creates what's missing)."""
    db.create_all()
    click.echo("[OK] Tables created (db.create_all).")


@click.command("create-admin")
@click.option("--username", default=None, help="Admin username (default: ADMIN_USERNAME env).")
@click.option("--password", default=None, help="Admin password (default: ADMIN_PASSWORD env).")
@with_appcontext
def create_admin(username, password):
    """Create or update the first admin user."""
    from .repositories import user_repository

    username = username or current_app.config.get("ADMIN_USERNAME")
    password = password or current_app.config.get("ADMIN_PASSWORD")
    if not username or not password:
        raise click.ClickException(
            "Provide --username/--password or set ADMIN_USERNAME/ADMIN_PASSWORD in .env.")
    _user, created = user_repository.upsert_admin(username, password)
    click.echo(f"[OK] Admin '{username}' {'created' if created else 'updated'}.")


@click.command("import-national")
@click.option("--path", default=None, help="Path to the national .xlsx (default: NATIONAL_XLSX_PATH).")
@click.option("--sheet", default=None, help="Sheet name (default: NATIONAL_SHEET_NAME).")
@with_appcontext
def import_national_cmd(path, sheet):
    """Import the national Excel data into SQL Server (idempotent upsert)."""
    from .data_import import import_national

    entry = import_national(path=path, sheet=sheet)
    click.echo(f"[{entry.status}] {entry.message}")
    click.echo(f"   read={entry.rows_read} inserted={entry.rows_inserted} "
               f"updated={entry.rows_updated} skipped={entry.rows_skipped}")
    if entry.status != "success":
        raise click.ClickException("Import did not succeed — see message above.")


@click.command("import-export")
@with_appcontext
def import_export_cmd():
    """Import the 'export' sheet into SQL Server (idempotent upsert)."""
    from .data_import import import_export
    entry = import_export()
    click.echo(f"[{entry.status}] {entry.message}")
    if entry.status != "success":
        raise click.ClickException("Export import did not succeed.")


@click.command("import-import")
@with_appcontext
def import_import_cmd():
    """Import import.xls into SQL Server (idempotent upsert)."""
    from .data_import import import_import
    entry = import_import()
    click.echo(f"[{entry.status}] {entry.message}")
    if entry.status != "success":
        raise click.ClickException("Import import did not succeed.")


@click.command("import-all")
@with_appcontext
def import_all_cmd():
    """Import national + export + import (best effort per source)."""
    from .data_import import import_export, import_import, import_national
    for label, fn in (("national", import_national), ("export", import_export),
                      ("import", import_import)):
        try:
            entry = fn()
            click.echo(f"  {label:9s}: [{entry.status}] {entry.message}")
        except Exception as exc:
            click.echo(f"  {label:9s}: [error] {exc}")


@click.command("create-views")
@click.option("--file", "sql_file", default=None, help="Path to views .sql (default: sql/02_views.sql).")
@with_appcontext
def create_views(sql_file):
    """Create/refresh the Power BI reporting views (SQL Server only)."""
    if not db.engine.url.get_backend_name().startswith("mssql"):
        raise click.ClickException(
            "create-views targets SQL Server (T-SQL). Current DB is "
            f"'{db.engine.url.get_backend_name()}'. Skipping.")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sql_file = sql_file or os.path.join(root, "sql", "02_views.sql")
    if not os.path.exists(sql_file):
        raise click.ClickException(f"SQL file not found: {sql_file}")

    with open(sql_file, encoding="utf-8") as fh:
        script = fh.read()

    # Split on standalone GO batch separators (T-SQL).
    batches = []
    current = []
    for line in script.splitlines():
        if line.strip().upper() == "GO":
            batches.append("\n".join(current))
            current = []
        else:
            current.append(line)
    if current:
        batches.append("\n".join(current))

    applied = 0
    for batch in batches:
        stmt = batch.strip()
        if not stmt or stmt.startswith("/*") and stmt.endswith("*/"):
            continue
        db.session.execute(text(stmt))
        applied += 1
    db.session.commit()
    click.echo(f"[OK] Applied {applied} SQL batch(es) from {os.path.basename(sql_file)}.")


@click.command("db-stats")
@with_appcontext
def db_stats():
    """Print quick table row counts."""
    from .models import (ExportShipment, ImportLog, ImportShipment,
                         NationalShipment, ReportJob, User)

    for model in (User, NationalShipment, ExportShipment, ImportShipment,
                  ReportJob, ImportLog):
        count = db.session.query(model).count()
        click.echo(f"  {model.__tablename__:24s}: {count}")
