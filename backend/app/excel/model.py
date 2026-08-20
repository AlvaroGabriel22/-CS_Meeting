"""Normalized table model.

This module defines the representation the whole system works with *after* an
Excel file has been imported.  Nothing downstream (charts, exports, UI) is
allowed to depend on openpyxl or on Excel coordinates: the coordinates are kept
only as *provenance* metadata (debug / traceability), never as business rules.

See docs/data-model.md and docs/excel-parser.md for the rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class ValueType(str, Enum):
    """What the cell *contains* (independent of its role in the table)."""

    EMPTY = "empty"
    NUMBER = "number"
    TEXT = "text"
    DATE = "date"
    BOOL = "bool"
    ERROR = "error"  # #DIV/0!, #REF!, ...
    NA = "na"  # explicit "NA" / "N/A" written by the analyst


class CellRole(str, Enum):
    """What the cell *is* inside the detected table."""

    HEADER = "header"  # part of the header band (periods, groups, series)
    LABEL = "label"  # row label / category column
    VALUE = "value"  # actual data point
    EMPTY = "empty"


class SemanticType(str, Enum):
    """What a cell / row / column *means*, independent of where it sits."""

    TITLE = "title"
    PERIOD = "period"
    SERIES = "series"
    CATEGORY = "category"
    SUBCATEGORY = "subcategory"
    METRIC = "metric"
    VALUE = "value"
    LABEL = "label"
    UNKNOWN = "unknown"


class PeriodKind(str, Enum):
    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"
    UNKNOWN = "unknown"


class PeriodAxis(str, Enum):
    """Which axis of the table carries the time dimension."""

    COLUMNS = "columns"
    ROWS = "rows"
    NONE = "none"


class TableShape(str, Enum):
    MATRIX = "matrix"  # periods across one axis, metrics across the other
    FLAT = "flat"  # long/tidy format: one record per row
    FRAGMENT = "fragment"  # too small / unstructured to classify


# --------------------------------------------------------------------------- #
# Quarters — canonical form is the label the reports use: "1Q" … "4Q"
# --------------------------------------------------------------------------- #
QUARTER_LABELS: tuple[str, ...] = ("1Q", "2Q", "3Q", "4Q")

#: which quarter each month belongs to (Jan/Feb/Mar -> 1Q, …)
QUARTER_OF_MONTH: dict[int, str] = {
    month: QUARTER_LABELS[(month - 1) // 3] for month in range(1, 13)
}


def quarter_label(number: int | str | None) -> str | None:
    """Canonical quarter label: ``3`` and ``"3Q"`` both give ``"3Q"``."""
    if number is None:
        return None
    if isinstance(number, str):
        digits = "".join(ch for ch in number if ch.isdigit())
        number = int(digits) if digits else 0
    return QUARTER_LABELS[number - 1] if 1 <= number <= 4 else None


def quarter_number(label: str | None) -> int | None:
    """The ordinal behind a canonical label: ``"3Q"`` -> ``3``."""
    if not label:
        return None
    digits = "".join(ch for ch in label if ch.isdigit())
    return int(digits) if digits and 1 <= int(digits) <= 4 else None


# --------------------------------------------------------------------------- #
# Period descriptor
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Period:
    """A time slot discovered in the header, e.g. ``2026 / Aug / W32``.

    Nothing here is hardcoded: ``week`` may be 30 this week and 34 next week,
    ``month`` may appear or disappear, ``year`` may be missing entirely.
    """

    kind: PeriodKind
    label: str
    year: int | None = None
    #: canonical quarter label — "1Q", "2Q", "3Q" or "4Q" (never a bare number)
    quarter: str | None = None
    month: int | None = None
    week: int | None = None
    day: int | None = None
    tokens: tuple[str, ...] = ()
    #: where ``year`` came from — "explicit" (written in the header) or
    #: "inferred" (resolved from the table's context by the period engine)
    year_source: str | None = None

    @property
    def quarter_number(self) -> int | None:
        """The quarter's ordinal, for ordering and arithmetic."""
        return quarter_number(self.quarter)

    @property
    def months(self) -> tuple[int, ...]:
        """Months this period covers (a quarter covers three)."""
        if self.kind is PeriodKind.MONTH and self.month:
            return (self.month,)
        if self.kind is PeriodKind.QUARTER and self.quarter_number:
            first = (self.quarter_number - 1) * 3 + 1
            return (first, first + 1, first + 2)
        if self.kind is PeriodKind.YEAR:
            return tuple(range(1, 13))
        return ()

    def contains(self, other: "Period") -> bool:
        """True when ``other`` falls inside this period (1Q contains Feb)."""
        if self.year and other.year and self.year != other.year:
            return False
        if self.kind is PeriodKind.YEAR:
            return other.kind is not PeriodKind.YEAR
        if self.kind is PeriodKind.QUARTER and other.kind is PeriodKind.MONTH:
            return bool(other.month) and other.month in self.months
        return False

    @property
    def sort_key(self) -> str:
        """Lexicographically sortable key (stable across imports).

        Source order is still the primary ordering used by the UI; this key
        exists so charts can order series that were collected from several
        sheets or files.
        """
        year = f"{self.year:04d}" if self.year is not None else "0000"
        if self.kind is PeriodKind.WEEK and self.week is not None:
            return f"{year}-W{self.week:02d}"
        if self.kind is PeriodKind.MONTH and self.month is not None:
            return f"{year}-M{self.month:02d}"
        if self.kind is PeriodKind.QUARTER and self.quarter_number is not None:
            return f"{year}-Q{self.quarter_number}"
        if self.kind is PeriodKind.DAY and self.day is not None:
            return f"{year}-M{self.month or 0:02d}-D{self.day:02d}"
        if self.kind is PeriodKind.YEAR:
            return f"{year}-Y"
        return f"{year}-U-{self.label}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "label": self.label,
            "year": self.year,
            "quarter": self.quarter,
            "quarterNumber": self.quarter_number,
            "month": self.month,
            "week": self.week,
            "day": self.day,
            "sortKey": self.sort_key,
            "yearSource": self.year_source,
            "tokens": list(self.tokens),
        }


