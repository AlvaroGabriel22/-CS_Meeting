"""The executive layer: KPIs and insights, built from the normalized model.

Sprint 3 produced numbers (series, deltas). This module turns them into the
few statements a meeting actually reads — without ever going beyond what the
data supports.

Three rules govern everything here:

* **nothing is invented.** A KPI exists only if the metric exists in the
  snapshot; a target exists only if the workbook holds one; a cause is never
  stated, because no dataset in this system contains causes.
* **the reference period comes from the engine**, not from a calendar: the
  predecessor of a month is the previous month *present in the file*.  When the
  file holds none — the real IQC sheet shows a single month — the comparison
  falls back to the column before it and says so (``comparisonBasis:
  "preceding"``), so a month is never silently read as month-on-month
  (ADR-0025).
* **ranking is deterministic and documented** (see :func:`insight_score`).

Insights travel as a template key plus parameters, so the same statement reads
in English, Portuguese or Korean without an AI call (ADR-0026).
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.domain.departments import canonical, schema_for
from app.excel import period_engine as PE
from app.schemas.table import TableOut
from app.services import analytics
from app.services import trends as trend_engine

logger = logging.getLogger(__name__)

#: how many KPIs and insights a meeting can absorb
MAX_KPIS = 6
MAX_INSIGHTS = 6

#: weights of the ranking formula — documented in ADR-0027 and ADR-0031
WEIGHT_WRONG_DIRECTION = 50.0
WEIGHT_TARGET_BREACH = 25.0
#: a metric that keeps moving the wrong way over three or more periods
WEIGHT_TREND_WORSENING = 30.0
#: a consistent trend whose quality cannot be judged still deserves a look
WEIGHT_TREND_CONSISTENT = 10.0
PERCENT_CAP = 300.0


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #
def default_metric(tables: Sequence[TableOut], department: str | None) -> str | None:
    """The metric a summary leads with.

    The department's headline metric when it declares one (IQC: ``PPM``), else
    the first metric the snapshot happens to contain.  Never a name this module
    made up.
    """
    schema = schema_for(department)
    available = analytics.selector_options(tables)["metrics"]
    if schema and schema.headline_metric:
        for metric in available:
            if canonical(metric) == canonical(schema.headline_metric):
                return metric
    return available[0] if available else None


def _period_axis(tables: Sequence[TableOut]) -> list[dict[str, Any]]:
    return analytics.periods_of(tables, order="chronological")


def resolve_period(tables: Sequence[TableOut], label: str | None) -> dict[str, Any] | None:
    """The requested period, or the last one the file holds."""
    axis = _period_axis(tables)
    if not axis:
        return None
    if label:
        for payload in axis:
            if payload["label"] == label:
                return payload
    return axis[-1]


def reference_of(
    tables: Sequence[TableOut], period: dict[str, Any]
) -> tuple[dict[str, Any] | None, str]:
    """What the selected period is compared against, and on what basis.

    1. the previous period **of the same kind** present in the file — August
       against July, the third quarter against the second;
    2. failing that, the period immediately before it on the chronological
       axis, whatever its granularity, reported as ``preceding`` so the UI can
       say "vs 3Q" instead of implying a month-on-month reading (ADR-0025);
    3. failing that, nothing — and the view says so.
    """
    axis = _period_axis(tables)
    domain_axis = [analytics._period(payload) for payload in axis]
    current = analytics._period(period)

    same_kind = PE.previous_period(current, domain_axis)
    if same_kind is not None:
        payload = next((item for item in axis if item["label"] == same_kind.label), None)
        return payload, "same_kind"

    position = next((index for index, item in enumerate(axis) if item["label"] == period["label"]), 0)
    if position > 0:
        return axis[position - 1], "preceding"
    return None, "none"


def previous_of(tables: Sequence[TableOut], period: dict[str, Any]) -> dict[str, Any] | None:
    return reference_of(tables, period)[0]


# --------------------------------------------------------------------------- #
# Targets
# --------------------------------------------------------------------------- #
def find_target(series: Sequence[dict[str, Any]], selector: dict[str, Any]) -> dict[str, Any] | None:
    """A target for this row, if the workbook carries one.

    Two shapes are accepted, both of them things a file can actually say: a row
    of the same group whose *series type* is ``Target``, or a sibling metric
    literally called ``Target``.  Nothing else counts as a target.
    """
    for candidate in series:
        other = candidate["selector"]
        if other.get("table") != selector.get("table"):
            continue
        if other.get("category") != selector.get("category"):
            continue
        if other.get("subcategory") != selector.get("subcategory"):
            continue
        is_target_series = canonical(other.get("seriesType") or "") == "target"
        is_target_metric = canonical(other.get("metric") or "") == "target"
        if is_target_series or is_target_metric:
            return candidate
    return None


def target_status(value: float | None, target: float | None, polarity: str | None) -> str | None:
    """``above`` / ``below`` / ``at`` — a fact; the judgement needs polarity."""
    if value is None or target is None:
        return None
    if value > target:
        return "above"
    if value < target:
        return "below"
    return "at"


def target_is_breached(status: str | None, polarity: str | None) -> bool:
    """Only a declared polarity can say which side of a target is the bad one."""
    if status is None or polarity is None:
        return False
    if polarity == "lower_is_better":
        return status == "above"
    if polarity == "higher_is_better":
        return status == "below"
    return False


# --------------------------------------------------------------------------- #
# KPIs
# --------------------------------------------------------------------------- #
def build_kpis(
    tables: Sequence[TableOut],
    *,
    period: dict[str, Any],
    previous: dict[str, Any] | None,
    table: str | None = None,
    metric: str | None = None,
    department: str | None = None,
    limit: int = MAX_KPIS,
) -> list[dict[str, Any]]:
    """One KPI per top-level category of the chosen table and metric.

    Top-level means a row without a sub-group: the reading a meeting opens
    with.  Sub-groups (``SKD``, ``CKD``) stay available in the tables and the
    charts.
    """
    metric = metric or default_metric(tables, department)
    if metric is None:
        return []

    filters = {"table": table, "metric": metric}
    series: list[dict[str, Any]] = []
    for item in tables:
        series.extend(analytics.table_series(item, filters=filters))
    all_series: list[dict[str, Any]] = []
    for item in tables:
        all_series.extend(analytics.table_series(item))

    schema = schema_for(department)
    polarity = schema.metric_polarity(metric) if schema else None

    kpis: list[dict[str, Any]] = []
    for candidate in series:
        selector = candidate["selector"]
        if selector.get("subcategory"):
            continue  # sub-groups are detail, not headline

        current = analytics._point_for(candidate, period["label"])
        earlier = analytics._point_for(candidate, previous["label"]) if previous else None
        delta = analytics.compute_delta(earlier, current, metric=metric, department=department)

        trend = trend_engine.trend_of_series(candidate, department=department).to_dict()
        target_series = find_target(all_series, selector)
        target_point = (
            analytics._point_for(target_series, period["label"]) if target_series else None
        )
        target_value = (target_point or {}).get("value")
        status = target_status((current or {}).get("value"), target_value, polarity)

        kpis.append(
            {
                "key": candidate["key"],
                "label": analytics.selector_label(selector),
                "selector": selector,
                "period": period,
                "value": (current or {}).get("value"),
                "display": (current or {}).get("display"),
                "valueType": (current or {}).get("valueType", "empty"),
                "previousPeriod": previous,
                "previousValue": delta["valueA"],
                "previousDisplay": delta["displayA"],
                "delta": delta["delta"],
                "deltaPercent": delta["deltaPercent"],
                "direction": delta["direction"],
                "severity": delta["severity"],
                "status": delta["status"],
                "polarity": polarity,
                "trend": trend,
                "target": target_value,
                "targetDisplay": (target_point or {}).get("display"),
                "targetStatus": status,
                "targetBreached": target_is_breached(status, polarity),
                "source": (current or {}).get("source"),
                "sourceRange": candidate.get("sourceRange"),
            }
        )
        if len(kpis) >= limit:
            break
    return kpis


# --------------------------------------------------------------------------- #
# Insights
# --------------------------------------------------------------------------- #
def insight_score(
    *,
    delta_percent: float | None,
    delta: float | None,
    severity: str,
    target_breached: bool,
    trend: dict[str, Any] | None = None,
) -> float:
    """Deterministic relevance score (ADR-0027, extended by ADR-0031).

    ``|Δ%| (capped at 300)
      + 50 when the movement is in the declared wrong direction
      + 25 when the value is on the wrong side of a target the file carries
      + 30 when the trend over three or more periods is worsening
      + 10 when the trend is consistent but its quality cannot be judged``.

    Every term is something the data states; nothing is learned or weighted by
    taste, and the cap stops a percentage against a tiny baseline from drowning
    everything else.
    """
    score = min(abs(delta_percent or 0.0), PERCENT_CAP)
    if severity == "negative":
        score += WEIGHT_WRONG_DIRECTION
    if target_breached:
        score += WEIGHT_TARGET_BREACH
    if trend:
        classification = trend.get("classification")
        quality = trend.get("quality")
        if quality == "worsening":
            score += WEIGHT_TREND_WORSENING
        elif classification in ("rising", "falling") and quality in ("unknown", "neutral"):
            score += WEIGHT_TREND_CONSISTENT
    if delta_percent is None and delta:
        score += 1.0  # a movement with no percentage still beats no movement
    return round(score, 3)


def _movement_insight(kpi: dict[str, Any], department: str | None) -> dict[str, Any] | None:
    if kpi["delta"] is None:
        return None
    rising = kpi["direction"] == "up"
    params = {
        "label": kpi["label"],
        "metric": kpi["selector"].get("metric"),
        "period": kpi["period"]["label"],
        "previousPeriod": (kpi["previousPeriod"] or {}).get("label"),
        "from": kpi["previousDisplay"],
        "to": kpi["display"],
        "percent": None
        if kpi["deltaPercent"] is None
        else f"{abs(kpi['deltaPercent']):.1f}%",
        "delta": f"{abs(kpi['delta']):,.0f}",
    }
    kind = "metric_moved" if kpi["deltaPercent"] is not None else "metric_moved_absolute"
    # the direction is part of the key: a sentence reads "rose"/"fell" in every
    # language without an ICU plugin in the UI (ADR-0026)
    template = f"{kind}_{'up' if rising else 'down'}"
    text = _render(kind, params, rising)
    return _insight(
        kind=kind,
        template=template,
        params=params | {"direction": kpi["direction"]},
        text=text,
        kpi=kpi,
        department=department,
        score=insight_score(
            delta_percent=kpi["deltaPercent"],
            delta=kpi["delta"],
            severity=kpi["severity"],
            target_breached=kpi["targetBreached"],
            trend=kpi.get("trend"),
        ),
    )


def _trend_insight(kpi: dict[str, Any], department: str | None) -> dict[str, Any] | None:
    """A statement about the sequence, not about one step.

    Only produced when the file actually holds three or more comparable
    readings; "not enough history" is a state of the KPI, not a headline.
    """
    trend = kpi.get("trend") or {}
    if trend.get("classification") not in ("rising", "falling"):
        return None
    if trend.get("points", 0) < trend_engine.MIN_POINTS:
        return None

    rising = trend["classification"] == "rising"
    params = {
        "label": kpi["label"],
        "metric": kpi["selector"].get("metric"),
        "points": trend["points"],
        "granularity": trend.get("granularity"),
        "from": trend["periodLabels"][0],
        "to": trend["periodLabels"][-1],
        "percent": None
        if trend.get("changePercent") is None
        else f"{abs(trend['changePercent']):.1f}%",
        "quality": trend.get("quality"),
    }
    word = "risen" if rising else "fallen"
    text = (
        f"{params['label']} has {word} across {params['points']} consecutive "
        f"{params['granularity']}s ({params['from']} → {params['to']})."
    )
    return _insight(
        kind="trend",
        template=f"trend_{'up' if rising else 'down'}",
        params=params,
        text=text,
        kpi=kpi,
        department=department,
        score=insight_score(
            delta_percent=trend.get("changePercent"),
            delta=trend.get("change"),
            severity="negative" if trend.get("quality") == "worsening" else kpi["severity"],
            target_breached=kpi["targetBreached"],
            trend=trend,
        ),
    )


def _target_insight(kpi: dict[str, Any], department: str | None) -> dict[str, Any] | None:
    if kpi["targetStatus"] is None or kpi["targetStatus"] == "at":
        return None
    params = {
        "label": kpi["label"],
        "period": kpi["period"]["label"],
        "value": kpi["display"],
        "target": kpi["targetDisplay"],
        "status": kpi["targetStatus"],
    }
    text = (
        f"{params['label']} is {params['status']} target in {params['period']} "
        f"({params['value']} vs {params['target']})."
    )
    return _insight(
        kind="target_status",
        template=f"target_{params['status']}",
        params=params,
        text=text,
        kpi=kpi,
        department=department,
        score=insight_score(
            delta_percent=kpi["deltaPercent"],
            delta=kpi["delta"],
            severity=kpi["severity"],
            target_breached=kpi["targetBreached"],
            trend=kpi.get("trend"),
        )
        + (WEIGHT_TARGET_BREACH if kpi["targetBreached"] else 0.0),
    )


def _extreme_insight(kpis: Sequence[dict[str, Any]], department: str | None) -> dict[str, Any] | None:
    """Which category moved most — a comparison, never a cause."""
    movers = [kpi for kpi in kpis if kpi["deltaPercent"] is not None]
    if len(movers) < 2:
        return None
    leader = max(movers, key=lambda kpi: abs(kpi["deltaPercent"]))
    rising = leader["direction"] == "up"
    params = {
        "label": leader["label"],
        "category": leader["selector"].get("category"),
        "metric": leader["selector"].get("metric"),
        "period": leader["period"]["label"],
        "percent": f"{abs(leader['deltaPercent']):.1f}%",
        "count": len(movers),
    }
    word = "increase" if rising else "decrease"
    text = (
        f"{params['category']} showed the largest {word} in {params['metric']} "
        f"among the {params['count']} categories analysed ({params['percent']} in "
        f"{params['period']})."
    )
    return _insight(
        kind="largest_movement",
        template=f"largest_movement_{'up' if rising else 'down'}",
        params=params | {"direction": leader["direction"]},
        text=text,
        kpi=leader,
        department=department,
        score=insight_score(
            delta_percent=leader["deltaPercent"],
            delta=leader["delta"],
            severity=leader["severity"],
            target_breached=leader["targetBreached"],
            trend=leader.get("trend"),
        ),
    )


def _render(template: str, params: dict[str, Any], rising: bool) -> str:
    word = "rose" if rising else "fell"
    if template == "metric_moved":
        return (
            f"{params['label']} {word} {params['percent']} in {params['period']} "
            f"({params['from']} → {params['to']})."
        )
    return (
        f"{params['label']} {word} by {params['delta']} in {params['period']} "
        f"({params['from']} → {params['to']})."
    )


def _insight(
    *,
    kind: str,
    template: str,
    params: dict[str, Any],
    text: str,
    kpi: dict[str, Any],
    department: str | None,
    score: float,
) -> dict[str, Any]:
    selector = kpi["selector"]
    return {
        # what to say — the frontend renders the template in the user's language
        "kind": kind,
        "template": f"insights.{template}",
        "params": params,
        "text": text,
        "score": score,
        # how it behaved
        "direction": kpi["direction"],
        "severity": kpi["severity"],
        "status": kpi["status"],
        "value": kpi["value"],
        "previousValue": kpi["previousValue"],
        "displayValue": kpi["display"],
        "displayPrevious": kpi["previousDisplay"],
        "delta": kpi["delta"],
        "deltaPercent": kpi["deltaPercent"],
        "target": kpi["target"],
        "targetStatus": kpi["targetStatus"],
        "trend": kpi.get("trend"),
        # where it came from
        "department": department,
        "table": selector.get("table"),
        "category": selector.get("category"),
        "subcategory": selector.get("subcategory"),
        "metric": selector.get("metric"),
        "seriesType": selector.get("seriesType"),
        "period": kpi["period"],
        "referencePeriod": kpi["previousPeriod"],
        "source": kpi["source"],
        "sourceRange": kpi["sourceRange"],
    }


def build_insights(
    kpis: Sequence[dict[str, Any]],
    *,
    department: str | None,
    version_id: int | None = None,
    version_number: int | None = None,
    limit: int = MAX_INSIGHTS,
) -> list[dict[str, Any]]:
    """Rank what the KPIs say, most relevant first."""
    produced: list[dict[str, Any]] = []
    for kpi in kpis:
        for insight in (
            _movement_insight(kpi, department),
            _trend_insight(kpi, department),
            _target_insight(kpi, department),
        ):
            if insight:
                produced.append(insight)
    extreme = _extreme_insight(kpis, department)
    if extreme:
        produced.append(extreme)

    produced.sort(
        key=lambda item: (-item["score"], -abs(item["delta"] or 0.0), item["text"])
    )
    for insight in produced:
        insight["versionId"] = version_id
        insight["versionNumber"] = version_number
    return produced[:limit]


# --------------------------------------------------------------------------- #
# The page in one call
# --------------------------------------------------------------------------- #
def build_executive_view(
    tables: Sequence[TableOut],
    *,
    period_label: str | None,
    table: str | None = None,
    metric: str | None = None,
    department: str | None = None,
    version_id: int | None = None,
    version_number: int | None = None,
) -> dict[str, Any]:
    """Everything the executive header of a department page needs."""
    period = resolve_period(tables, period_label)
    if period is None:
        return {
            "period": None,
            "previousPeriod": None,
            "comparisonBasis": "none",
            "metric": None,
            "kpis": [],
            "insights": [],
            "options": analytics.selector_options(tables),
            "periods": [],
            "warnings": ["no_period_in_snapshot"],
        }

    previous, basis = reference_of(tables, period)
    chosen_metric = metric or default_metric(tables, department)
    kpis = build_kpis(
        tables,
        period=period,
        previous=previous,
        table=table,
        metric=chosen_metric,
        department=department,
    )
    insights = build_insights(
        kpis, department=department, version_id=version_id, version_number=version_number
    )

    warnings: list[str] = []
    if previous is None:
        warnings.append("no_reference_period_in_snapshot")
    elif basis == "preceding":
        # the file holds no earlier period of the same granularity, so the
        # comparison is against the column before it — labelled, never implied
        warnings.append("reference_period_is_preceding_column")
    if not any(kpi["target"] is not None for kpi in kpis):
        warnings.append("no_target_in_snapshot")
    if kpis and all(
        (kpi.get("trend") or {}).get("classification") == "insufficient_data" for kpi in kpis
    ):
        warnings.append("insufficient_history_for_trend")

    logger.info(
        "executive view: %s %s — %d KPI(s), %d insight(s)",
        department,
        period["label"],
        len(kpis),
        len(insights),
    )
    return {
        "period": period,
        "previousPeriod": previous,
        "comparisonBasis": basis,
        "metric": chosen_metric,
        "kpis": kpis,
        "insights": insights,
        "options": analytics.selector_options(tables),
        "periods": analytics.periods_of(tables),
        "warnings": warnings,
    }
