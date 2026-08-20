"""Render model — the normalized table, prepared for display.

The UI must not re-derive structure from rows and columns: merges, groups,
indentation, borders and alignment all come from the model that already read
the workbook.  This module turns a :class:`TableOut` into a grid of cells that
a component can draw directly, and nothing else.

What it guarantees:

* **merges become spans** — a cell merged over nine rows in Excel is one cell
  with ``rowSpan: 9``; the covered coordinates are not emitted at all;
* **nothing is invented** — a label cell that is empty in the workbook stays
  empty (the IQC headline rows carry the block's figure and no metric name,
  so no artificial "PPM" ever appears in the UI);
* **inferred names travel as metadata** — ``inferredText`` lets the UI show
  the parser's reading (``Total``) in a visibly different way, never as if the
  file had said it;
* **no period is hardcoded** — the period axis is whatever the model holds, in
  the file's own order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openpyxl.utils import range_boundaries

from app.schemas.table import TableOut

#: horizontal alignment used when the workbook does not state one
DEFAULT_ALIGN = {"corner": "center", "period": "center", "label": "left", "value": "right"}


@dataclass
class Span:
    rows: int = 1
    cols: int = 1


def _origin(source_range: str) -> tuple[int, int]:
    c1, r1, _c2, _r2 = range_boundaries(source_range)
    return r1, c1


def _merge_geometry(table: TableOut) -> tuple[dict[tuple[int, int], Span], set[tuple[int, int]]]:
    """Translate the workbook's merged ranges into table-local spans."""
    row_origin, col_origin = _origin(table.source_range)
    anchors: dict[tuple[int, int], Span] = {}
    covered: set[tuple[int, int]] = set()

    for merged in table.merged_ranges:
        c1, r1, c2, r2 = range_boundaries(merged)
        # clip to the table: a merge may start outside the detected region
        top = max(r1 - row_origin, 0)
        left = max(c1 - col_origin, 0)
        bottom = min(r2 - row_origin, len(table.rows) - 1)
        right = min(c2 - col_origin, len(table.columns) - 1)
        if bottom < top or right < left:
            continue
        anchors[(top, left)] = Span(rows=bottom - top + 1, cols=right - left + 1)
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                if (row, col) != (top, left):
                    covered.add((row, col))
    return anchors, covered


def _headline_rows(table: TableOut) -> set[int]:
    """The first data row of every block: the row carrying the block's figure."""
    seen: set[int] = set()
    headlines: set[int] = set()
    for row in table.rows:
        if row.is_header_row:
            continue
        if row.block not in seen:
            seen.add(row.block)
            headlines.add(row.index)
    return headlines


def _depth(row: Any, is_headline: bool) -> int:
    """Indentation level, derived from the hierarchy the parser found."""
    if is_headline:
        return 1 if row.subcategory else 0
    return 2 if row.subcategory else 1


def build_table_view(table: TableOut) -> dict[str, Any]:
    """Build the display grid of one normalized table."""
    anchors, covered = _merge_geometry(table)
    headlines = _headline_rows(table)
    cells = {(cell.row, cell.col): cell for cell in table.cells}
    styles = table.styles
    label_cols = table.label_col_count

    columns = [
        {
            "index": column.index,
            "kind": "label" if column.is_label_column else "period",
            "label": column.label,
            "period": column.period.model_dump(by_alias=True) if column.period else None,
            "seriesType": column.series_type,
            "sourceColumn": column.source_column,
            "width": column.width,
        }
        for column in table.columns
    ]

    rows: list[dict[str, Any]] = []
    for row in table.rows:
        is_headline = row.index in headlines
        depth = _depth(row, is_headline) if not row.is_header_row else 0
        row_cells: list[dict[str, Any]] = []

        for column in table.columns:
            position = (row.index, column.index)
            if position in covered:
                continue  # drawn by the merge anchor
            span = anchors.get(position, Span())
            cell = cells.get(position)
            row_cells.append(
                _build_cell(
                    row=row,
                    column=column,
                    cell=cell,
                    span=span,
                    label_cols=label_cols,
                    styles=styles,
                    is_headline=is_headline,
                    depth=depth,
                )
            )

        rows.append(
            {
                "index": row.index,
                "kind": "header" if row.is_header_row else "data",
                "semantic": row.semantic,
                "category": row.category,
                "subcategory": row.subcategory,
                "metric": row.metric,
                "seriesType": row.series_type,
                "block": row.block,
                "isHeadline": is_headline,
                "depth": depth,
                "inferred": list(row.inferred) if isinstance(row.inferred, (list, tuple)) else [],
                "sourceRow": row.source_row,
                "height": row.height,
                "cells": row_cells,
            }
        )

    return {
        "id": table.id,
        "title": table.title,
        "department": table.department,
        "sheet": table.sheet_name,
        "sourceRange": table.source_range,
        "hierarchy": list(table.hierarchy),
        "headerRowCount": table.header_row_count,
        "labelColumnCount": label_cols,
        "columnCount": len(table.columns),
        "rowCount": len(table.rows),
        "periods": [
            column.period.model_dump(by_alias=True) for column in table.columns if column.period
        ],
        "columns": columns,
        "rows": rows,
        "warnings": list(table.warnings),
        "meta": {
            "reportingYear": table.meta.get("reportingYear"),
            "blocks": table.meta.get("blocks"),
            # metadata only: the headline metric is never drawn as a label
            "headlineMetric": table.meta.get("schema") and _headline_metric(table),
            "headlineConfirmed": bool(table.meta.get("headlineMetricConfirmed")),
        },
    }


