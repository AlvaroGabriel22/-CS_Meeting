"""Semantic projection — the human-readable proof that the file was understood.

Turns a normalized table into the compact view the specification asks for::

    {
      "department": "OQC",
      "table": "SEC",
      "periods": ["2025", "2026", "Jan", …, "W32", "W33"],
      "rows": [
        {"category": "SEC", "subcategory": "Total", "metric": "PPM", "values": [...]}
      ]
    }

It reads the *interpretation* (periods, hierarchy, semantic types), never the
Excel coordinates — which is exactly what makes it a proof.
"""

from __future__ import annotations

from typing import Any

from app.excel.model import NormalizedTable
from app.schemas.table import TableOut


def from_normalized(table: NormalizedTable, department: str | None = None) -> TableOut:
    """Bridge the in-memory model to the wire contract (same field names)."""
    payload = table.to_dict()
    if department:
        payload["department"] = department
    return TableOut.model_validate(payload)


def interpretation_view(table: TableOut, *, max_rows: int | None = None) -> dict[str, Any]:
    """Compact semantic view of one table."""
    view: dict[str, Any] = {
        "department": table.department,
        "sheet": table.sheet_name,
        "table": _table_name(table),
        "sourceRange": table.source_range,
        "shape": table.shape,
        "periodAxis": table.period_axis,
        "hierarchy": list(table.hierarchy),
        "periods": [],
        "rows": [],
        "warnings": list(table.warnings),
    }

    if table.period_axis == "columns":
        view["periods"] = [column.period.label for column in table.columns if column.period]
        view["rows"] = _rows_by_period_columns(table, max_rows)
    elif table.period_axis == "rows":
        view["periods"] = [row.period.label for row in table.rows if row.period]
        view["rows"] = _rows_transposed(table, max_rows)
    else:
        view["rows"] = _rows_flat(table, max_rows)
    return view


# --------------------------------------------------------------------------- #
def _table_name(table: TableOut) -> str | None:
    if table.title:
        return table.title
    categories = [row.category for row in table.rows if row.category]
    if categories and len(set(categories)) == 1:
        return categories[0]
    corner = table.meta.get("cornerLabel")
    return str(corner) if corner else None


def _cell_index(table: TableOut) -> dict[tuple[int, int], Any]:
    return {(cell.row, cell.col): cell for cell in table.cells}


def _value_entry(cell: Any, period_label: str, series: str | None = None) -> dict[str, Any]:
    if cell is None:
        return {"period": period_label, "series": series, "type": "empty", "value": None}
    return {
        "period": period_label,
        "series": series,
        "type": cell.value_type,
        "raw": cell.raw_value,
        "value": cell.number,
        "display": cell.display_value,
        "error": cell.error_code,
        "source": cell.source,
    }


def _rows_by_period_columns(table: TableOut, max_rows: int | None) -> list[dict[str, Any]]:
    cells = _cell_index(table)
    period_columns = [column for column in table.columns if column.period]
    out: list[dict[str, Any]] = []
    for row in table.rows:
        if row.is_header_row or not (row.category or row.subcategory or row.metric or row.label):
            continue
        out.append(
            {
                "category": row.category,
                "subcategory": row.subcategory,
                "metric": row.metric or row.label,
                "sourceRow": row.source_row,
                "values": [
                    _value_entry(cells.get((row.index, column.index)), column.period.label, column.series)
                    for column in period_columns
                ],
            }
        )
        if max_rows and len(out) >= max_rows:
            break
    return out


def _rows_transposed(table: TableOut, max_rows: int | None) -> list[dict[str, Any]]:
    cells = _cell_index(table)
    metric_columns = [column for column in table.columns if not column.is_label_column]
    out: list[dict[str, Any]] = []
    for row in table.rows:
        if row.is_header_row or not row.period:
            continue
        out.append(
            {
                "period": row.period.label,
                "sourceRow": row.source_row,
                "values": [
                    dict(
                        _value_entry(cells.get((row.index, column.index)), row.period.label),
                        metric=column.label,
                    )
                    for column in metric_columns
                ],
            }
        )
        if max_rows and len(out) >= max_rows:
            break
    return out


def _rows_flat(table: TableOut, max_rows: int | None) -> list[dict[str, Any]]:
    cells = _cell_index(table)
    headers = [column.label for column in table.columns]
    out: list[dict[str, Any]] = []
    for row in table.rows:
        if row.is_header_row:
            continue
        record = {}
        for index, name in enumerate(headers):
            cell = cells.get((row.index, index))
            record[name] = cell.number if cell and cell.number is not None else (cell.text if cell else None)
        out.append(record)
        if max_rows and len(out) >= max_rows:
            break
    return out
