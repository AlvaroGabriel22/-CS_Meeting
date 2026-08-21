"""Wire contract for the department page and its configuration.

Three shapes: the charts, the report the author builds, and the settings that
name things.  Everything else on a page comes from the workbook.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from .common import CamelModel
from .table import PeriodOut

AlignLiteral = Literal["left", "center", "right"]
BlockTypeLiteral = Literal["text", "image", "shape"]
ShapeLiteral = Literal["rectangle", "circle", "line", "arrow", "divider"]
TextSizeLiteral = Literal["small", "normal", "large", "heading"]


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
class ChartPointOut(CamelModel):
    """One column of one series.  ``value`` is null where the file has a gap."""

    period: str
    value: float | None = None
    display: str | None = None
    #: provenance: the cell the number came from
    source: str | None = None


class ChartSeriesOut(CamelModel):
    key: str
    label: str
    points: list[ChartPointOut] = []


class ChartOptionOut(CamelModel):
    """One row of the table a chart could plot."""

    key: str
    #: the most specific name — ``SKD``, ``Local``
    label: str
    #: every level, so two ``SKD`` rows can be told apart
    path: str
    category: str | None = None
    subcategory: str | None = None
    metric: str | None = None


class ChartOut(CamelModel):
    """One table's chart: its parts as bars, its total as a line."""

    table: str
    #: the name the user gave it in the settings, if any
    title: str | None = None
    metric: str
    sheet: str
    source_range: str
    #: True when the bars are the parts of the whole and stack into it
    stacked: bool = False
    #: True when the presenter chose what to plot instead of the default
    configured: bool = False
    periods: list[PeriodOut] = []
    bars: list[ChartSeriesOut] = []
    line: ChartSeriesOut | None = None
    #: everything this table could plot, for the configuration screen
    available: list[ChartOptionOut] = []


class ChartsResponseOut(CamelModel):
    version_id: int
    department: str
    metric: str | None = None
    charts: list[ChartOut] = []


# --------------------------------------------------------------------------- #
# The report
# --------------------------------------------------------------------------- #
class ReportBlockOut(CamelModel):
    """One piece of a cell.  A cell is an ordered list of these."""

    id: str
    type: BlockTypeLiteral
    align: AlignLiteral = "left"
    # text
    text: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    size: Any = None  # text size name, or shape size in points
    # image
    asset_id: int | None = None
    url: str | None = None
    caption: str | None = None
    width: int | None = None
    # shape
    shape: ShapeLiteral | None = None
    color: str | None = None


class ReportColumnOut(CamelModel):
    id: str
    name: str = ""


class ReportRowOut(CamelModel):
    id: str
    #: column id -> the blocks of that cell, in the author's order
    cells: dict[str, list[ReportBlockOut]] = {}


class ReportContentOut(CamelModel):
    title: str = ""
    columns: list[ReportColumnOut] = []
    rows: list[ReportRowOut] = []


class ReportMediaOut(CamelModel):
    id: int
    asset_id: int
    url: str
    mime_type: str
    size_bytes: int
    caption: str | None = None


class ReportOut(CamelModel):
    """The report a person wrote about one snapshot."""

    version_id: int
    department: str
    version_number: int | None = None
    version_label: str | None = None
    language: str = "en"
    content: ReportContentOut = ReportContentOut()
    text: str = ""
    translation_key: str | None = None
    media: list[ReportMediaOut] = []
    updated_at: datetime | None = None

    @property
    def is_empty(self) -> bool:  # pragma: no cover - convenience for callers
        return not (self.content.title or self.content.columns or self.content.rows)


class ReportSaveIn(CamelModel):
    content: dict[str, Any] = {}
    language: str = "en"


class UploadedImageOut(CamelModel):
    """An image the author can now place in a cell."""

    asset_id: int
    url: str
    mime_type: str
    size_bytes: int


class TranslationOut(CamelModel):
    """Everything a person wrote, in another language (ADR-0035, ADR-0039).

    Two kinds of authored text exist in this product and neither can be shipped
    in a language bundle, because neither is known before someone types it: the
    report, and the titles given to the charts and tables.  Everything else on
    the page is interface text or a label the workbook carries.
    """

    version_id: int
    department: str
    source_language: str
    target_language: str
    provider: str
    model: str | None = None
    #: the author's report, unchanged — always available
    original: ReportContentOut
    translated: ReportContentOut
    #: the titles from the department settings, keyed exactly as they are stored
    chart_titles: dict[str, str] = {}
    table_titles: dict[str, str] = {}
    string_count: int = 0
    cached_count: int = 0
    rejected_count: int = 0


class ReportSummaryOut(CamelModel):
    """One line of the reports library."""

    version_id: int
    department: str
    version_number: int | None = None
    version_label: str | None = None
    title: str = ""
    column_count: int = 0
    row_count: int = 0
    image_count: int = 0
    language: str = "en"
    updated_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class ChartSeriesChoiceOut(CamelModel):
    """What one chart plots, when the presenter chose it."""

    bars: list[str] = []
    line: str | None = None


class DepartmentSettingsOut(CamelModel):
    """What this department's charts and tables are called, and what they plot."""

    department: str
    chart_titles: dict[str, str] = {}
    table_titles: dict[str, str] = {}
    #: table name -> the composition chosen for its chart (ADR-0041)
    chart_series: dict[str, ChartSeriesChoiceOut] = {}


class DepartmentSettingsIn(CamelModel):
    chart_titles: dict[str, str] = {}
    table_titles: dict[str, str] = {}
    chart_series: dict[str, ChartSeriesChoiceOut] = {}
