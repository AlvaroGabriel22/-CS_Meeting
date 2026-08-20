"""**Layer 2 — Interpreter: raw structure -> semantic structure.**

Decides what the region *means*: where the title is, which rows are headers,
which columns name the rows, what each header token is (year / month / week /
series), and how the row labels nest (category > subcategory > metric).

It produces decisions only — no cells are built here (that is the normalizer's
job, layer 3).  Everything is inferred; a :class:`DepartmentSchema` may be
supplied to raise confidence, but is never required.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from openpyxl.utils import get_column_letter

from app.domain.departments import DepartmentSchema, canonical, is_metric_token

from . import periods as P
from . import values as V
from .model import (
    ColumnDescriptor,
    PeriodAxis,
    PeriodKind,
    RowDescriptor,
    SemanticType,
    TableShape,
    ValueType,
)
from .raw_model import RawSheet
from .regions import Rect

logger = logging.getLogger(__name__)

MAX_HEADER_ROWS = 6
MAX_LABEL_COLS = 4
#: header rows sparser than this get their group labels forward-filled
SPARSE_HEADER_RATIO = 0.6

#: column names that carry the time dimension in flat/long tables
FLAT_PERIOD_COLUMNS = {
    "year": {"year", "ano", "yr", "연도"},
    "month": {"month", "mes", "월"},
    "week": {"week", "semana", "sem", "주"},
    "day": {"day", "dia", "date", "data", "일"},
}


@dataclass
class TableInterpretation:
    """The semantic reading of one region — the contract between layers 2 and 3."""

    rect: Rect
    title: str | None = None
    title_rows: int = 0
    header_rows: int = 0
    label_cols: int = 0
    columns: list[ColumnDescriptor] = field(default_factory=list)
    rows: list[RowDescriptor] = field(default_factory=list)
    period_axis: PeriodAxis = PeriodAxis.NONE
    shape: TableShape = TableShape.MATRIX
    hierarchy: tuple[str, ...] = ()
    #: label column index -> hierarchy level name
    label_roles: dict[int, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def data_start_row(self) -> int:
        """First Excel row that holds measurements."""
        return self.rect.r1 + self.title_rows + self.header_rows


# --------------------------------------------------------------------------- #
# Row / column statistics
# --------------------------------------------------------------------------- #
def _cell_stats(sheet: RawSheet, row: int, c1: int, c2: int) -> tuple[int, int, int]:
    """(non-empty, measurement-like, textual) counts for one row of a region.

    A numeric cell that reads as a period (``2026``, ``8``, ``W32``) is *not*
    counted as a measurement — otherwise a merged year header would look like a
    data row and the whole header band would be missed.
    """
    entries: list[tuple[str, ValueType]] = []
    for col in range(c1, c2 + 1):
        value_type, _, _, _ = V.coerce(sheet.value(row, col))
        if value_type is ValueType.EMPTY:
            continue
        entries.append((sheet.text(row, col), value_type))

    non_empty = len(entries)
    period_hits = sum(1 for text, _ in entries if P.match_token(text) is not None)
    period_row = period_hits >= max(2, int(0.6 * non_empty))

    measurements = textual = 0
    for text, value_type in entries:
        if period_row and P.match_token(text) is not None:
            continue
        if value_type in (ValueType.NUMBER, ValueType.ERROR, ValueType.NA):
            measurements += 1
        elif value_type in (ValueType.TEXT, ValueType.DATE):
            textual += 1
    return non_empty, measurements, textual


def _detect_title(sheet: RawSheet, rect: Rect) -> tuple[str | None, int]:
    """A wide, lonely, non-numeric row at the top of the region is a title."""
    title_parts: list[str] = []
    row = rect.r1
    while row <= rect.r2 and len(title_parts) < 2:
        distinct = {
            sheet.text(row, col) for col in range(rect.c1, rect.c2 + 1) if sheet.is_occupied(row, col)
        }
        non_empty, numeric, _ = _cell_stats(sheet, row, rect.c1, rect.c2)
        if numeric == 0 and len(distinct) == 1 and non_empty >= 1 and rect.rows > 2:
            title_parts.append(distinct.pop())
            row += 1
            continue
        break
    return (" — ".join(title_parts) if title_parts else None), len(title_parts)


def _detect_header_rows(sheet: RawSheet, rect: Rect, first_row: int) -> int:
    """Number of leading rows that describe the data instead of being data."""
    for offset, row in enumerate(range(first_row, rect.r2 + 1)):
        non_empty, numeric, _ = _cell_stats(sheet, row, rect.c1, rect.c2)
        if non_empty and numeric >= max(2, int(0.4 * non_empty)):
            return min(offset, MAX_HEADER_ROWS)
    return 1 if rect.r2 > first_row else 0


def _detect_label_cols(sheet: RawSheet, rect: Rect, data_start: int) -> int:
    """Leading columns that name the rows instead of holding measurements."""
    if data_start > rect.r2:
        return 0
    count = 0
    for col in range(rect.c1, min(rect.c1 + MAX_LABEL_COLS, rect.c2 + 1)):
        non_empty = numeric = 0
        for row in range(data_start, rect.r2 + 1):
            value_type, _, _, _ = V.coerce(sheet.value(row, col))
            if value_type is ValueType.EMPTY:
                continue
            non_empty += 1
            if value_type is ValueType.NUMBER:
                numeric += 1
        if non_empty and numeric >= max(1, int(0.5 * non_empty)):
            break
        count += 1
    return min(count, rect.cols - 1) if rect.cols > 1 else 0


def _header_row_values(sheet: RawSheet, row: int, c1: int, c2: int) -> list[str]:
    """Values of a header row, forward-filled when it holds sparse group labels.

    Excel authors often write ``2026`` once above a block of months instead of
    merging the cells.  Merged ranges are already resolved by the parser, so
    this only covers the un-merged case.
    """
    raw = [sheet.text(row, col) for col in range(c1, c2 + 1)]
    filled_ratio = sum(1 for value in raw if value) / max(len(raw), 1)
    if filled_ratio >= SPARSE_HEADER_RATIO:
        return raw
    out: list[str] = []
    current = ""
    for value in raw:
        if value:
            current = value
        out.append(current)
    return out


# --------------------------------------------------------------------------- #
# Hierarchy: category > subcategory > metric
# --------------------------------------------------------------------------- #
def _label_matrix(
    sheet: RawSheet, rect: Rect, data_start: int, label_cols: int
) -> list[list[str]]:
    """Label values per data row, with merged/blank groups carried downwards."""
    carry = [""] * label_cols
    matrix: list[list[str]] = []
    for row in range(data_start, rect.r2 + 1):
        parts: list[str] = []
        for i in range(label_cols):
            text = sheet.text(row, rect.c1 + i)
            if text:
                carry[i] = text
                carry[i + 1 :] = [""] * (label_cols - i - 1)
            parts.append(text or carry[i])
        matrix.append(parts)
    return matrix


def _dominated_by(matrix: list[list[str]], index: int, predicate, minimum_distinct: int = 1) -> bool:
    """True when a label column is mostly made of one kind of token."""
    values = [row[index] for row in matrix if row[index]]
    if not values:
        return False
    hits = [value for value in values if predicate(value)]
    if len({value for value in hits}) < minimum_distinct:
        return False
    return len(hits) >= max(1, int(0.6 * len(values)))


def _assign_hierarchy(
    matrix: list[list[str]], label_cols: int, schema: DepartmentSchema | None
) -> tuple[dict[int, str], tuple[str, ...]]:
    """Decide what each label column is: category, subcategory, metric, series.

    Order of reasoning:

    1. A column dominated by *plan-vs-outcome* labels (``Target``/``Result``)
       is a **series**, never a metric — it says how a number was produced, not
       what was measured (ADR-0012).
    2. The outermost remaining column groups the rows, so it is a category and
       is never considered for the metric role.
    3. The metric is the innermost remaining column whose values read as
       measured quantities (``PPM``, ``Def.``, ``Insp.``…); failing that, the
       layout itself implies the innermost column names the measure.
    4. A single label column of unknown words names the rows: category.
    """
    if label_cols <= 0 or not matrix:
        return {}, ()

    roles: dict[int, str] = {}

    series_col = next(
        (
            index
            for index in range(label_cols - 1, -1, -1)
            if _dominated_by(
                matrix, index, lambda value: P.match_plan_actual_series(value) is not None, 2
            )
        ),
        None,
    )
    if series_col is not None:
        roles[series_col] = "series"

    remaining = [index for index in range(label_cols) if index not in roles]
    if not remaining:
        return roles, ("series",)

    category_col = remaining[0] if len(remaining) >= 2 else None
    metric_candidates = [index for index in remaining if index != category_col]

    metric_col = next(
        (
            index
            for index in reversed(metric_candidates)
            if _dominated_by(matrix, index, lambda value: is_metric_token(value, schema))
        ),
        None,
    )
    if metric_col is None and series_col is None and len(remaining) >= 2:
        metric_col = remaining[-1]

    if metric_col is not None:
        roles[metric_col] = "metric"

    outer = [index for index in remaining if metric_col is None or index < metric_col]
    if outer:
        roles[outer[0]] = "category"
    if len(outer) >= 2:
        roles[outer[1]] = "subcategory"
    for index in outer[2:]:
        roles[index] = "label"

    order = {"category": 0, "subcategory": 1, "metric": 2, "series": 3}
    hierarchy = tuple(
        role
        for role in sorted(
            (role for role in roles.values() if role in order),
            key=lambda role: order[role],
        )
    )
    return roles, hierarchy


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def interpret_region(
    sheet: RawSheet, rect: Rect, schema: DepartmentSchema | None = None
) -> TableInterpretation:
    """Read one region semantically."""
    title, title_rows = _detect_title(sheet, rect)
    first_row = rect.r1 + title_rows
    header_rows = _detect_header_rows(sheet, rect, first_row)
    data_start = first_row + header_rows
    label_cols = _detect_label_cols(sheet, rect, data_start)

    interpretation = TableInterpretation(
        rect=rect,
        title=title,
        title_rows=title_rows,
        header_rows=header_rows,
        label_cols=label_cols,
    )

    header_values = [
        _header_row_values(sheet, first_row + i, rect.c1, rect.c2) for i in range(header_rows)
    ]
    row_kinds = [P.row_period_kind(row[label_cols:]) for row in header_values]

    # ---------------- columns --------------------------------------------- #
    for offset, col in enumerate(range(rect.c1, rect.c2 + 1)):
        header_path = tuple(row[offset] for row in header_values if row[offset])
        is_label = offset < label_cols
        period, series_type = (None, None)
        if not is_label and header_rows:
            period, series_type = P.build_period(
                [row[offset] for row in header_values], row_kinds
            )
        if is_label:
            semantic = SemanticType.LABEL
        elif period:
            semantic = SemanticType.PERIOD
        elif series_type:
            semantic = SemanticType.SERIES
        else:
            semantic = SemanticType.UNKNOWN
        interpretation.columns.append(
            ColumnDescriptor(
                index=offset,
                source_column=get_column_letter(col),
                header_path=header_path,
                label=header_path[-1] if header_path else get_column_letter(col),
                period=period,
                series_type=series_type,
                semantic=semantic,
                is_label_column=is_label,
                width=sheet.col_widths.get(col),
            )
        )

    # ---------------- rows & hierarchy ------------------------------------ #
    matrix = _label_matrix(sheet, rect, data_start, label_cols)
    roles, hierarchy = _assign_hierarchy(matrix, label_cols, schema)
    interpretation.label_roles = roles
    interpretation.hierarchy = hierarchy

    for offset, row in enumerate(range(rect.r1, rect.r2 + 1)):
        is_header = offset < title_rows + header_rows
        descriptor = RowDescriptor(
            index=offset,
            source_row=row,
            is_header_row=is_header,
            height=sheet.row_heights.get(row),
            semantic=SemanticType.TITLE
            if offset < title_rows
            else SemanticType.PERIOD
            if is_header
            else SemanticType.VALUE,
        )
        if not is_header and label_cols:
            labels = matrix[offset - (title_rows + header_rows)]
            descriptor.label_path = tuple(value for value in labels if value)
            descriptor.label = descriptor.label_path[-1] if descriptor.label_path else ""
            descriptor.level = max(len(descriptor.label_path) - 1, 0)
            for index, role in roles.items():
                value = labels[index] if index < len(labels) else ""
                if not value:
                    continue
                if role == "category":
                    descriptor.category = value
                elif role == "subcategory":
                    descriptor.subcategory = value
                elif role == "series":
                    descriptor.series_type = P.match_plan_actual_series(value) or value
                elif role == "metric":
                    # a plan/outcome label sitting in the metric column is still
                    # a series: "Target" says how, not what (ADR-0012)
                    series = P.match_plan_actual_series(value)
                    if series:
                        descriptor.series_type = series
                    else:
                        descriptor.metric = value
            if descriptor.metric:
                descriptor.semantic = SemanticType.METRIC
            elif descriptor.series_type:
                descriptor.semantic = SemanticType.SERIES
            elif descriptor.subcategory:
                descriptor.semantic = SemanticType.SUBCATEGORY
            elif descriptor.category:
                descriptor.semantic = SemanticType.CATEGORY
        interpretation.rows.append(descriptor)

    # ---------------- period axis ----------------------------------------- #
    column_periods = [column.period for column in interpretation.columns if column.period]
    if len(column_periods) >= 2:
        interpretation.period_axis = PeriodAxis.COLUMNS
    elif label_cols:
        first_labels = [
            row.label_path[0] for row in interpretation.rows if not row.is_header_row and row.label_path
        ]
        if P.looks_like_period_sequence(first_labels):
            interpretation.period_axis = PeriodAxis.ROWS
            kind = P.row_period_kind(first_labels)
            for descriptor in interpretation.rows:
                if descriptor.is_header_row or not descriptor.label_path:
                    continue
                period, _ = P.build_period(descriptor.label_path, [kind] * len(descriptor.label_path))
                descriptor.period = period
                if period:
                    # the row *is* a period; it is not a metric or a category
                    descriptor.semantic = SemanticType.PERIOD
                    descriptor.category = descriptor.subcategory = descriptor.metric = None
            interpretation.hierarchy = ()
            interpretation.label_roles = {}

    # ---------------- shape ------------------------------------------------ #
    data_rows = rect.r2 - data_start + 1
    if interpretation.period_axis is not PeriodAxis.NONE:
        interpretation.shape = TableShape.MATRIX
    elif header_rows <= 1 and data_rows >= 4 and rect.cols >= 3:
        interpretation.shape = TableShape.FLAT
        interpretation.meta["flatPeriodColumns"] = _flat_period_columns(interpretation)
    elif rect.rows < 2 or rect.cols < 2:
        interpretation.shape = TableShape.FRAGMENT
    else:
        interpretation.shape = TableShape.MATRIX
        interpretation.warnings.append("no_period_detected")

    years = {
        column.period.year
        for column in interpretation.columns
        if column.period and column.period.year
    }
    corner = interpretation.columns[0].header_path[-1] if (
        interpretation.columns and interpretation.columns[0].header_path
    ) else None
    interpretation.meta.update(
        {
            "contextYear": max(years) if years else None,
            "cornerLabel": corner,
            "dataStartRow": data_start,
            "titleRows": title_rows,
            "labelRoles": {str(index): role for index, role in roles.items()},
            "schema": schema.code if schema else None,
        }
    )
    logger.debug(
        "interpreted %s: header=%d labels=%d hierarchy=%s axis=%s",
        rect.a1,
        header_rows,
        label_cols,
        hierarchy,
        interpretation.period_axis.value,
    )
    return interpretation


def _flat_period_columns(interpretation: TableInterpretation) -> dict[str, int]:
    """Map ``year``/``month``/``week``/``day`` to column indexes of a flat table."""
    found: dict[str, int] = {}
    for column in interpretation.columns:
        name = canonical(column.label)
        for key, aliases in FLAT_PERIOD_COLUMNS.items():
            if name in aliases and key not in found:
                found[key] = column.index
    return found


__all__ = ["TableInterpretation", "interpret_region", "PeriodKind"]
