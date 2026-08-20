"""Analytics over the normalized model.

Charts, period comparison and version comparison all read the *same* model the
tables are drawn from.  A series is identified by what it means — table,
category, subcategory, metric — never by where it sits in the workbook, so it
survives a file whose columns moved.

Three rules govern the arithmetic:

* ``delta = B - A``;
* ``deltaPercent = (B - A) / A × 100``, and **only** when ``A`` is a real
  non-zero number — otherwise the percentage is ``null`` with a status saying
  why;
* a missing period is missing, never zero.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

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


# --------------------------------------------------------------------------- #
# Deltas
# --------------------------------------------------------------------------- #
def _direction(delta: float | None) -> str:
    if delta is None:
        return "unknown"
    if delta > 0:
        return "up"
    if delta < 0:
        return "down"
    return "flat"


def _severity(metric: str | None, direction: str, department: str | None) -> str:
    """Good or bad — only when the department declares the metric's polarity."""
    schema = schema_for(department)
    polarity = schema.metric_polarity(metric) if schema and metric else None
    if polarity is None or direction in ("unknown", "flat"):
        return "neutral" if direction == "flat" else "unknown"
    if polarity == "lower_is_better":
        return "negative" if direction == "up" else "positive"
    if polarity == "higher_is_better":
        return "positive" if direction == "up" else "negative"
    return "neutral"


def compute_delta(
    point_a: dict[str, Any] | None,
    point_b: dict[str, Any] | None,
    *,
    metric: str | None = None,
    department: str | None = None,
) -> dict[str, Any]:
    """``B - A`` with an honest percentage.

    A percentage needs a real, non-zero baseline: without one it is ``null``
    and the status says which side was missing or that the ratio is undefined.
    """
    value_a = (point_a or {}).get("value")
    value_b = (point_b or {}).get("value")
    result: dict[str, Any] = {
        "valueA": value_a,
        "valueB": value_b,
        "displayA": (point_a or {}).get("display"),
        "displayB": (point_b or {}).get("display"),
        "delta": None,
        "deltaPercent": None,
        "direction": "unknown",
        "severity": "unknown",
        "status": "ok",
    }

    if value_a is None:
        result["status"] = "missing_a"
        return result
    if value_b is None:
        result["status"] = "missing_b"
        return result

    delta = value_b - value_a
    result["delta"] = delta
    result["direction"] = _direction(delta)
    result["severity"] = _severity(metric, result["direction"], department)

    if value_a == 0:
        # a percentage against a zero baseline is not a number; say so
        result["status"] = "undefined_percent"
        return result
    result["deltaPercent"] = delta / value_a * 100.0
    return result


def _point_for(series: dict[str, Any], label: str | None) -> dict[str, Any] | None:
    if label is None:
        return None
    for point in series["points"]:
        if point["period"]["label"] == label:
            return point
    return None


# --------------------------------------------------------------------------- #
# Comparisons
# --------------------------------------------------------------------------- #
def compare_periods(
    tables: Sequence[TableOut],
    *,
    period_a: str,
    period_b: str,
    filters: dict[str, str | None] | None = None,
    department: str | None = None,
) -> dict[str, Any]:
    """Two periods of the same snapshot, row by row."""
    series = []
    for table in tables:
        series.extend(table_series(table, filters=filters))

    warnings: list[str] = []
    available = {point["period"]["label"] for item in series for point in item["points"]}
    for label in (period_a, period_b):
        if label not in available:
            warnings.append(f"period_not_in_snapshot:{label}")

    rows = [
        _comparison_row(item, _point_for(item, period_a), _point_for(item, period_b), department)
        for item in series
    ]
    return {
        "kind": "periods",
        "periodA": _period_payload(series, period_a),
        "periodB": _period_payload(series, period_b),
        "rows": rows,
        "warnings": warnings,
    }


