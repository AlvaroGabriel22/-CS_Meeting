"""Series extraction over the normalized model.

The charts read the *same* model the tables are drawn from.  A series is
identified by what it means — table, category, subcategory, metric — never by
where it sits in the workbook, so it survives a file whose columns moved.

There is no arithmetic here.  The user does the calculations in Excel before
uploading; this layer selects and arranges, and a missing reading stays missing
rather than becoming a zero (ADR-0036).
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.domain.departments import canonical, schema_for
from app.excel import period_engine as PE
from app.excel.model import Period, PeriodKind
from app.schemas.table import PeriodOut, TableOut

logger = logging.getLogger(__name__)

#: value types that carry a number a chart may plot
PLOTTABLE = {"number"}


# --------------------------------------------------------------------------- #
# Series extraction
# --------------------------------------------------------------------------- #
def _selector(table: TableOut, row: Any) -> dict[str, Any]:
    return {
        "table": table.title or table.sheet_name,
        "category": row.category,
        "subcategory": row.subcategory,
        "metric": row.metric,
        "seriesType": row.series_type,
    }


def selector_key(selector: dict[str, Any]) -> str:
    return "|".join(
        str(selector.get(part) or "")
        for part in ("table", "category", "subcategory", "metric", "seriesType")
    )


def selector_label(selector: dict[str, Any]) -> str:
    parts = [
        selector.get("category"),
        selector.get("subcategory"),
        selector.get("metric"),
        selector.get("seriesType"),
    ]
    return " · ".join(part for part in parts if part) or (selector.get("table") or "")


def _matches(selector: dict[str, Any], filters: dict[str, str | None]) -> bool:
    for field, wanted in filters.items():
        if wanted is None:
            continue
        if canonical(str(selector.get(field) or "")) != canonical(wanted):
            return False
    return True


def table_series(
    table: TableOut,
    *,
    filters: dict[str, str | None] | None = None,
    order: str = "file",
) -> list[dict[str, Any]]:
    """Every data row of a table, as a series over its period columns."""
    filters = filters or {}
    cells = {(cell.row, cell.col): cell for cell in table.cells}
    period_columns = [column for column in table.columns if column.period]
    if order == "chronological":
        period_columns = sorted(
            period_columns, key=lambda column: PE.sort_key(_period(column.period))
        )

    series: list[dict[str, Any]] = []
    for row in table.rows:
        if row.is_header_row:
            continue
        selector = _selector(table, row)
        if not any(selector.values()):
            continue
        if not _matches(selector, filters):
            continue

        points = []
        for column in period_columns:
            cell = cells.get((row.index, column.index))
            points.append(
                {
                    "period": column.period.model_dump(by_alias=True),
                    "value": cell.number if cell and cell.value_type in PLOTTABLE else None,
                    "display": cell.display_value if cell else None,
                    "valueType": cell.value_type if cell else "empty",
                    "source": cell.source if cell else None,
                }
            )

        series.append(
            {
                "key": selector_key(selector),
                "label": selector_label(selector),
                "selector": selector,
                "sheet": table.sheet_name,
                "sourceRange": table.source_range,
                "tableId": table.id,
                "points": points,
            }
        )
    return series


def _period(period: PeriodOut | dict[str, Any] | None) -> Period:
    """Back to the domain object, so the period engine can order it."""
    if period is None:
        return Period(kind=PeriodKind.UNKNOWN, label="")
    data = period if isinstance(period, dict) else period.model_dump(by_alias=True)
    return Period(
        kind=PeriodKind(data.get("kind", "unknown")),
        label=data.get("label", ""),
        year=data.get("year"),
        quarter=data.get("quarter"),
        month=data.get("month"),
        week=data.get("week"),
        day=data.get("day"),
    )


def periods_of(tables: Sequence[TableOut], order: str = "file") -> list[dict[str, Any]]:
    """The period axis of a snapshot: the union of its tables', without repeats."""
    seen: dict[str, dict[str, Any]] = {}
    for table in tables:
        for column in table.columns:
            if not column.period:
                continue
            payload = column.period.model_dump(by_alias=True)
            seen.setdefault(payload["label"], payload)
    periods = list(seen.values())
    if order == "chronological":
        periods.sort(key=lambda payload: PE.sort_key(_period(payload)))
    return periods


def selector_options(tables: Sequence[TableOut]) -> dict[str, list[str]]:
    """What the UI may offer, discovered from the snapshot."""
    options: dict[str, list[str]] = {
        "tables": [],
        "categories": [],
        "subcategories": [],
        "metrics": [],
        "seriesTypes": [],
    }

    def add(bucket: str, value: str | None) -> None:
        if value and value not in options[bucket]:
            options[bucket].append(value)

    for table in tables:
        add("tables", table.title or table.sheet_name)
        for row in table.rows:
            if row.is_header_row:
                continue
            add("categories", row.category)
            add("subcategories", row.subcategory)
            add("metrics", row.metric)
            add("seriesTypes", row.series_type)
    return options


def build_series_response(
    tables: Sequence[TableOut],
    *,
    filters: dict[str, str | None] | None = None,
    order: str = "file",
    limit: int | None = None,
) -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    for table in tables:
        series.extend(table_series(table, filters=filters, order=order))
    if limit:
        series = series[:limit]
    return {
        "order": order,
        "periods": periods_of(tables, order),
        "series": series,
        "options": selector_options(tables),
    }
