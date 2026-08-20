"""Value coercion and number formatting."""

from __future__ import annotations

import pytest

from app.excel.model import ValueType
from app.excel.values import coerce, display_format, format_number, parse_number


@pytest.mark.parametrize("raw", ["#DIV/0!", "#N/A", "#REF!", "#VALUE!"])
def test_excel_errors_are_preserved_not_zeroed(raw: str) -> None:
    value_type, number, _text, error = coerce(raw)
    assert value_type is ValueType.ERROR
    assert number is None  # never silently becomes 0
    assert error == raw


@pytest.mark.parametrize(
    "raw",
    ["NA", "N/A", "n.a.", "n/d", "해당없음", "Not applicable", "sem dados", "-", "--", "–", "—"],
)
def test_na_variants_normalise_to_one_semantic_value(raw: str) -> None:
    """Every "no data" spelling becomes NA — and keeps its original text."""
    value_type, number, text, error = coerce(raw)
    assert value_type is ValueType.NA
    assert number is None and error is None
    assert text == raw  # rawValue is never rewritten


@pytest.mark.parametrize("raw", ["TBD", "?", "pending", "check", "0", "OK"])
def test_unknown_text_never_becomes_na(raw: str) -> None:
    """The NA vocabulary is a closed list: nothing else is promoted to NA."""
    assert coerce(raw)[0] is not ValueType.NA


def test_empty_and_text() -> None:
    assert coerce(None)[0] is ValueType.EMPTY
    assert coerce("   ")[0] is ValueType.EMPTY
    assert coerce("Excessive solder")[0] is ValueType.TEXT


@pytest.mark.parametrize(
    "raw,expected",
    [("3000", 3000.0), ("5,789", 5789.0), ("5.789,5", 5789.5), ("1,234.5", 1234.5), ("12,5", 12.5)],
)
def test_numbers_written_as_text(raw: str, expected: float) -> None:
    assert parse_number(raw) == expected


def test_numbers_keep_their_stored_value() -> None:
    value_type, number, _text, _error = coerce(3000)
    assert value_type is ValueType.NUMBER and number == 3000.0


def test_display_format_from_excel_number_format() -> None:
    integer = display_format("#,##0", ValueType.NUMBER)
    assert (integer.kind, integer.decimals, integer.thousands) == ("integer", 0, True)

    decimal = display_format("#,##0.0", ValueType.NUMBER)
    assert (decimal.kind, decimal.decimals) == ("decimal", 1)

    percent = display_format("0.00%", ValueType.NUMBER)
    assert (percent.kind, percent.decimals) == ("percent", 2)


def test_thousand_separator_is_presentation_only() -> None:
    fmt = display_format("#,##0", ValueType.NUMBER)
    assert format_number(3000, fmt) == "3,000"
    assert format_number(5789, fmt) == "5,789"
    # pt-BR rendering of the same untouched value
    assert format_number(5789, fmt, locale_group=".", locale_dec=",") == "5.789"


def test_percent_rendering() -> None:
    fmt = display_format("0.0%", ValueType.NUMBER)
    assert format_number(0.1336, fmt) == "13.4%"
