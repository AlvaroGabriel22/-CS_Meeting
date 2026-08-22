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

A department whose data is not "parts of a whole" gets a different chart
altogether.  FIELD writes a ``Target`` row and a ``Result`` row under each
model (``ASR / MX``, ``CASR / Mobile``), so its chart is one **pair** per
model: the result as bars, the target as the line over them
(``chart_kind="series_pair"``).  One table therefore yields several charts, and
which of them are shown is a setting like any other.

Two things here *are* arithmetic, and both are declared by the department
rather than assumed:

* a **share** (``chart_share``) splits a rate among its parts in proportion to
  a quantity that really adds up — IQC stacks the total PPM split by each
  part's share of the rejected lots, because PPM itself does not add up
  (ADR-0046).  Every figure involved is a cell of the workbook, and each
  plotted point carries the three addresses it came from;
* a **break** cuts the line where the period axis changes granularity — years
  and months in the same row are two blocks, not one trend, so nothing is
  drawn between 2026 and January (ADR-0047).

All of that is the *default*.  A presenter who wants ``SKD`` and ``CKD`` on the
bars with total ``PPM`` on the line says so in the configuration, and this
module plots exactly the rows they picked — from any metric the table carries
(ADR-0041).  The rows come from the workbook either way; the only thing being
chosen is which of them to draw.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.domain.departments import ChartShare, canonical, schema_for
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


def _series_label(selector: dict[str, Any]) -> str:
    """What to call a row inside a pair chart: ``Target`` / ``Result``."""
    return selector.get("seriesType") or selector.get("metric") or _short_label(selector)


def _full_label(selector: dict[str, Any]) -> str:
    """Every level of the row, so a chooser can tell two ``SKD`` rows apart."""
    parts = [
        selector.get("category"),
        selector.get("subcategory"),
        selector.get("metric"),
        selector.get("seriesType"),
    ]
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
            "seriesType": item["selector"].get("seriesType"),
        }
        for item in analytics.table_series(table)
        # a row is named either by what it measures (``PPM``) or by what it is
        # (``Target``) — FIELD writes the second kind and no metric at all
        if item["selector"].get("category")
        and (item["selector"].get("metric") or item["selector"].get("seriesType"))
    ]


# --------------------------------------------------------------------------- #
# Sharing a rate among its parts (ADR-0046)
# --------------------------------------------------------------------------- #
def _sibling(
    series: list[dict[str, Any]], selector: dict[str, Any], metric: str
) -> dict[str, Any] | None:
    """The same row of the table, read on another metric.

    ``SKD``'s ``Rej. Lot`` next to ``SKD``'s ``PPM`` — same category, same
    sub-group, different measurement.
    """
    for item in series:
        other = item["selector"]
        if (
            other.get("category") == selector.get("category")
            and other.get("subcategory") == selector.get("subcategory")
            and canonical(other.get("metric") or "") == canonical(metric)
        ):
            return item
    return None


def _leading_row(
    series: list[dict[str, Any]], department: str | None, metric: str
) -> dict[str, Any] | None:
    """The table's own total, on one metric."""
    for item in series:
        if _is_leading(item["selector"], department) and canonical(
            item["selector"].get("metric") or ""
        ) == canonical(metric):
            return item
    return None


class _Share:
    """Splits the whole among the parts, and remembers where each figure came from.

    A segment is ``whole x weight(part) / weight(total)``.  Nothing is invented:
    all three numbers are cells of the workbook, and the point that comes out
    carries their addresses so the chart can still prove itself.
    """

    def __init__(
        self,
        share: ChartShare,
        whole: dict[str, Any],
        weight_total: dict[str, Any],
        weights: dict[str, dict[str, Any]],
    ) -> None:
        self.share = share
        self._whole = {point["period"]["label"]: point for point in whole["points"]}
        self._weight_total = {point["period"]["label"]: point for point in weight_total["points"]}
        self._weights = {
            key: {point["period"]["label"]: point for point in item["points"]}
            for key, item in weights.items()
        }

    def applies_to(self, key: str) -> bool:
        return key in self._weights

    def point(self, key: str, period_label: str) -> dict[str, Any]:
        whole = self._whole.get(period_label) or {}
        total = self._weight_total.get(period_label) or {}
        part = self._weights[key].get(period_label) or {}
        whole_value, total_value, part_value = (
            whole.get("value"),
            total.get("value"),
            part.get("value"),
        )

        if whole_value is None or total_value is None or part_value is None:
            value = None
        elif total_value == 0:
            # nothing was rejected, so no part is responsible for anything —
            # and the whole is zero too.  A gap here would hide a real zero
            value = 0.0 if whole_value == 0 else None
        else:
            value = whole_value * part_value / total_value

        return {
            "period": period_label,
            "value": value,
            "display": None,
            # the number is not in any single cell, so it does not claim one
            "source": None,
            "derivedFrom": {
                "whole": whole.get("source"),
                "weight": part.get("source"),
                "weightTotal": total.get("source"),
            },
        }


