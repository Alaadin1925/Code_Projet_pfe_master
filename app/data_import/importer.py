"""Idempotent Excel → SQL import pipeline (national / export / import).

Reads a sheet, normalizes column names, converts dates/numbers, handles missing
values, deduplicates by MAILITM_FID, and upserts into the target table. Every run
is recorded in ``import_logs``. Safe to re-run (existing parcels updated).
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
from flask import current_app

from ..extensions import db
from ..models import ExportShipment, ImportShipment, NationalShipment, ImportLog
from ..models.import_log import IMPORT_FAILED, IMPORT_SUCCESS
from . import cleaners
from .column_mapping import (COLUMN_MAP, EDI_VERBATIM_ATTRS,
                             build_header_lookup)

log = logging.getLogger(__name__)
_CHUNK = 1000


def _convert_row(row: pd.Series, header_lookup: dict[str, str]) -> dict | None:
    rec: dict = {}
    for excel_header, attr, kind in COLUMN_MAP:
        actual = header_lookup.get(excel_header)
        raw = row[actual] if actual is not None else None
        if kind == "str":
            rec[attr] = (cleaners.clean_str_verbatim(raw)
                         if attr in EDI_VERBATIM_ATTRS else cleaners.clean_str(raw))
        elif kind == "int":
            rec[attr] = cleaners.to_int(raw)
        elif kind == "float":
            rec[attr] = cleaners.to_float(raw)
        elif kind == "datetime":
            rec[attr] = cleaners.to_datetime(raw)

    if not rec.get("mailitm_fid"):
        return None

    month = rec.get("deposit_month")
    if month is not None and not (1 <= month <= 12):
        rec["deposit_month"] = None
    year = rec.get("deposit_year")
    if year is not None and not (1900 <= year <= 9999):
        rec["deposit_year"] = None

    rec["is_delivered"] = cleaners.is_delivered(rec.get("last_event"))
    rec["is_crbt"] = cleaners.is_crbt(rec.get("shipment_type"), rec.get("crbt_amount"))
    return rec


def _run_import(model, path, sheet, header_row, batch_id) -> ImportLog:
    entry = ImportLog(batch_id=batch_id, source_file=path, sheet_name=str(sheet))
    db.session.add(entry)
    db.session.commit()

    if not path:
        return _fail(entry, f"Path not configured for {model.__tablename__}.")

    try:
        log.info("Reading %s [sheet=%s header=%s] → %s", path, sheet, header_row, model.__tablename__)
        df = pd.read_excel(path, sheet_name=sheet, header=header_row, dtype=object)
    except Exception as exc:
        return _fail(entry, f"Failed to read Excel: {exc}")

    entry.rows_read = len(df)
    header_lookup = build_header_lookup(df.columns)
    if "MAILITM_FID" not in header_lookup:
        return _fail(entry, "MAILITM_FID column not found — wrong sheet/header row?")

    # Keep EVERY source row (no MAILITM_FID dedup) so report counts match the
    # source exactly — a FID can repeat across bureaux/events.
    records: list[dict] = []
    skipped = 0
    now = datetime.utcnow()
    for _, row in df.iterrows():
        rec = _convert_row(row, header_lookup)
        if rec is None:
            skipped += 1
            continue
        rec["import_batch"] = batch_id
        rec["created_at"] = now
        rec["updated_at"] = now
        records.append(rec)

    try:
        # Full reload: clear this source's table, then bulk-insert all rows.
        # Idempotent (re-running yields the same data) and transactional.
        db.session.query(model).delete()
        for i in range(0, len(records), _CHUNK):
            db.session.bulk_insert_mappings(model, records[i:i + _CHUNK])
            db.session.flush()

        entry.rows_inserted = len(records)
        entry.rows_updated = 0
        entry.rows_skipped = skipped
        entry.status = IMPORT_SUCCESS
        entry.message = f"OK — full reload: {len(records)} rows loaded, {skipped} skipped."
        entry.finished_at = datetime.utcnow()
        db.session.commit()
        log.info("[%s] %s", model.__tablename__, entry.message)
        return entry
    except Exception as exc:
        db.session.rollback()
        return _fail(entry, f"Load failed: {exc}")


def import_national(path=None, sheet=None, header_row=None, batch_id=None) -> ImportLog:
    cfg = current_app.config
    return _run_import(
        NationalShipment,
        path or cfg.get("NATIONAL_XLSX_PATH"),
        sheet or cfg.get("NATIONAL_SHEET_NAME", "national"),
        cfg.get("NATIONAL_HEADER_ROW", 2) if header_row is None else header_row,
        batch_id or datetime.utcnow().strftime("nat_%Y%m%d_%H%M%S"))


def import_export(path=None, sheet=None, header_row=None, batch_id=None) -> ImportLog:
    cfg = current_app.config
    return _run_import(
        ExportShipment,
        path or cfg.get("NATIONAL_XLSX_PATH"),  # export lives in the same workbook
        sheet or cfg.get("EXPORT_SHEET_NAME", "export"),
        cfg.get("EXPORT_HEADER_ROW", 2) if header_row is None else header_row,
        batch_id or datetime.utcnow().strftime("exp_%Y%m%d_%H%M%S"))


def import_import(path=None, sheet=None, header_row=None, batch_id=None) -> ImportLog:
    cfg = current_app.config
    return _run_import(
        ImportShipment,
        path or cfg.get("IMPORT_XLS_PATH"),
        0 if sheet is None else sheet,  # import.xls: first sheet
        cfg.get("IMPORT_HEADER_ROW", 0) if header_row is None else header_row,
        batch_id or datetime.utcnow().strftime("imp_%Y%m%d_%H%M%S"))


def _fail(entry: ImportLog, message: str) -> ImportLog:
    log.error(message)
    entry.status = IMPORT_FAILED
    entry.message = message
    entry.finished_at = datetime.utcnow()
    db.session.add(entry)
    db.session.commit()
    return entry