def _headline_metric(table: TableOut) -> str | None:
    for row in table.rows:
        if row.metric and "metric" in (row.inferred or []):
            return row.metric
    return None


def _build_cell(
    *,
    row: Any,
    column: Any,
    cell: Any,
    span: Span,
    label_cols: int,
    styles: dict[str, Any],
    is_headline: bool,
    depth: int,
) -> dict[str, Any]:
    is_label_column = column.index < label_cols
    if row.is_header_row:
        kind = "corner" if is_label_column else "period"
    elif is_label_column:
        kind = "label"
    else:
        kind = "value"

    text = _cell_text(cell)
    if kind == "value" and not text:
        kind = "empty"
    if kind == "label" and not text:
        kind = "empty"

    style = styles.get(cell.style_id) if cell and cell.style_id else None
    align = (style.align_h if style and style.align_h else None) or DEFAULT_ALIGN.get(
        "value" if kind == "empty" and not is_label_column else kind, "left"
    )
    bold = bool(style.bold) if style else False
    if kind in ("corner", "period"):
        bold = True

    # a label written in the metric column that names a sub-group is indented
    # one level, exactly like the group it opens
    indent = 0
    if kind in ("label", "empty") and is_label_column:
        indent = max(depth - column.index, 0)

    return {
        "row": row.index,
        "col": column.index,
        "rowSpan": span.rows,
        "colSpan": span.cols,
        "kind": kind,
        "semantic": cell.semantic if cell else "unknown",
        "text": text,
        "value": cell.number if cell else None,
        "valueType": cell.value_type if cell else "empty",
        "align": align,
        "bold": bold,
        "fillColor": style.fill_color if style else None,
        "textColor": style.font_color if style else None,
        "borders": list(style.borders) if style else [],
        "wrap": bool(style.wrap) if style else False,
        "indent": indent,
        "isHeadline": is_headline and is_label_column,
        # what the parser read but the workbook does not say — shown apart
        "inferredText": _inferred_text(row, column, text, is_headline, label_cols),
        "source": cell.source if cell else None,
        "mergedRange": cell.merged_range if cell else None,
    }


def _cell_text(cell: Any) -> str:
    if cell is None:
        return ""
    if cell.value_type == "number":
        return cell.display_value or ""
    if cell.value_type == "error":
        return cell.error_code or ""
    if cell.value_type in ("empty",):
        return ""
    return cell.text or cell.raw_value or ""


def _inferred_text(
    row: Any, column: Any, text: str, is_headline: bool, label_cols: int
) -> str | None:
    """The label the parser inferred for an empty structural cell.

    Only the *group* name is offered (``Total``), never the metric: a headline
    row's figure is the metric, and writing its name into the table would add
    content the workbook does not have.
    """
    if text or column.index != 0 or column.index >= label_cols:
        return None
    if not is_headline or not row.category:
        return None
    return row.category if "category" in (row.inferred or []) else None
