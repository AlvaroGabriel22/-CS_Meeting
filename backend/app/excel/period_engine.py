"""Period engine — resolving the time dimension of a whole table.

``periods.py`` reads one token at a time (``"3Q"`` -> quarter ``"3Q"``).  This module
looks at *all* the periods of a table together and answers the questions a
single token cannot:

* **Which year does an undated period belong to?**  A header reading
  ``'25 | '26 | 1Q | 2Q | 3Q | Aug`` states two years explicitly and leaves the
  quarters and the month undated: they belong to the current reporting year,
  which is the latest year written in the same header.
* **How do periods relate?**  ``1Q`` covers Jan/Feb/Mar, ``Aug`` sits inside
  ``3Q``, both sit inside ``2026``.  Quarters are always the canonical labels
  ``1Q``/``2Q``/``3Q``/``4Q``, never bare numbers.
* **In which order do they go?**  By year, then by granularity, then by ordinal
  — never by column position.

Nothing here knows that today is August 2026, that a quarter has closed, or
that a week exists.  It reads what the file says.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from .model import QUARTER_OF_MONTH, Period, PeriodKind

logger = logging.getLogger(__name__)

#: coarse to fine — used for ordering and for choosing the reporting year
GRANULARITY_RANK = {
    PeriodKind.YEAR: 0,
    PeriodKind.QUARTER: 1,
    PeriodKind.MONTH: 2,
    PeriodKind.WEEK: 3,
    PeriodKind.DAY: 4,
    PeriodKind.UNKNOWN: 5,
}

@dataclass
class PeriodResolution:
    """The resolved periods of one table plus what had to be inferred."""

    periods: list[Period]
    reporting_year: int | None = None
    inferred_years: int = 0
    warnings: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


def reporting_year(periods: list[Period]) -> int | None:
    """The year the table is reporting on.

    The latest year written explicitly in the header: a report showing
    ``'25 | '26`` is reporting 2026 and comparing it against 2025.
    """
    years = [period.year for period in periods if period.year and period.year_source != "inferred"]
    return max(years) if years else None


def enrich(period: Period, year: int | None) -> Period:
    """Fill in what can be derived: the quarter of a month, the reporting year."""
    quarter = period.quarter
    if period.kind is PeriodKind.MONTH and period.month and quarter is None:
        quarter = QUARTER_OF_MONTH[period.month]

    resolved_year = period.year
    year_source = period.year_source or ("explicit" if period.year else None)
    if resolved_year is None and year is not None and period.kind is not PeriodKind.UNKNOWN:
        resolved_year = year
        year_source = "inferred"

    if quarter == period.quarter and resolved_year == period.year and year_source == period.year_source:
        return period
    return replace(period, quarter=quarter, year=resolved_year, year_source=year_source)


def resolve(periods: list[Period]) -> PeriodResolution:
    """Resolve a table's periods against each other."""
    if not periods:
        return PeriodResolution(periods=[], reporting_year=None)

    year = reporting_year(periods)
    resolved = [enrich(period, year) for period in periods]
    inferred = sum(1 for period in resolved if period.year_source == "inferred")

    resolution = PeriodResolution(
        periods=resolved, reporting_year=year, inferred_years=inferred
    )
    undated = [period.label for period in resolved if period.year is None]
    if undated:
        resolution.warnings.append("period_without_year")
        logger.info("periods left without a year: %s", ", ".join(undated))
    return resolution


def sort_key(period: Period) -> tuple:
    """Chronological ordering across granularities, independent of position."""
    year = period.year if period.year is not None else 0
    quarter = period.quarter_number
    ordinal = period.week or period.month or (quarter * 3 if quarter else 0) or 0
    return (year, GRANULARITY_RANK[period.kind], ordinal, period.label)


def in_order(periods: list[Period]) -> list[Period]:
    return sorted(periods, key=sort_key)


def group_by_year(periods: list[Period]) -> dict[int | None, list[Period]]:
    grouped: dict[int | None, list[Period]] = {}
    for period in periods:
        grouped.setdefault(period.year, []).append(period)
    return grouped


def covering(period: Period, candidates: list[Period]) -> list[Period]:
    """The candidates that contain ``period`` (Aug -> [3Q, 2026])."""
    return [candidate for candidate in candidates if candidate.contains(period)]
