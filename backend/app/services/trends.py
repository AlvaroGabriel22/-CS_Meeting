"""Trend analysis over three or more comparable periods.

A trend is a *reading of a sequence*, so it needs three things the rest of the
system already provides: values, an order (the period engine) and a comparable
granularity.  Nothing here is learned, guessed or generated — the rules below
are the whole of it.

**Comparability.** Only periods of the same kind are compared: three months, or
three quarters, never a month against the quarter that contains it.  The finest
granularity that has at least three readings is the one analysed — a file with
three months and four quarters is read monthly — and the classification says
which granularity and how many periods it covers.

**Classification.**

======================  ==================================================
``rising``              every step that is not flat goes up
``falling``             every step that is not flat goes down
``stable``              every step is flat
``volatile``            steps go both ways
``insufficient_data``   fewer than three comparable values
======================  ==================================================

A step is **flat** when it moves less than :data:`FLAT_TOLERANCE` of the
previous value (2%).  The threshold exists because a report that reads 6,329
then 6,340 has not "risen"; 2% is the smallest movement the quality meetings
treat as real, and it is a constant here so it can be argued with.

**Quality.** Direction is arithmetic; whether it is good needs the metric's
declared polarity (ADR-0022): ``lower_is_better`` turns ``falling`` into
``improving``.  A ``neutral`` metric is never judged, and an undeclared one
stays ``unknown``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.domain.departments import schema_for
from app.excel import period_engine as PE

logger = logging.getLogger(__name__)

#: a step smaller than this fraction of the previous value is not a movement
FLAT_TOLERANCE = 0.02

#: a trend needs at least this many comparable readings
MIN_POINTS = 3

CLASSIFICATIONS = ("rising", "falling", "stable", "volatile", "insufficient_data")
QUALITIES = ("improving", "worsening", "stable", "neutral", "unknown")


@dataclass
class Trend:
    classification: str = "insufficient_data"
    quality: str = "unknown"
    #: how many comparable readings the classification is based on
    points: int = 0
    #: the granularity that was compared ("month", "quarter", …)
    granularity: str | None = None
    #: labels of the periods used, oldest first
    period_labels: list[str] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    #: how many consecutive steps at the end move the same way
    consecutive: int = 0
    first_value: float | None = None
    last_value: float | None = None
    change: float | None = None
    change_percent: float | None = None
    polarity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "quality": self.quality,
            "points": self.points,
            "granularity": self.granularity,
            "periodLabels": list(self.period_labels),
            "values": list(self.values),
            "consecutive": self.consecutive,
            "firstValue": self.first_value,
            "lastValue": self.last_value,
            "change": self.change,
            "changePercent": self.change_percent,
            "polarity": self.polarity,
        }


def _step_direction(previous: float, current: float) -> str:
    reference = max(abs(previous), 1e-9)
    if abs(current - previous) / reference < FLAT_TOLERANCE:
        return "flat"
    return "up" if current > previous else "down"


def comparable_run(points: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """The longest set of readings that can honestly be compared.

    Points are grouped by period kind — months with months, quarters with
    quarters — and the **finest granularity that has enough readings** wins: a
    file showing three months and four quarters is tracked monthly, because
    that is the most recent and most actionable reading.  When no granularity
    reaches three readings the largest group is returned anyway, so the caller
    can report ``insufficient_data`` with the numbers it does have.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for point in points:
        if point.get("value") is None:
            continue
        kind = (point.get("period") or {}).get("kind")
        if not kind or kind == "unknown":
            continue
        groups.setdefault(kind, []).append(point)

    if not groups:
        return []

    def rank(kind: str) -> int:
        from app.excel.model import PeriodKind

        try:
            return PE.GRANULARITY_RANK[PeriodKind(kind)]
        except ValueError:  # pragma: no cover - defensive
            return 99

    usable = {name: items for name, items in groups.items() if len(items) >= MIN_POINTS}
    if usable:
        # finest granularity first: month beats quarter beats year
        kind = max(usable, key=lambda name: rank(name))
    else:
        kind = max(groups, key=lambda name: (len(groups[name]), rank(name)))
    chosen = groups[kind]

    from app.services import analytics  # local import: avoids a cycle

    return sorted(chosen, key=lambda point: PE.sort_key(analytics._period(point["period"])))


def classify(
    points: Sequence[dict[str, Any]],
    *,
    metric: str | None = None,
    department: str | None = None,
) -> Trend:
    """Read a series as a trend."""
    schema = schema_for(department)
    polarity = schema.metric_polarity(metric) if schema and metric else None

    run = comparable_run(points)
    trend = Trend(polarity=polarity)
    if run:
        trend.granularity = (run[0].get("period") or {}).get("kind")
        trend.period_labels = [point["period"]["label"] for point in run]
        trend.values = [float(point["value"]) for point in run]
        trend.points = len(run)

    if trend.points < MIN_POINTS:
        trend.classification = "insufficient_data"
        trend.quality = "unknown"
        return trend

    steps = [
        _step_direction(previous, current)
        for previous, current in zip(trend.values, trend.values[1:])
    ]
    moving = [step for step in steps if step != "flat"]

    if not moving:
        trend.classification = "stable"
    elif all(step == "up" for step in moving):
        trend.classification = "rising"
    elif all(step == "down" for step in moving):
        trend.classification = "falling"
    else:
        trend.classification = "volatile"

    # how long the run at the end has been going the same way
    consecutive = 0
    for step in reversed(steps):
        if step == "flat" or (consecutive and step != steps[-1]):
            break
        if step != steps[-1]:
            break
        consecutive += 1
    trend.consecutive = consecutive

    trend.first_value = trend.values[0]
    trend.last_value = trend.values[-1]
    trend.change = trend.last_value - trend.first_value
    if trend.first_value:
        trend.change_percent = trend.change / trend.first_value * 100.0

    trend.quality = _quality(trend.classification, polarity)
    logger.debug(
        "trend %s over %d %s(s): %s",
        trend.classification,
        trend.points,
        trend.granularity,
        trend.quality,
    )
    return trend


def _quality(classification: str, polarity: str | None) -> str:
    """Good or bad — only when the department declared which way is better."""
    if classification in ("insufficient_data", "volatile"):
        return "unknown" if polarity != "neutral" else "neutral"
    if classification == "stable":
        return "stable"
    if polarity is None:
        return "unknown"
    if polarity == "neutral":
        return "neutral"
    if polarity == "lower_is_better":
        return "improving" if classification == "falling" else "worsening"
    return "improving" if classification == "rising" else "worsening"


def trend_of_series(
    series: dict[str, Any], *, department: str | None = None
) -> Trend:
    """Convenience wrapper: classify a series produced by ``analytics``."""
    return classify(
        series.get("points", []),
        metric=(series.get("selector") or {}).get("metric"),
        department=department,
    )
