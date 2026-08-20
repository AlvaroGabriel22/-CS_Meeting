"""Wire contract for normalized tables (mirrors app.excel.model)."""

from __future__ import annotations

from typing import Any, Literal

from .common import CamelModel

PeriodKindLiteral = Literal["year", "quarter", "month", "week", "day", "unknown"]
CellRoleLiteral = Literal["header", "label", "value", "empty"]
ValueTypeLiteral = Literal["empty", "number", "text", "date", "bool", "error", "na"]
SemanticLiteral = Literal[
    "title", "period", "series", "category", "subcategory", "metric", "value", "label", "unknown"
]


class PeriodOut(CamelModel):
    kind: PeriodKindLiteral
    label: str
    year: int | None = None
    #: canonical quarter label — "1Q" … "4Q"
    quarter: str | None = None
    quarter_number: int | None = None
    month: int | None = None
    week: int | None = None
    day: int | None = None
    sort_key: str
    tokens: list[str] = []


class DisplayFormatOut(CamelModel):
    kind: str = "auto"
    decimals: int | None = None
    thousands: bool = True
    currency: str | None = None


class CellStyleOut(CamelModel):
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_size: float | None = None
    font_name: str | None = None
    font_color: str | None = None
    fill_color: str | None = None
    align_h: str | None = None
    align_v: str | None = None
    wrap: bool = False
    borders: list[str] = []


class TableColumnOut(CamelModel):
    index: int
    source_column: str | None = None
    header_path: list[str] = []
    label: str = ""
    period: PeriodOut | None = None
    #: "Target" / "Result" / "Plan" — never a metric (ADR-0012)
    series_type: str | None = None
    semantic: SemanticLiteral = "unknown"
    is_label_column: bool = False
    width: float | None = None


class TableRowOut(CamelModel):
    index: int
    source_row: int | None = None
    label_path: list[str] = []
    label: str = ""
    level: int = 0
    category: str | None = None
    subcategory: str | None = None
    metric: str | None = None
    series_type: str | None = None
    #: index of the label block this row belongs to (a group and its metrics)
    block: int = 0
    #: fields the parser inferred rather than read ("category", "metric")
    inferred: list[str] = []
    semantic: SemanticLiteral = "unknown"
    is_header_row: bool = False
    period: PeriodOut | None = None
    height: float | None = None


class TableCellOut(CamelModel):
    row: int
    col: int
    role: CellRoleLiteral
    semantic: SemanticLiteral = "unknown"
    value_type: ValueTypeLiteral
    #: the value exactly as the file holds it ("3,000", "NA", "#DIV/0!")
    raw_value: str | None = None
    number: float | None = None
    text: str | None = None
    #: canonical rendering of ``number`` (never replaces it)
    display_value: str | None = None
    error_code: str | None = None
    formula: str | None = None
    number_format: str | None = None
    display: DisplayFormatOut | None = None
    style_id: str | None = None
    source: str | None = None
    merged_range: str | None = None
    is_merge_anchor: bool = False


class TableOut(CamelModel):
    id: int | None = None
    sheet_name: str
    source_range: str
    title: str | None = None
    department: str | None = None
    hierarchy: list[str] = []
    shape: Literal["matrix", "flat", "fragment"]
    period_axis: Literal["columns", "rows", "none"]
    header_row_count: int = 0
    label_col_count: int = 0
    columns: list[TableColumnOut] = []
    rows: list[TableRowOut] = []
    cells: list[TableCellOut] = []
    merged_ranges: list[str] = []
    styles: dict[str, CellStyleOut] = {}
    warnings: list[str] = []
    meta: dict[str, Any] = {}


class TableSummaryOut(CamelModel):
    """Lightweight view used in listings (no cells)."""

    id: int | None = None
    sheet_name: str
    source_range: str
    title: str | None = None
    shape: str
    period_axis: str
    hierarchy: list[str] = []
    row_count: int
    col_count: int
    periods: list[PeriodOut] = []
    warnings: list[str] = []


class InterpretationOut(CamelModel):
    """Semantic projection of a table — the Sprint 0 acceptance view."""

    department: str | None = None
    sheet: str
    table: str | None = None
    source_range: str
    shape: str
    period_axis: str
    hierarchy: list[str] = []
    periods: list[str] = []
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []


# --------------------------------------------------------------------------- #
# Render model — the table prepared for display (Sprint 2)
# --------------------------------------------------------------------------- #
CellKindLiteral = Literal["corner", "period", "label", "value", "empty"]


class RenderCellOut(CamelModel):
    """One drawn cell.  Merged ranges arrive as spans; covered cells are absent."""

    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    kind: CellKindLiteral
    semantic: str = "unknown"
    #: already formatted for reading ("20,970"); never a re-computed value
    text: str = ""
    value: float | None = None
    value_type: str = "empty"
    align: str = "left"
    bold: bool = False
    fill_color: str | None = None
    text_color: str | None = None
    borders: list[str] = []
    wrap: bool = False
    #: indentation level inside the label column, from the hierarchy
    indent: int = 0
    is_headline: bool = False
    #: what the parser inferred for a cell the workbook leaves empty; the UI
    #: must show it as clearly distinct from the file's own content
    inferred_text: str | None = None
    source: str | None = None
    merged_range: str | None = None


class RenderColumnOut(CamelModel):
    index: int
    kind: Literal["label", "period"]
    label: str = ""
    period: PeriodOut | None = None
    series_type: str | None = None
    source_column: str | None = None
    width: float | None = None


class RenderRowOut(CamelModel):
    index: int
    kind: Literal["header", "data"]
    semantic: str = "unknown"
    category: str | None = None
    subcategory: str | None = None
    metric: str | None = None
    series_type: str | None = None
    block: int = 0
    #: the row carrying the block's own figure (no metric label of its own)
    is_headline: bool = False
    depth: int = 0
    inferred: list[str] = []
    source_row: int | None = None
    height: float | None = None
    cells: list[RenderCellOut] = []


class TableViewOut(CamelModel):
    """A normalized table, ready to draw."""

    id: int | None = None
    title: str | None = None
    department: str | None = None
    sheet: str
    source_range: str
    hierarchy: list[str] = []
    header_row_count: int = 0
    label_column_count: int = 0
    column_count: int = 0
    row_count: int = 0
    periods: list[PeriodOut] = []
    columns: list[RenderColumnOut] = []
    rows: list[RenderRowOut] = []
    warnings: list[str] = []
    meta: dict[str, Any] = {}
