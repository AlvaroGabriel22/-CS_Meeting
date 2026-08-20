"""Presentation model contract.

Sprint 0 defines the shape; the endpoints that serve it arrive in Sprint 1+.

::

    Presentation
    ├── department        IQC | OQC | FIELD
    ├── versions[]        v1, v2, … (immutable once published)
    └── version
        ├── imports[]     referenced, never copied
        ├── tables[]      normalized tables from those imports
        ├── charts[]      selections *by label*, never by column index
        ├── issueReports[] rich documents (TipTap)
        ├── translations[] cache entries used by this version
        └── assets[]      images on disk, metadata in SQLite
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from .common import CamelModel
from .imports import DepartmentLiteral, ImportOut
from .table import TableSummaryOut

PresentationStatusLiteral = Literal["draft", "ready", "archived", "trashed"]
VersionStatusLiteral = Literal["draft", "published"]
ChartKindLiteral = Literal["line", "bar", "grouped-bar", "kpi", "target-result"]

#: a TipTap / ProseMirror document
RichDocument = dict[str, Any]


class ChartDefinitionOut(CamelModel):
    id: int
    order_index: int = 0
    kind: ChartKindLiteral = "line"
    title: str | None = None
    subtitle: str | None = None
    table_definition_id: int | None = None
    #: rows/periods/series are selected by *label* and sortKey so the chart
    #: survives a table that gained or lost columns (ADR-0002)
    config: dict[str, Any] = {}


class IssueReportCellOut(CamelModel):
    id: int
    row_id: int
    column_id: int
    doc: RichDocument = {}
    align: str = "left"
    valign: str = "top"


class IssueReportColumnOut(CamelModel):
    id: int
    index: int
    title: str = ""
    width: float | None = None
    align: str = "left"


class IssueReportRowOut(CamelModel):
    id: int
    index: int
    height: float | None = None


class IssueReportOut(CamelModel):
    id: int
    department: DepartmentLiteral
    order_index: int = 0
    title: str = ""
    language: str = "en"
    columns: list[IssueReportColumnOut] = []
    rows: list[IssueReportRowOut] = []
    cells: list[IssueReportCellOut] = []
    config: dict[str, Any] = {}


class AssetOut(CamelModel):
    id: int
    url: str  # served path, never a filesystem path
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None


class TranslationOut(CamelModel):
    source_hash: str
    source_language: str
    target_language: str
    provider: str
    cached: bool = True
    content: RichDocument = {}


class PresentationVersionOut(CamelModel):
    id: int
    number: int
    label: str | None = None
    status: VersionStatusLiteral = "draft"
    notes: str | None = None
    created_at: datetime
    published_at: datetime | None = None
    parent_version_id: int | None = None


class PresentationOut(CamelModel):
    id: int
    department: DepartmentLiteral
    name: str
    period_label: str | None = None
    status: PresentationStatusLiteral = "draft"
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    trashed_at: datetime | None = None
    latest_version: PresentationVersionOut | None = None
    version_count: int = 0
    issue_count: int = 0


class PresentationModelOut(CamelModel):
    """Everything the UI and the exporters need to render one version."""

    presentation: PresentationOut
    version: PresentationVersionOut
    imports: list[ImportOut] = []
    tables: list[TableSummaryOut] = []
    charts: list[ChartDefinitionOut] = []
    issue_reports: list[IssueReportOut] = []
    assets: list[AssetOut] = []
    language: str = "en"


class PresentationLimitOut(CamelModel):
    """Shown when the 8-presentation ceiling is reached (never auto-delete)."""

    limit: int
    active_count: int
    candidates: list[PresentationOut] = []