# --------------------------------------------------------------------------- #
# Styles
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CellStyle:
    """Visual snapshot of a cell, deduplicated per table."""

    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_size: float | None = None
    font_name: str | None = None
    font_color: str | None = None  # "RRGGBB"
    fill_color: str | None = None  # "RRGGBB"
    align_h: str | None = None  # left|center|right|justify
    align_v: str | None = None  # top|center|bottom
    wrap: bool = False
    borders: tuple[str, ...] = ()  # subset of top/right/bottom/left

    def to_dict(self) -> dict[str, Any]:
        return {
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "fontSize": self.font_size,
            "fontName": self.font_name,
            "fontColor": self.font_color,
            "fillColor": self.fill_color,
            "alignH": self.align_h,
            "alignV": self.align_v,
            "wrap": self.wrap,
            "borders": list(self.borders),
        }

    @property
    def is_default(self) -> bool:
        return self == DEFAULT_STYLE


DEFAULT_STYLE = CellStyle()


# --------------------------------------------------------------------------- #
# Display hints (formatting is presentation, never mutation)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DisplayFormat:
    """How a number should be *rendered*.  The stored value is never changed."""

    kind: str = "auto"  # auto|integer|decimal|percent|currency|text
    decimals: int | None = None
    thousands: bool = True
    currency: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "decimals": self.decimals,
            "thousands": self.thousands,
            "currency": self.currency,
        }


DEFAULT_FORMAT = DisplayFormat()


# --------------------------------------------------------------------------- #
# Cells
# --------------------------------------------------------------------------- #
@dataclass
class NormalizedCell:
    """One cell of a normalized table.

    ``row``/``col`` are 0-based indexes *inside the detected table*, not Excel
    coordinates.  ``source`` keeps the Excel address purely as provenance.
    """

    row: int
    col: int
    role: CellRole = CellRole.EMPTY
    semantic: SemanticType = SemanticType.UNKNOWN
    value_type: ValueType = ValueType.EMPTY
    #: exactly what the file holds, as a string ("3,000", "NA", "#DIV/0!")
    raw_value: str | None = None
    #: the interpreted numeric value (3000.0) — None when there is no number
    number: float | None = None
    #: textual content after trimming
    text: str | None = None
    #: canonical rendering of ``number`` using the file's number format
    display_value: str | None = None
    raw: Any = None
    error_code: str | None = None  # "#DIV/0!" ...
    formula: str | None = None
    number_format: str | None = None
    display: DisplayFormat = DEFAULT_FORMAT
    style_id: str | None = None
    source_address: str | None = None  # "Q40"
    merged_range: str | None = None  # "B2:B4" when the cell belongs to a merge
    is_merge_anchor: bool = False

    @property
    def is_empty(self) -> bool:
        return self.value_type is ValueType.EMPTY

    @property
    def is_numeric(self) -> bool:
        return self.value_type is ValueType.NUMBER

    def to_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "col": self.col,
            "role": self.role.value,
            "semantic": self.semantic.value,
            "valueType": self.value_type.value,
            "rawValue": self.raw_value,
            "number": self.number,
            "text": self.text,
            "displayValue": self.display_value,
            "errorCode": self.error_code,
            "formula": self.formula,
            "numberFormat": self.number_format,
            "display": self.display.to_dict(),
            "styleId": self.style_id,
            "source": self.source_address,
            "mergedRange": self.merged_range,
            "isMergeAnchor": self.is_merge_anchor,
        }


