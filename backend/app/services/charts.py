"""The charts of a department page.

The user does the arithmetic in Excel before uploading; this layer neither
recomputes nor interprets anything.  It reads the values the workbook already
holds and arranges them for drawing: one chart per table, in the order the file
lists them (ADR-0036).

Each chart is a **column chart with a line over it**:

* the **bars** are the parts of the table, across the periods the file carries;
* the **line** is the table's leading group (``Total``), drawn over them so the
  whole is readable against its parts.

How the bars stand depends on the department, because it depends on whether the
parts actually add up — and only the real workbook can say (ADR-0037):

* ``chart_bars="stacked"`` (IQC) — the bars are the **leaf components**: a
  category with sub-groups contributes its sub-groups (``SKD``, ``CKD``), one
  without them contributes itself (``Local``).  Stacked, they read as the
  whole, with the ``Total`` line over them;
* ``chart_bars="grouped"`` (the default, and everything not yet confirmed) —
  one bar per category, side by side.

Nothing here is hardcoded.  The metric is the department's headline metric when
it declares one, otherwise the first metric the snapshot happens to contain; the
components are whatever the hierarchy found; the periods are the file's own
columns; and the line follows the department's implicit group label.  A
different file draws a different chart with no code change.

All of that is the *default*.  A presenter who wants ``SKD`` and ``CKD`` on the
bars with total ``PPM`` on the line says so in the configuration, and this
module plots exactly the rows they picked — from any metric the table carries
(ADR-0041).  The rows come from the workbook either way; the only thing being
chosen is which of them to draw.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.domain.departments import canonical, schema_for
from app.schemas.table import TableOut
from app.services import analytics

logger = logging.getLogger(__name__)


def headline_metric(tables: Sequence[TableOut], department: str | None) -> str | None:
    """The metric the charts plot.

    The department's declared headline metric when the snapshot actually has
    it, else the first metric present.  Never a name this module made up.
    """
    metrics: list[str] = []
    for table in tables:
        for row in table.rows:
            if row.metric and row.metric not in metrics:
                metrics.append(row.metric)
    if not metrics:
        return None

    schema = schema_for(department)
    declared = schema.headline_metric if schema else None
    if declared:
        for metric in metrics:
            if canonical(metric) == canonical(declared):
                return metric
    return metrics[0]


def _is_leading(selector: dict[str, Any], department: str | None) -> bool:
    """True when this row is the table's own total rather than a part of it."""
    schema = schema_for(department)
    leading = schema.implicit_group_label if schema else None
    if not leading:
        return False
    return canonical(selector.get("category") or "") == canonical(leading) and not selector.get(
        "subcategory"
    )


def _components(series: list[dict[str, Any]], department: str | None) -> list[dict[str, Any]]:
    """The parts of the table, at the deepest level each one reaches.

    A category that has sub-groups is represented by those sub-groups (they are
    what actually add up); a category without them is represented by itself.
    The leading group is never a part — it is the whole, and it is the line.
    """
    parts = [item for item in series if not _is_leading(item["selector"], department)]
    with_subgroups = {
        item["selector"]["category"] for item in parts if item["selector"].get("subcategory")
    }
    return [
        item
        for item in parts
        if item["selector"].get("subcategory")
        or item["selector"]["category"] not in with_subgroups
    ]


def _line_key(series: list[dict[str, Any]], department: str | None) -> str | None:
    """Which series is drawn as the line rather than as bars.

    The department's leading group when the snapshot has it (IQC: ``Total``),
    otherwise the first series — a line over the bars is only useful when it is
    the whole against its parts, and the whole is whatever the file leads with.
    """
    schema = schema_for(department)
    leading = schema.implicit_group_label if schema else None
    if leading:
        for item in series:
            selector = item["selector"]
            if canonical(selector.get("category") or "") == canonical(leading) and not selector.get(
                "subcategory"
            ):
                return item["key"]
    return series[0]["key"] if series else None


def _short_label(selector: dict[str, Any]) -> str:
    """The most specific name of a row: the sub-group, else the category."""
    return selector.get("subcategory") or selector.get("category") or ""


def _full_label(selector: dict[str, Any]) -> str:
    """Every level of the row, so a chooser can tell two ``SKD`` rows apart."""
    parts = [selector.get("category"), selector.get("subcategory"), selector.get("metric")]
    return " · ".join(part for part in parts if part)