def _share_for(
    table: TableOut,
    bars: list[dict[str, Any]],
    *,
    department: str | None,
    metric: str,
) -> _Share | None:
    """The share rule for this chart, when the department declares one and the
    table actually carries every figure it needs.

    Refuses quietly in every other case — a chart that cannot be split honestly
    is drawn with the file's own numbers instead.
    """
    schema = schema_for(department)
    share = schema.chart_share if schema else None
    if not share or not bars:
        return None
    if canonical(share.whole) != canonical(metric):
        return None
    if any(canonical(item["selector"].get("metric") or "") != canonical(metric) for item in bars):
        return None  # a chosen composition mixing metrics is plotted as it is

    everything = analytics.table_series(table)
    whole = _leading_row(everything, department, share.whole)
    weight_total = _leading_row(everything, department, share.weight)
    if whole is None or weight_total is None:
        return None

    weights: dict[str, dict[str, Any]] = {}
    for item in bars:
        weight = _sibling(everything, item["selector"], share.weight)
        if weight is None:
            return None  # one part without its weight would fake the whole
        weights[item["key"]] = weight
    return _Share(share, whole, weight_total, weights)


# --------------------------------------------------------------------------- #
# Where a line stops and starts again (ADR-0047)
# --------------------------------------------------------------------------- #
def _breaks(periods: list[dict[str, Any]]) -> list[int]:
    """Indices where the period axis changes granularity.

    A row that reads ``2025 | 2026 | Jan | Feb | …`` is two blocks: closing
    years and the months of the current one.  Drawing a segment from 2026 to
    January would state a trend between a year and a month, which is not a
    thing, so the line is cut there and the chart shows the seam.
    """
    return [
        index
        for index in range(1, len(periods))
        if periods[index].get("kind") != periods[index - 1].get("kind")
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

    bar_items = [item for item in series if item["key"] != line_key]

    # a stack of rates only means something once it is shared out; when the
    # department declares no share, or the table lacks a figure the share
    # needs, the bars keep the file's own numbers
    share = (
        _share_for(table, bar_items, department=department, metric=metric) if stacked else None
    )

    def points_of(item: dict[str, Any]) -> list[dict[str, Any]]:
        if share and share.applies_to(item["key"]):
            return [share.point(item["key"], period["label"]) for period in periods]
        return values_of(item)

    bars = [
        {"key": item["key"], "label": label_of(item), "points": points_of(item)}
        for item in bar_items
    ]
    line = next(
        (
            {"key": item["key"], "label": label_of(item), "points": values_of(item)}
            for item in pool.values()
            if item["key"] == line_key
        ),
        None,
    )

    name = table.title or table.sheet_name
    return {
        "id": name,
        "kind": "components",
        "table": name,
        "metric": metric,
        "sheet": table.sheet_name,
        "sourceRange": table.source_range,
        "stacked": stacked,
        "configured": configured,
        "enabled": True,
        "periods": periods,
        "bars": bars,
        "line": line,
        "breaks": [],
        "shared": bool(share),
        "share": (
            {"whole": share.share.whole, "weight": share.share.weight} if share else None
        ),
        "available": available_series(table),
    }


#: the plan a department sets itself, and the outcome it measures against it.
#: A pair chart draws the outcome as bars and the plan as the line over them.
PLAN_SERIES = ("Target", "Plan", "Forecast")
OUTCOME_SERIES = ("Result",)


def _pair_id(table_name: str, category: str | None, subcategory: str | None) -> str:
    """A chart's own name, since one table can hold several of them."""
    return " · ".join(part for part in (table_name, category, subcategory) if part)


def build_pair_charts(
    table: TableOut,
    *,
    department: str | None,
    configured: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """One chart per model: its result as bars, its target as the line.

    The models are whatever the table groups its rows into — ``ASR / MX``,
    ``ASR / Mobile``, ``CASR / Mobile`` — read from the hierarchy, never from a
    list.  A model is only a chart when the file gives it both series.

    By default the first model of each category is drawn, because that is the
    one the sheet leads with; the rest are there in the configuration for the
    presenter to switch on.  Nothing is hidden — every pair the workbook holds
    comes back, each saying whether it is currently shown.
    """
    name = table.title or table.sheet_name
    everything = analytics.table_series(table)
    configured = configured or {}

    groups: dict[tuple[str | None, str | None], dict[str, dict[str, Any]]] = {}
    for item in everything:
        selector = item["selector"]
        series_type = selector.get("seriesType")
        if not series_type or not selector.get("category"):
            continue
        key = (selector.get("category"), selector.get("subcategory"))
        groups.setdefault(key, {})[series_type] = item

    periods = [
        column.period.model_dump(by_alias=True) for column in table.columns if column.period
    ]
    breaks = _breaks(periods)

    def values_of(item: dict[str, Any]) -> list[dict[str, Any]]:
        by_label = {point["period"]["label"]: point for point in item["points"]}
        return [
            {
                "period": period["label"],
                # ``NA`` is not a zero: the target simply was not set
                "value": (by_label.get(period["label"]) or {}).get("value"),
                "display": (by_label.get(period["label"]) or {}).get("display"),
                "source": (by_label.get(period["label"]) or {}).get("source"),
            }
            for period in periods
        ]

    leading: set[str | None] = set()
    charts: list[dict[str, Any]] = []
    for (category, subcategory), found in groups.items():
        plan = next((found[key] for key in PLAN_SERIES if key in found), None)
        outcome = next((found[key] for key in OUTCOME_SERIES if key in found), None)
        if plan is None or outcome is None:
            continue

        first_of_category = category not in leading
        leading.add(category)

        chart_id = _pair_id(name, category, subcategory)
        config = configured.get(chart_id) or {}

        # the presenter may reach for any row of the table, not only this
        # model's two — the same freedom the components charts give (ADR-0041)
        pool = {item["key"]: item for item in everything}
        chosen = [pool[key] for key in config.get("bars", []) if key in pool]
        bars = chosen or [outcome]
        line = pool.get(config.get("line") or "") or plan

        # a chart that stays within its model names its rows by what they are;
        # one that reaches across models has to say which model each row is
        drawn = bars + [line]
        models = {
            (item["selector"].get("category"), item["selector"].get("subcategory"))
            for item in drawn
        }

        def name_of(item: dict[str, Any]) -> str:
            selector = item["selector"]
            if len(models) == 1:
                return _series_label(selector)
            return " · ".join(
                part
                for part in (_short_label(selector), selector.get("seriesType"))
                if part
            )

        charts.append(
            {
                "id": chart_id,
                "kind": "pair",
                "table": name,
                "category": category,
                "subcategory": subcategory,
                "metric": None,
                "sheet": table.sheet_name,
                "sourceRange": table.source_range,
                "stacked": False,
                "configured": bool(config.get("bars") or config.get("line")),
                # the first model of each category is the one the sheet leads
                # with; the presenter decides from there.  ``None`` is stored
                # by a composition that only chose rows, and means "as the
                # department decides" — not "off"
                "enabled": (
                    first_of_category
                    if config.get("enabled") is None
                    else bool(config["enabled"])
                ),
                "defaultEnabled": first_of_category,
                "periods": periods,
                "bars": [
                    {"key": item["key"], "label": name_of(item), "points": values_of(item)}
                    for item in bars
                    if item["key"] != line["key"]
                ],
                "line": {
                    "key": line["key"],
                    "label": name_of(line),
                    "points": values_of(line),
                },
                "breaks": breaks,
                "shared": False,
                "share": None,
                "available": available_series(table),
            }
        )
    return charts


def build_charts(
    tables: Sequence[TableOut],
    *,
    department: str | None = None,
    configured: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Every chart of a snapshot, in the order the workbook lists its tables.

    ``configured`` maps a chart's own id to the composition the presenter chose
    for it, exactly as the department settings store it.  For a department of
    one chart per table that id *is* the table's name, so a setting made before
    a table ever held two charts still finds its chart.
    """
    schema = schema_for(department)
    configured = configured or {}

    if schema and schema.chart_kind == "series_pair":
        charts = [
            chart
            for table in tables
            for chart in build_pair_charts(table, department=department, configured=configured)
        ]
        logger.info(
            "charts: %s — %d pair chart(s), %d shown",
            department,
            len(charts),
            sum(1 for chart in charts if chart["enabled"]),
        )
        return {"metric": None, "charts": charts}

    metric = headline_metric(tables, department)
    charts = []
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