# --------------------------------------------------------------------------- #
# Axis descriptors
# --------------------------------------------------------------------------- #
@dataclass
class ColumnDescriptor:
    index: int
    source_column: str | None = None  # "Q"
    header_path: tuple[str, ...] = ()  # ("2026", "Aug", "W32")
    label: str = ""
    period: Period | None = None
    #: how the number was produced — "Target", "Result", "Plan"… never a metric
    series_type: str | None = None
    semantic: SemanticType = SemanticType.UNKNOWN
    is_label_column: bool = False
    width: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "sourceColumn": self.source_column,
            "headerPath": list(self.header_path),
            "label": self.label,
            "period": self.period.to_dict() if self.period else None,
            "seriesType": self.series_type,
            "semantic": self.semantic.value,
            "isLabelColumn": self.is_label_column,
            "width": self.width,
        }


@dataclass
class RowDescriptor:
    index: int
    source_row: int | None = None  # 40
    label_path: tuple[str, ...] = ()  # ("SEC", "Total", "PPM")
    label: str = ""
    level: int = 0
    #: interpreted hierarchy — category > subcategory > metric
    category: str | None = None
    subcategory: str | None = None
    metric: str | None = None
    #: "Target" / "Result" rows keep their series meaning instead of pretending
    #: to be a metric (ADR-0012)
    series_type: str | None = None
    #: index of the label block this row belongs to (a group and its metrics)
    block: int = 0
    #: fields the parser inferred rather than read ("category", "metric")
    inferred: tuple[str, ...] = ()
    semantic: SemanticType = SemanticType.UNKNOWN
    is_header_row: bool = False
    period: Period | None = None  # only when the table is transposed
    height: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "sourceRow": self.source_row,
            "labelPath": list(self.label_path),
            "label": self.label,
            "level": self.level,
            "category": self.category,
            "subcategory": self.subcategory,
            "metric": self.metric,
            "seriesType": self.series_type,
            "block": self.block,
            "inferred": list(self.inferred),
            "semantic": self.semantic.value,
            "isHeaderRow": self.is_header_row,
            "period": self.period.to_dict() if self.period else None,
            "height": self.height,
        }


# --------------------------------------------------------------------------- #
# Table
# --------------------------------------------------------------------------- #
@dataclass
class NormalizedTable:
    """Self-contained, Excel-independent representation of one table."""

    sheet_name: str
    source_range: str  # "B2:Q40" — provenance only
    title: str | None = None
    department: str | None = None
    #: names of the label levels, outermost first: ("category", "metric")
    hierarchy: tuple[str, ...] = ()
    shape: TableShape = TableShape.MATRIX
    period_axis: PeriodAxis = PeriodAxis.NONE
    header_row_count: int = 0
    label_col_count: int = 0
    columns: list[ColumnDescriptor] = field(default_factory=list)
    rows: list[RowDescriptor] = field(default_factory=list)
    cells: list[NormalizedCell] = field(default_factory=list)
    merged_ranges: list[str] = field(default_factory=list)
    styles: dict[str, CellStyle] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    # -- access helpers ----------------------------------------------------- #
    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def col_count(self) -> int:
        return len(self.columns)

    def cell(self, row: int, col: int) -> NormalizedCell | None:
        for c in self.cells:  # tables are small; index lazily if this ever hurts
            if c.row == row and c.col == col:
                return c
        return None

    @property
    def periods(self) -> list[Period]:
        if self.period_axis is PeriodAxis.COLUMNS:
            return [c.period for c in self.columns if c.period]
        if self.period_axis is PeriodAxis.ROWS:
            return [r.period for r in self.rows if r.period]
        return []

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheetName": self.sheet_name,
            "sourceRange": self.source_range,
            "title": self.title,
            "department": self.department,
            "hierarchy": list(self.hierarchy),
            "shape": self.shape.value,
            "periodAxis": self.period_axis.value,
            "headerRowCount": self.header_row_count,
            "labelColCount": self.label_col_count,
            "columns": [c.to_dict() for c in self.columns],
            "rows": [r.to_dict() for r in self.rows],
            "cells": [c.to_dict() for c in self.cells],
            "mergedRanges": list(self.merged_ranges),
            "styles": {k: v.to_dict() for k, v in self.styles.items()},
            "warnings": list(self.warnings),
            "meta": dict(self.meta),
        }


@dataclass
class ParsedSheet:
    name: str
    tables: list[NormalizedTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedWorkbook:
    filename: str
    parser_version: str
    sheets: list[ParsedSheet] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def tables(self) -> list[NormalizedTable]:
        return [t for s in self.sheets for t in s.tables]

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "parserVersion": self.parser_version,
            "sheets": [
                {
                    "name": s.name,
                    "warnings": list(s.warnings),
                    "tables": [t.to_dict() for t in s.tables],
                }
                for s in self.sheets
            ],
            "warnings": list(self.warnings),
        }