def available_series(table: TableOut) -> list[dict[str, Any]]:
    """Every row of the table a chart could plot, in the file's order.

    Offered to the configuration screen so the presenter picks from what the
    workbook actually has — never from a list this system made up.
    """
    return [
        {
            "key": item["key"],
            "label": _short_label(item["selector"]),
            "path": _full_label(item["selector"]),
            "category": item["selector"].get("category"),
            "subcategory": item["selector"].get("subcategory"),
            "metric": item["selector"].get("metric"),
        }
        for item in analytics.table_series(table)
        if item["selector"].get("category") and item["selector"].get("metric")
    ]


def build_chart(
    table: TableOut,
    *,
    metric: str,
    department: str | None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """One chart for one table, or ``None`` when it holds nothing to plot.

    ``config`` is the composition the presenter chose — ``{"bars": [key, …],
    "line": key}``.  Keys the workbook no longer has are ignored, and a
    configuration that selects nothing falls back to the automatic rule, so a
    chart is never left empty by a stale setting.
    """
    everything = {item["key"]: item for item in analytics.table_series(table)}
    found = [
        item
        for item in analytics.table_series(table, filters={"metric": metric})
        if item["selector"].get("category")
    ]

    schema = schema_for(department)
    stacked = bool(schema and schema.chart_bars == "stacked")

    chosen_bars = [everything[key] for key in (config or {}).get("bars", []) if key in everything]
    chosen_line = everything.get((config or {}).get("line") or "")
    configured = bool(chosen_bars or chosen_line)

    if configured:
        series = chosen_bars
        line_key = chosen_line["key"] if chosen_line else None
        pool = {item["key"]: item for item in series}
        if chosen_line:
            pool[chosen_line["key"]] = chosen_line
    else:
        if not found:
            return None
        if stacked:
            # the parts that add up to the whole: SKD, CKD, Local
            series = _components(found, department)
        else:
            # one bar per category; sub-groups stay in the table as detail
            top_level = [item for item in found if not item["selector"].get("subcategory")]
            series = top_level or found
        line_key = _line_key(found, department)
        pool = {item["key"]: item for item in found}

    if not series and not chosen_line:
        return None

    periods = [
        column.period.model_dump(by_alias=True) for column in table.columns if column.period
    ]

    def values_of(item: dict[str, Any]) -> list[dict[str, Any]]:
        by_label = {point["period"]["label"]: point for point in item["points"]}
        return [
            {
                "period": period["label"],
                # a period the row does not reach is a gap, never a zero
                "value": (by_label.get(period["label"]) or {}).get("value"),
                "display": (by_label.get(period["label"]) or {}).get("display"),
                "source": (by_label.get(period["label"]) or {}).get("source"),
            }
            for period in periods
        ]

    # a sub-group names itself (SKD, CKD); a category without one keeps its own
    # name (Local).  When the chart mixes metrics — which only a chosen
    # composition can do — the metric is added, or two rows would read alike.
    drawn = list(series) + ([chosen_line] if chosen_line else [])
    mixed = len({item["selector"].get("metric") for item in drawn}) > 1

    def label_of(item: dict[str, Any]) -> str:
        selector = item["selector"]
        name = _short_label(selector)
        return f"{name} · {selector['metric']}" if mixed and selector.get("metric") else name

    bars = [
        {"key": item["key"], "label": label_of(item), "points": values_of(item)}
        for item in series
        if item["key"] != line_key
    ]
    line = next(
        (
            {"key": item["key"], "label": label_of(item), "points": values_of(item)}
            for item in pool.values()
            if item["key"] == line_key
        ),
        None,
    )

    return {
        "table": table.title or table.sheet_name,
        "metric": metric,
        "sheet": table.sheet_name,
        "sourceRange": table.source_range,
        "stacked": stacked,
        "configured": configured,
        "periods": periods,
        "bars": bars,
        "line": line,
        "available": available_series(table),
    }


def build_charts(
    tables: Sequence[TableOut],
    *,
    department: str | None = None,
    configured: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Every chart of a snapshot, in the order the workbook lists its tables.

    ``configured`` maps a table's own name to the composition the presenter
    chose for it, exactly as the department settings store it.
    """
    metric = headline_metric(tables, department)
    configured = configured or {}
    charts: list[dict[str, Any]] = []
    if metric:
        for table in tables:
            name = table.title or table.sheet_name
            chart = build_chart(
                table,
                metric=metric,
                department=department,
                config=configured.get(name),
            )
            if chart is not None:
                charts.append(chart)

    logger.info(
        "charts: %s — %d chart(s) on %s", department, len(charts), metric or "no metric"
    )
    return {"metric": metric, "charts": charts}
