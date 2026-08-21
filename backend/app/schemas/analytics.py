"""Wire contract for the chart series.

Every point carries the cell it came from, so a number on a chart can always be
traced back to the workbook (ADR-0021).
"""

from __future__ import annotations

from typing import Any, Literal

from .common import CamelModel
from .imports import DepartmentLiteral
from .table import PeriodOut


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