def compare_versions(
    tables_a: Sequence[TableOut],
    tables_b: Sequence[TableOut],
    *,
    period: str,
    filters: dict[str, str | None] | None = None,
    department: str | None = None,
) -> dict[str, Any]:
    """The same period, the same rows, in two snapshots.

    Snapshots are immutable: this only reads them.  A row that exists in one
    version and not in the other is reported as missing, never as zero.
    """
    series_a = {
        item["key"]: item
        for table in tables_a
        for item in table_series(table, filters=filters)
    }
    series_b = {
        item["key"]: item
        for table in tables_b
        for item in table_series(table, filters=filters)
    }

    warnings: list[str] = []
    only_a = sorted(set(series_a) - set(series_b))
    only_b = sorted(set(series_b) - set(series_a))
    if only_a:
        warnings.append(f"rows_only_in_a:{len(only_a)}")
    if only_b:
        warnings.append(f"rows_only_in_b:{len(only_b)}")

    rows = []
    for key in list(series_a) + [key for key in series_b if key not in series_a]:
        item_a = series_a.get(key)
        item_b = series_b.get(key)
        reference = item_a or item_b
        rows.append(
            _comparison_row(
                reference,
                _point_for(item_a, period) if item_a else None,
                _point_for(item_b, period) if item_b else None,
                department,
            )
        )

    payload = _period_payload(list(series_a.values()) + list(series_b.values()), period)
    return {
        "kind": "versions",
        "periodA": payload,
        "periodB": payload,
        "rows": rows,
        "warnings": warnings,
    }


def _comparison_row(
    series: dict[str, Any],
    point_a: dict[str, Any] | None,
    point_b: dict[str, Any] | None,
    department: str | None,
) -> dict[str, Any]:
    selector = series["selector"]
    return {
        "key": series["key"],
        "label": series["label"],
        "selector": selector,
        "delta": compute_delta(
            point_a, point_b, metric=selector.get("metric"), department=department
        ),
        "sourceA": (point_a or {}).get("source"),
        "sourceB": (point_b or {}).get("source"),
    }


def _period_payload(series: Iterable[dict[str, Any]], label: str) -> dict[str, Any] | None:
    for item in series:
        for point in item["points"]:
            if point["period"]["label"] == label:
                return point["period"]
    return None


# --------------------------------------------------------------------------- #
# Executive insights (infrastructure only — nothing generates slides yet)
# --------------------------------------------------------------------------- #
def build_insights(
    comparison: dict[str, Any],
    *,
    department: str | None,
    version_id: int | None,
    version_number: int | None = None,
    source_ranges: dict[str, str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Turn the biggest movements into statements a summary could use."""
    ranked = [
        row
        for row in comparison["rows"]
        if row["delta"]["status"] == "ok" and row["delta"]["delta"] is not None
    ]
    ranked.sort(key=lambda row: abs(row["delta"].get("deltaPercent") or 0), reverse=True)

    insights = []
    for row in ranked[:limit]:
        delta = row["delta"]
        selector = row["selector"]
        insights.append(
            {
                "title": _insight_title(row, comparison),
                "department": department,
                "table": selector.get("table"),
                "category": selector.get("category"),
                "subcategory": selector.get("subcategory"),
                "metric": selector.get("metric"),
                "seriesType": selector.get("seriesType"),
                "period": comparison.get("periodB"),
                "referencePeriod": comparison.get("periodA"),
                "value": delta["valueB"],
                "previousValue": delta["valueA"],
                "displayValue": delta["displayB"],
                "displayPrevious": delta["displayA"],
                "delta": delta["delta"],
                "deltaPercent": delta["deltaPercent"],
                "direction": delta["direction"],
                "severity": delta["severity"],
                "status": delta["status"],
                "source": row.get("sourceB") or row.get("sourceA"),
                "sourceRange": (source_ranges or {}).get(selector.get("table") or ""),
                "versionId": version_id,
                "versionNumber": version_number,
            }
        )
    return insights


def _insight_title(row: dict[str, Any], comparison: dict[str, Any]) -> str:
    label = row["label"]
    period_b = (comparison.get("periodB") or {}).get("label") or "?"
    period_a = (comparison.get("periodA") or {}).get("label") or "?"
    if comparison["kind"] == "versions":
        return f"{label} — {period_b} across versions"
    return f"{label} — {period_b} vs {period_a}"
