"""Wire contract for the analytical layer (Sprint 3).

Everything here is expressed in the language of the normalized model —
department, table, category, subcategory, metric, period — and never in Excel
coordinates.  The coordinates travel along as provenance so any number on a
chart can be traced back to the cell, the file and the version it came from.
"""

from __future__ import annotations

from typing import Any, Literal

from .common import CamelModel
from .imports import DepartmentLiteral
from .table import PeriodOut

#: how a value behaved between two periods — a fact, not a judgement
DirectionLiteral = Literal["up", "down", "flat", "unknown"]
#: whether that movement is good or bad, only when the metric's polarity is known
SeverityLiteral = Literal["positive", "negative", "neutral", "unknown"]
#: why a comparison could not produce a number
StatusLiteral = Literal["ok", "missing_a", "missing_b", "undefined_percent"]


class SeriesSelectorOut(CamelModel):
    """What a series *is*, in model terms.  This is also its identity."""

    table: str | None = None
    category: str | None = None
    subcategory: str | None = None
    metric: str | None = None
    series_type: str | None = None

    @property
    def key(self) -> str:
        return "|".join(
            part or ""
            for part in (self.table, self.category, self.subcategory, self.metric, self.series_type)
        )


class SeriesPointOut(CamelModel):
    """One period of one series."""

    period: PeriodOut
    value: float | None = None
    display: str | None = None
    value_type: str = "empty"
    #: provenance: the exact cell this number came from
    source: str | None = None


class SeriesOut(CamelModel):
    key: str
    label: str
    selector: SeriesSelectorOut
    #: provenance of the whole series
    sheet: str | None = None
    source_range: str | None = None
    table_id: int | None = None
    points: list[SeriesPointOut] = []


class SelectorOptionsOut(CamelModel):
    """What the UI may offer, discovered from the snapshot itself."""

    tables: list[str] = []
    categories: list[str] = []
    subcategories: list[str] = []
    metrics: list[str] = []
    series_types: list[str] = []


class SeriesResponseOut(CamelModel):
    version_id: int
    department: DepartmentLiteral
    #: "file" keeps the workbook's column order, "chronological" uses sortKey
    order: Literal["file", "chronological"] = "file"
    periods: list[PeriodOut] = []
    series: list[SeriesOut] = []
    options: SelectorOptionsOut = SelectorOptionsOut()


class DeltaOut(CamelModel):
    """``B - A`` and its percentage, with the reason when there is none."""

    value_a: float | None = None
    value_b: float | None = None
    display_a: str | None = None
    display_b: str | None = None
    delta: float | None = None
    delta_percent: float | None = None
    direction: DirectionLiteral = "unknown"
    severity: SeverityLiteral = "unknown"
    status: StatusLiteral = "ok"


class ComparisonRowOut(CamelModel):
    key: str
    label: str
    selector: SeriesSelectorOut
    delta: DeltaOut
    source_a: str | None = None
    source_b: str | None = None


class ExecutiveInsightOut(CamelModel):
    """One statement an executive summary could be built from (Sprint 5+).

    Sprint 3 only produces these; nothing generates a presentation from them
    yet.  Every field needed to write a sentence *and* to prove it is here.
    """

    title: str
    department: DepartmentLiteral | None = None
    table: str | None = None
    category: str | None = None
    subcategory: str | None = None
    metric: str | None = None
    series_type: str | None = None
    period: PeriodOut | None = None
    reference_period: PeriodOut | None = None
    value: float | None = None
    previous_value: float | None = None
    display_value: str | None = None
    display_previous: str | None = None
    delta: float | None = None
    delta_percent: float | None = None
    direction: DirectionLiteral = "unknown"
    severity: SeverityLiteral = "unknown"
    status: StatusLiteral = "ok"
    #: provenance — cell, sheet range, version
    source: str | None = None
    source_range: str | None = None
    version_id: int | None = None
    version_number: int | None = None


class ComparisonResponseOut(CamelModel):
    """Two periods of one snapshot, or one period across two snapshots."""

    kind: Literal["periods", "versions"]
    version_id: int
    version_number: int | None = None
    compared_version_id: int | None = None
    compared_version_number: int | None = None
    department: DepartmentLiteral
    period_a: PeriodOut | None = None
    period_b: PeriodOut | None = None
    rows: list[ComparisonRowOut] = []
    insights: list[ExecutiveInsightOut] = []
    warnings: list[str] = []
    meta: dict[str, Any] = {}


# --------------------------------------------------------------------------- #
# Executive layer (Sprint 4)
# --------------------------------------------------------------------------- #
TargetStatusLiteral = Literal["above", "below", "at"]


class KpiOut(CamelModel):
    """One headline reading, derived from the model — never invented."""

    key: str
    label: str
    selector: SeriesSelectorOut
    period: PeriodOut
    value: float | None = None
    display: str | None = None
    value_type: str = "empty"
    #: the previous period *of the same kind* present in the file, if any
    previous_period: PeriodOut | None = None
    previous_value: float | None = None
    previous_display: str | None = None
    delta: float | None = None
    delta_percent: float | None = None
    direction: DirectionLiteral = "unknown"
    severity: SeverityLiteral = "unknown"
    status: StatusLiteral = "ok"
    #: "lower_is_better" / "higher_is_better" / "neutral" — declared, not guessed
    polarity: str | None = None
    #: only present when the workbook itself carries a target
    target: float | None = None
    target_display: str | None = None
    target_status: TargetStatusLiteral | None = None
    target_breached: bool = False
    source: str | None = None
    source_range: str | None = None


class InsightOut(CamelModel):
    """A statement a meeting can read, with everything needed to prove it.

    ``template`` + ``params`` let the UI render it in any language; ``text`` is
    the English rendering used by tests and, later, by the exporters.
    """

    kind: str
    template: str
    params: dict[str, Any] = {}
    text: str
    #: deterministic relevance (ADR-0027)
    score: float = 0.0
    direction: DirectionLiteral = "unknown"
    severity: SeverityLiteral = "unknown"
    status: StatusLiteral = "ok"
    value: float | None = None
    previous_value: float | None = None
    display_value: str | None = None
    display_previous: str | None = None
    delta: float | None = None
    delta_percent: float | None = None
    target: float | None = None
    target_status: TargetStatusLiteral | None = None
    # provenance
    department: DepartmentLiteral | None = None
    table: str | None = None
    category: str | None = None
    subcategory: str | None = None
    metric: str | None = None
    series_type: str | None = None
    period: PeriodOut | None = None
    reference_period: PeriodOut | None = None
    source: str | None = None
    source_range: str | None = None
    version_id: int | None = None
    version_number: int | None = None


class ExecutiveViewOut(CamelModel):
    """The executive header of a department page, in one call."""

    version_id: int
    version_number: int | None = None
    version_label: str | None = None
    department: DepartmentLiteral
    period: PeriodOut | None = None
    previous_period: PeriodOut | None = None
    #: "same_kind" (month vs month), "preceding" (the column before it) or "none"
    comparison_basis: Literal["same_kind", "preceding", "none"] = "none"
    metric: str | None = None
    periods: list[PeriodOut] = []
    options: SelectorOptionsOut = SelectorOptionsOut()
    kpis: list[KpiOut] = []
    insights: list[InsightOut] = []
    warnings: list[str] = []
