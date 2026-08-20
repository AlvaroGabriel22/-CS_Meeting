"""Value coercion: raw Excel values -> normalized (type, number, text, error).

Rules that matter for the quality reports:

* ``#DIV/0!`` and friends are *preserved* as errors, never turned into 0.
* an explicit ``NA`` typed by the analyst is a first-class value, not text and
  not a missing cell.
* numbers are stored exactly as they came; formatting is a display hint only.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .model import DEFAULT_FORMAT, DisplayFormat, ValueType

EXCEL_ERRORS = {
    "#DIV/0!",
    "#N/A",
    "#NAME?",
    "#NULL!",
    "#NUM!",
    "#REF!",
    "#VALUE!",
    "#SPILL!",
    "#CALC!",
    "#GETTING_DATA",
}

#: Strings the analysts use to mean "no data for this slot".  A **closed list**
#: on purpose (ADR-0013): unknown text is never promoted to NA, and the original
#: is always kept in ``rawValue``.
NA_TOKENS = {
    # explicit
    "na",
    "n/a",
    "n.a.",
    "n.a",
    "n/d",
    "n.d.",
    "nd",
    # dashes used as "nothing to report"
    "-",
    "--",
    "---",
    "\u2010",  # hyphen
    "\u2013",  # en dash
    "\u2014",  # em dash
    "\u2015",  # horizontal bar
    # spelled out
    "not applicable",
    "no data",
    "nao aplicavel",
    "não aplicável",
    "nao ha dados",
    "sem dados",
    "해당없음",
    "해당 없음",
    "없음",
}

_NUMERIC_RE = re.compile(
    r"""^[+-]?(
        \d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?   # 1,234,567.89 / 1.234.567,89
        | \d+(?:[.,]\d+)?                      # 1234.56
    )\s*%?$""",
    re.VERBOSE,
)


def is_error_value(value: Any) -> bool:
    return isinstance(value, str) and value.strip().upper() in EXCEL_ERRORS


def is_na_value(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in NA_TOKENS


def parse_number(text: str) -> float | None:
    """Parse a number written as text, tolerating pt-BR and en-US separators."""
    raw = text.strip().replace(" ", " ")
    if not raw or not _NUMERIC_RE.match(raw):
        return None
    percent = raw.endswith("%")
    raw = raw.rstrip("%").strip().replace(" ", "")
    if "," in raw and "." in raw:
        # the right-most separator is the decimal one
        dec = "," if raw.rfind(",") > raw.rfind(".") else "."
        thou = "." if dec == "," else ","
        raw = raw.replace(thou, "").replace(dec, ".")
    elif "," in raw:
        # a single comma: decimal separator unless it groups thousands (1,234)
        left, _, right = raw.rpartition(",")
        raw = raw.replace(",", "") if len(right) == 3 and left else raw.replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return value / 100.0 if percent else value


def coerce(value: Any) -> tuple[ValueType, float | None, str | None, str | None]:
    """Return ``(value_type, number, text, error_code)`` for a raw Excel value."""
    if value is None:
        return ValueType.EMPTY, None, None, None
    if isinstance(value, bool):
        return ValueType.BOOL, 1.0 if value else 0.0, str(value).upper(), None
    if isinstance(value, (int, float)):
        return ValueType.NUMBER, float(value), None, None
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return ValueType.DATE, None, value.isoformat(), None
    text = str(value).strip()
    if not text:
        return ValueType.EMPTY, None, None, None
    if is_error_value(text):
        return ValueType.ERROR, None, text.upper(), text.upper()
    if is_na_value(text):
        return ValueType.NA, None, text, None
    number = parse_number(text)
    if number is not None:
        return ValueType.NUMBER, number, text, None
    return ValueType.TEXT, None, text, None


# --------------------------------------------------------------------------- #
# Display format derived from the Excel number format
# --------------------------------------------------------------------------- #
_CURRENCY_SIGNS = {"R$": "BRL", "$": "USD", "€": "EUR", "£": "GBP", "₩": "KRW", "¥": "JPY"}


def display_format(number_format: str | None, value_type: ValueType) -> DisplayFormat:
    """Translate an Excel number format into a renderer-agnostic hint.

    The stored value is never touched — the frontend decides how to print it
    (``3000`` -> ``3,000``) from this hint.
    """
    if value_type is not ValueType.NUMBER:
        return DEFAULT_FORMAT
    fmt = (number_format or "").strip()
    if not fmt or fmt.lower() == "general":
        return DEFAULT_FORMAT

    section = fmt.split(";")[0]
    currency = next((code for sign, code in _CURRENCY_SIGNS.items() if sign in section), None)
    decimals = 0
    if "." in section:
        tail = section.split(".", 1)[1]
        decimals = len(re.match(r"[0#]*", tail).group(0))
    thousands = "," in re.sub(r"\[[^\]]*\]", "", section).split(".")[0]

    if "%" in section:
        return DisplayFormat(kind="percent", decimals=decimals, thousands=thousands)
    if currency:
        return DisplayFormat(kind="currency", decimals=decimals or 2, thousands=True, currency=currency)
    if "@" in section:
        return DisplayFormat(kind="text", thousands=False)
    kind = "integer" if decimals == 0 else "decimal"
    return DisplayFormat(kind=kind, decimals=decimals, thousands=thousands or decimals == 0)


def format_number(value: float, fmt: DisplayFormat, locale_group: str = ",", locale_dec: str = ".") -> str:
    """Reference implementation of the display rule (mirrored on the frontend).

    Used by the PDF/PPT exporters so that a value looks the same everywhere.
    """
    if fmt.kind == "percent":
        value = value * 100.0
    decimals = fmt.decimals
    if decimals is None:
        decimals = 0 if float(value).is_integer() else 2
    text = f"{abs(value):,.{decimals}f}" if fmt.thousands else f"{abs(value):.{decimals}f}"
    text = text.replace(",", "\x00").replace(".", locale_dec).replace("\x00", locale_group)
    sign = "-" if value < 0 else ""
    if fmt.kind == "percent":
        return f"{sign}{text}%"
    if fmt.kind == "currency" and fmt.currency:
        return f"{sign}{fmt.currency} {text}"
    return f"{sign}{text}"
