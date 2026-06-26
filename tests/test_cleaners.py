"""Unit tests for the import value cleaners."""
from datetime import datetime

from app.data_import import cleaners


def test_to_float_handles_comma_and_blanks():
    assert cleaners.to_float("4,3") == 4.3
    assert cleaners.to_float("1 234,5") == 1234.5
    assert cleaners.to_float(" ") is None
    assert cleaners.to_float("_") is None
    assert cleaners.to_float(7) == 7.0


def test_to_int():
    assert cleaners.to_int("3") == 3
    assert cleaners.to_int("3,0") == 3
    assert cleaners.to_int("nan") is None


def test_to_datetime_textual_and_blank():
    assert cleaners.to_datetime("Feb 11 2026 11:05") == datetime(2026, 2, 11, 11, 5)
    assert cleaners.to_datetime("X") is None
    assert cleaners.to_datetime(None) is None


def test_clean_str_vs_verbatim():
    assert cleaners.clean_str(" ") is None
    assert cleaners.clean_str("SFAX") == "SFAX"
    # EDI sentinel 'X' is kept verbatim
    assert cleaners.clean_str_verbatim("X") == "X"


def test_is_delivered_and_crbt():
    assert cleaners.is_delivered("Envoi Livré") is True
    assert cleaners.is_delivered("Recevoir envoi") is False
    assert cleaners.is_crbt("CRBT", None) is True
    assert cleaners.is_crbt("Ordinaire", 0) is False
    assert cleaners.is_crbt(None, 12.0) is True
