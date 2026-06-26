"""Value cleaning / type coercion for the national import.

All converters are null-safe and never raise: a value that cannot be parsed
becomes ``None`` so a single bad cell never aborts the whole import.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

# Tokens that mean "no value" in the source spreadsheet.
_BLANK_TOKENS = {"", "nan", "none", "null", "nat", "_", "·", "(blank)", "(vide)"}


def clean_str(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in _BLANK_TOKENS:
        return None
    return s


def clean_str_verbatim(value: object) -> str | None:
    """Like clean_str but keeps the EDI sentinel 'X' (only true blanks → None)."""
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "null", "nat"}:
        return None
    return s


def to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if pd.isna(value) else float(value)
    s = str(value).strip().replace(" ", "")
    if s.lower() in _BLANK_TOKENS:
        return None
    s = s.replace(",", ".")  # French decimal comma → dot
    try:
        return float(s)
    except ValueError:
        return None


def to_int(value: object) -> int | None:
    f = to_float(value)
    if f is None:
        return None
    try:
        return int(round(f))
    except (ValueError, OverflowError):
        return None


def to_datetime(value: object) -> datetime | None:
    """Parse Excel datetimes and free-text dates like 'Feb 11 2026 11:05'."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    # A bare number (Excel serial that lost its date format, or a stray numeric
    # cell) would be misread by pandas as nanoseconds-since-epoch → a bogus 1970
    # date. We cannot tell a serial from junk, so drop it rather than corrupt data.
    if isinstance(value, (bool, int, float)):
        return None
    if isinstance(value, str) and value.strip().lower() in _BLANK_TOKENS:
        return None
    ts = pd.to_datetime(value, errors="coerce", dayfirst=False)
    if pd.isna(ts):
        ts = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()


def is_delivered(last_event: str | None) -> bool:
    """National delivery flag — derived from 'Dernier E' (NOT from EDI fields,
    which are the placeholder 'X' for national shipments)."""
    if not last_event:
        return False
    return last_event.strip().lower().startswith("envoi liv")


def is_crbt(shipment_type: str | None, crbt_amount: float | None) -> bool:
    if shipment_type and shipment_type.strip().upper() == "CRBT":
        return True
    return bool(crbt_amount and crbt_amount > 0)
