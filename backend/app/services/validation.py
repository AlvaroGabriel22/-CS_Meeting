"""Validation report for a real workbook.

Answers, per file: which sheets, which tables, where they sit, what merges
exist, which periods and hierarchy were detected, which metrics and series,
how big each table is, what the parser warned about — and, most importantly,
**where the reading is ambiguous**.

Ambiguities are reported, never guessed away (safety rule of Sprint 0): each
one names what a human has to decide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.domain.departments import is_metric_token, schema_for
from app.excel import PARSER_VERSION, parse_file
from app.excel.interpreter import MAX_HEADER_ROWS, MAX_LABEL_COLS
from app.excel.model import NormalizedTable, TableShape

#: how many data rows of each table go into the summarized JSON
SAMPLE_ROWS = 8


@dataclass
class Ambiguity:
    """Something a human must confirm before the reading can be trusted."""

    code: str
    severity: str  # info | check | blocking
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
        }


# --------------------------------------------------------------------------- #
# Ambiguity detection
# --------------------------------------------------------------------------- #
def detect_ambiguities(table: NormalizedTable) -> list[Ambiguity]:
    found: list[Ambiguity] = []
    data_rows = [row for row in table.rows if not row.is_header_row]
    value_cells = [cell for cell in table.cells if cell.role.value == "value"]

    if table.shape is TableShape.MATRIX and table.period_axis.value == "none":
        found.append(
            Ambiguity(
                "no_period_detected",
                "blocking",
                "A matrix table with no time dimension: the header tokens were not "
                "recognised as periods. Which row carries the periods?",
                {"headerRows": table.header_row_count, "columns": table.col_count},
            )
        )

    if table.shape is TableShape.MATRIX and table.header_row_count == 0:
        found.append(
            Ambiguity(
                "no_header_band",
                "blocking",
                "No header row was identified — the first row already looks like data.",
                {"sourceRange": table.source_range},
            )
        )

    if table.header_row_count >= MAX_HEADER_ROWS:
        found.append(
            Ambiguity(
                "header_band_at_cap",
                "check",
                f"The header band hit the {MAX_HEADER_ROWS}-row cap; deeper headers "
                "would be read as data.",
                {"headerRowCount": table.header_row_count},
            )
        )

    if table.label_col_count >= MAX_LABEL_COLS:
        found.append(
            Ambiguity(
                "label_columns_at_cap",
                "check",
                f"The label columns hit the {MAX_LABEL_COLS}-column cap; a deeper "
                "hierarchy would be truncated.",
                {"labelColCount": table.label_col_count},
            )
        )

    if table.shape is TableShape.MATRIX and not table.hierarchy:
        found.append(
            Ambiguity(
                "no_hierarchy",
                "check",
                "No label column was found, so rows have no category/metric names.",
                {"labelColCount": table.label_col_count},
            )
        )

    periods = table.periods
    labels = [period.label for period in periods]
    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        found.append(
            Ambiguity(
                "duplicate_period_labels",
                "info",
                "The same period label appears more than once (usual when a merged "
                "month spans Target/Result columns).",
                {"labels": duplicates},
            )
        )

    undated = [
        period.label
        for period in periods
        if period.kind.value in ("month", "week", "quarter") and period.year is None
    ]
    if undated:
        found.append(
            Ambiguity(
                "period_without_year",
                "check",
                "Months/weeks with no year in their header path: chart ordering falls "
                "back to source order. Should they inherit the newest year in the table?",
                {"labels": undated[:12], "contextYear": table.meta.get("contextYear")},
            )
        )

    kinds = sorted({period.kind.value for period in periods})
    if len(kinds) > 1:
        found.append(
            Ambiguity(
                "mixed_period_granularity",
                "info",
                "The table mixes granularities in one axis (expected for these "
                "reports: yearly, monthly and weekly columns side by side).",
                {"kinds": kinds},
            )
        )

    schema = schema_for(table.department)
    unknown_metrics = sorted(
        {row.metric for row in data_rows if row.metric and not is_metric_token(row.metric, schema)}
    )
    if unknown_metrics:
        found.append(
            Ambiguity(
                "metric_outside_vocabulary",
                "check",
                "Row labels were treated as metrics although they are not in the "
                "department vocabulary. Confirm them or add them to the schema.",
                {"metrics": unknown_metrics[:12], "department": table.department},
            )
        )

    if table.meta.get("uncachedFormulas"):
        found.append(
            Ambiguity(
                "formula_without_cached_value",
                "check",
                "Formulas without a cached result: the workbook was saved by a tool "
                "that did not evaluate them. Values are empty, never zero.",
                {"count": table.meta["uncachedFormulas"]},
            )
        )

    header_band = table.header_row_count + int(table.meta.get("titleRows") or 0)
    straddling = [
        cell.merged_range
        for cell in table.cells
        if cell.merged_range and cell.is_merge_anchor and cell.row < header_band
        and _merge_height(cell.merged_range) + cell.row > header_band
    ]
    if straddling:
        found.append(
            Ambiguity(
                "merge_crosses_header_boundary",
                "check",
                "A merged range spans both the header band and the data area, so the "
                "boundary between them is uncertain.",
                {"ranges": sorted(set(straddling))[:8]},
            )
        )

    if value_cells:
        empty_ratio = sum(1 for cell in value_cells if cell.value_type.value == "empty") / len(value_cells)
        if empty_ratio > 0.5:
            found.append(
                Ambiguity(
                    "mostly_empty",
                    "check",
                    "More than half of the value cells are empty — the detected region "
                    "may be larger than the real table.",
                    {"emptyRatio": round(empty_ratio, 2), "valueCells": len(value_cells)},
                )
            )

    if table.shape is TableShape.FRAGMENT:
        found.append(
            Ambiguity(
                "fragment_region",
                "info",
                "A small block was detected (often a note, a legend or a stray cell).",
                {"rows": table.row_count, "cols": table.col_count},
            )
        )

    return found


def _merge_height(range_str: str) -> int:
    from openpyxl.utils import range_boundaries

    _c1, r1, _c2, r2 = range_boundaries(range_str)
    return r2 - r1 + 1


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def table_report(table: NormalizedTable) -> dict[str, Any]:
    data_rows = [row for row in table.rows if not row.is_header_row]
    value_cells = [cell for cell in table.cells if cell.role.value == "value"]
    counts: dict[str, int] = {}
    for cell in value_cells:
        counts[cell.value_type.value] = counts.get(cell.value_type.value, 0) + 1

    return {
        "sheet": table.sheet_name,
        "sourceRange": table.source_range,
        "title": table.title,
        "shape": table.shape.value,
        "periodAxis": table.period_axis.value,
        "size": {
            "rows": table.row_count,
            "columns": table.col_count,
            "headerRows": table.header_row_count,
            "labelColumns": table.label_col_count,
            "dataRows": len(data_rows),
            "valueCells": len(value_cells),
        },
        "mergedRanges": list(table.merged_ranges),
        "periods": [
            {
                "label": period.label,
                "kind": period.kind.value,
                "year": period.year,
                "quarter": period.quarter,
                "month": period.month,
                "week": period.week,
                "sortKey": period.sort_key,
            }
            for period in table.periods
        ],
        "hierarchy": list(table.hierarchy),
        "categories": sorted({row.category for row in data_rows if row.category}),
        "subcategories": sorted({row.subcategory for row in data_rows if row.subcategory}),
        "metrics": sorted({row.metric for row in data_rows if row.metric}),
        "seriesTypes": sorted(
            {row.series_type for row in data_rows if row.series_type}
            | {column.series_type for column in table.columns if column.series_type}
        ),
        "valueTypes": counts,
        "styles": len(table.styles),
        "warnings": list(table.warnings),
        "ambiguities": [item.to_dict() for item in detect_ambiguities(table)],
        "model": summarize_model(table),
    }


def summarize_model(table: NormalizedTable, sample_rows: int = SAMPLE_ROWS) -> dict[str, Any]:
    """A readable JSON slice of the normalized model (not the whole cell grid)."""
    cells = {(cell.row, cell.col): cell for cell in table.cells}
    period_columns = [column for column in table.columns if column.period]
    rows: list[dict[str, Any]] = []

    for row in table.rows:
        if row.is_header_row:
            continue
        entry: dict[str, Any] = {
            "sourceRow": row.source_row,
            "category": row.category,
            "subcategory": row.subcategory,
            "metric": row.metric,
            "seriesType": row.series_type,
            "period": row.period.label if row.period else None,
            "values": [],
        }
        for column in period_columns or [c for c in table.columns if not c.is_label_column]:
            cell = cells.get((row.index, column.index))
            if cell is None:
                continue
            entry["values"].append(
                {
                    "period": column.period.label if column.period else column.label,
                    "seriesType": column.series_type,
                    "type": cell.value_type.value,
                    "raw": cell.raw_value,
                    "value": cell.number,
                    "display": cell.display_value,
                    "source": cell.source_address,
                }
            )
        rows.append(entry)
        if len(rows) >= sample_rows:
            break

    return {
        "department": table.department,
        "sheet": table.sheet_name,
        "sourceRange": table.source_range,
        "hierarchy": list(table.hierarchy),
        "periods": [period.label for period in table.periods],
        "columns": [
            {
                "index": column.index,
                "sourceColumn": column.source_column,
                "headerPath": list(column.header_path),
                "period": column.period.label if column.period else None,
                "seriesType": column.series_type,
                "isLabelColumn": column.is_label_column,
            }
            for column in table.columns
        ],
        "rowsSample": rows,
        "rowsTotal": sum(1 for row in table.rows if not row.is_header_row),
    }


def workbook_report(path: Path, department: str | None = None) -> dict[str, Any]:
    workbook = parse_file(path, department)
    tables = [table_report(table) for table in workbook.tables]
    severities = [
        ambiguity["severity"]
        for table in tables
        for ambiguity in table["ambiguities"]
    ]
    return {
        "file": path.name,
        "department": department,
        "parserVersion": PARSER_VERSION,
        "sheets": [
            {"name": sheet.name, "tables": len(sheet.tables), "warnings": list(sheet.warnings)}
            for sheet in workbook.sheets
        ],
        "tableCount": len(tables),
        "warnings": list(workbook.warnings),
        "verdict": (
            "blocking" if "blocking" in severities else "check" if "check" in severities else "ok"
        ),
        "tables": tables,
    }
