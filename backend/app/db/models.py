"""SQLite schema.

Layering (see docs/data-model.md):

* **facts** — ``RawDataFile`` -> ``DepartmentData`` -> ``TableDefinition`` /
  ``TableColumn`` / ``TableRow`` / ``TableCell``.  Written once at import time
  and never edited: re-importing creates a new ``DepartmentData``.
* **editorial** — ``ChartDefinition`` and the ``IssueReport*`` family belong to
  a ``PresentationVersion`` and are what the user edits.
* **support** — ``Translation`` (cache), ``Asset`` (files on disk).

Imported tables are *referenced* by versions, never copied, so a new version
costs only the editable content.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Enum as SAEnum,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Department(str, enum.Enum):
    IQC = "IQC"
    OQC = "OQC"
    FIELD = "FIELD"


class PresentationStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    ARCHIVED = "archived"
    TRASHED = "trashed"


class VersionStatus(str, enum.Enum):
    DRAFT = "draft"  # autosave target, mutable
    PUBLISHED = "published"  # immutable snapshot created by "Save Version"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --------------------------------------------------------------------------- #
# Presentations & versions
# --------------------------------------------------------------------------- #
class Presentation(TimestampMixin, Base):
    __tablename__ = "presentations"

    id: Mapped[int] = mapped_column(primary_key=True)
    department: Mapped[Department] = mapped_column(SAEnum(Department, native_enum=False, length=16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    period_label: Mapped[str | None] = mapped_column(String(80))  # "W32/2026"
    status: Mapped[PresentationStatus] = mapped_column(
        SAEnum(PresentationStatus, native_enum=False, length=16),
        nullable=False,
        default=PresentationStatus.DRAFT,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime)  # recoverable bin
    notes: Mapped[str | None] = mapped_column(Text)

    versions: Mapped[list["PresentationVersion"]] = relationship(
        back_populates="presentation", cascade="all, delete-orphan", order_by="PresentationVersion.number"
    )

    @property
    def is_active(self) -> bool:
        return self.status not in (PresentationStatus.ARCHIVED, PresentationStatus.TRASHED)


class PresentationVersion(TimestampMixin, Base):
    __tablename__ = "presentation_versions"
    __table_args__ = (UniqueConstraint("presentation_id", "number", name="uq_version_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    presentation_id: Mapped[int] = mapped_column(
        ForeignKey("presentations.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # v1, v2, ...
    label: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[VersionStatus] = mapped_column(
        SAEnum(VersionStatus, native_enum=False, length=16), default=VersionStatus.DRAFT, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    parent_version_id: Mapped[int | None] = mapped_column(ForeignKey("presentation_versions.id"))
    #: what this snapshot shows — periods, table names, parser version
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    presentation: Mapped[Presentation] = relationship(back_populates="versions")
    imports: Mapped[list["DepartmentData"]] = relationship(
        secondary="version_imports", back_populates="versions"
    )
    charts: Mapped[list["ChartDefinition"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="ChartDefinition.order_index"
    )
    issue_reports: Mapped[list["IssueReport"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="IssueReport.order_index"
    )


class VersionImport(Base):
    """Which imported dataset each version shows (no data duplication)."""

    __tablename__ = "version_imports"

    version_id: Mapped[int] = mapped_column(
        ForeignKey("presentation_versions.id", ondelete="CASCADE"), primary_key=True
    )
    department_data_id: Mapped[int] = mapped_column(
        ForeignKey("department_data.id", ondelete="CASCADE"), primary_key=True
    )


# --------------------------------------------------------------------------- #
# Raw data & parsed facts
# --------------------------------------------------------------------------- #
class RawDataFile(TimestampMixin, Base):
    __tablename__ = "raw_data_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    department: Mapped[Department] = mapped_column(SAEnum(Department, native_enum=False, length=16), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)  # relative to data_dir
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    imports: Mapped[list["DepartmentData"]] = relationship(
        back_populates="raw_file", cascade="all, delete-orphan"
    )


class DepartmentData(TimestampMixin, Base):
    """One parse of one raw file: the immutable result of an import."""

    __tablename__ = "department_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    department: Mapped[Department] = mapped_column(SAEnum(Department, native_enum=False, length=16), nullable=False, index=True)
    raw_data_file_id: Mapped[int] = mapped_column(
        ForeignKey("raw_data_files.id", ondelete="CASCADE"), index=True
    )
    parser_version: Mapped[str] = mapped_column(String(20), nullable=False)
    parsed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)  # sheets, tables, periods found
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    raw_file: Mapped[RawDataFile] = relationship(back_populates="imports")
    tables: Mapped[list["TableDefinition"]] = relationship(
        back_populates="department_data", cascade="all, delete-orphan"
    )
    versions: Mapped[list[PresentationVersion]] = relationship(
        secondary="version_imports", back_populates="imports"
    )


class TableDefinition(Base):
    __tablename__ = "table_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    department_data_id: Mapped[int] = mapped_column(
        ForeignKey("department_data.id", ondelete="CASCADE"), index=True
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    sheet_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_range: Mapped[str] = mapped_column(String(40), nullable=False)  # provenance only
    title: Mapped[str | None] = mapped_column(String(300))
    department: Mapped[str | None] = mapped_column(String(16))
    #: label levels, outermost first: ["category", "subcategory", "metric"]
    hierarchy: Mapped[list] = mapped_column(JSON, default=list)
    shape: Mapped[str] = mapped_column(String(16), nullable=False)
    period_axis: Mapped[str] = mapped_column(String(16), nullable=False)
    header_row_count: Mapped[int] = mapped_column(Integer, default=0)
    label_col_count: Mapped[int] = mapped_column(Integer, default=0)
    merged_ranges: Mapped[list] = mapped_column(JSON, default=list)
    styles: Mapped[dict] = mapped_column(JSON, default=dict)  # style_id -> style
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    department_data: Mapped[DepartmentData] = relationship(back_populates="tables")
    columns: Mapped[list["TableColumn"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="TableColumn.index"
    )
    rows: Mapped[list["TableRow"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="TableRow.index"
    )
    cells: Mapped[list["TableCell"]] = relationship(
        back_populates="table", cascade="all, delete-orphan"
    )


class TableColumn(Base):
    __tablename__ = "table_columns"
    __table_args__ = (UniqueConstraint("table_definition_id", "index", name="uq_table_column"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    table_definition_id: Mapped[int] = mapped_column(
        ForeignKey("table_definitions.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_column: Mapped[str | None] = mapped_column(String(8))
    header_path: Mapped[list] = mapped_column(JSON, default=list)
    label: Mapped[str] = mapped_column(String(300), default="")
    period: Mapped[dict | None] = mapped_column(JSON)
    #: "Target" / "Result" / "Plan" — how the number was produced
    series_type: Mapped[str | None] = mapped_column(String(60))
    semantic: Mapped[str] = mapped_column(String(16), default="unknown")
    is_label_column: Mapped[bool] = mapped_column(Boolean, default=False)
    width: Mapped[float | None] = mapped_column(Float)

    table: Mapped[TableDefinition] = relationship(back_populates="columns")


class TableRow(Base):
    __tablename__ = "table_rows"
    __table_args__ = (UniqueConstraint("table_definition_id", "index", name="uq_table_row"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    table_definition_id: Mapped[int] = mapped_column(
        ForeignKey("table_definitions.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row: Mapped[int | None] = mapped_column(Integer)
    label_path: Mapped[list] = mapped_column(JSON, default=list)
    label: Mapped[str] = mapped_column(String(300), default="")
    level: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str | None] = mapped_column(String(160))
    subcategory: Mapped[str | None] = mapped_column(String(160))
    metric: Mapped[str | None] = mapped_column(String(160))
    series_type: Mapped[str | None] = mapped_column(String(60))
    #: label block (a group and the metrics under it)
    block: Mapped[int] = mapped_column(Integer, default=0)
    #: what the parser inferred rather than read
    inferred: Mapped[list] = mapped_column(JSON, default=list)
    semantic: Mapped[str] = mapped_column(String(16), default="unknown")
    is_header_row: Mapped[bool] = mapped_column(Boolean, default=False)
    period: Mapped[dict | None] = mapped_column(JSON)
    height: Mapped[float | None] = mapped_column(Float)

    table: Mapped[TableDefinition] = relationship(back_populates="rows")


class TableCell(Base):
    __tablename__ = "table_cells"
    __table_args__ = (
        Index("ix_table_cells_position", "table_definition_id", "row_index", "col_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    table_definition_id: Mapped[int] = mapped_column(
        ForeignKey("table_definitions.id", ondelete="CASCADE"), index=True
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    col_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    semantic: Mapped[str] = mapped_column(String(16), default="unknown")
    value_type: Mapped[str] = mapped_column(String(10), nullable=False)
    #: original — exactly as the workbook holds it
    raw_value: Mapped[str | None] = mapped_column(Text)
    #: interpreted
    number_value: Mapped[float | None] = mapped_column(Float)
    text_value: Mapped[str | None] = mapped_column(Text)
    display_value: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(20))
    formula: Mapped[str | None] = mapped_column(Text)
    number_format: Mapped[str | None] = mapped_column(String(80))
    display: Mapped[dict | None] = mapped_column(JSON)
    style_id: Mapped[str | None] = mapped_column(String(20))
    source_address: Mapped[str | None] = mapped_column(String(12))
    merged_range: Mapped[str | None] = mapped_column(String(24))
    is_merge_anchor: Mapped[bool] = mapped_column(Boolean, default=False)

    table: Mapped[TableDefinition] = relationship(back_populates="cells")


# --------------------------------------------------------------------------- #
# Editorial content
# --------------------------------------------------------------------------- #
class ChartDefinition(TimestampMixin, Base):
    __tablename__ = "chart_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("presentation_versions.id", ondelete="CASCADE"), index=True
    )
    table_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("table_definitions.id", ondelete="SET NULL")
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(24), default="line")  # line|bar|grouped-bar|kpi|target
    title: Mapped[str | None] = mapped_column(String(300))
    subtitle: Mapped[str | None] = mapped_column(String(300))
    #: which rows/periods/series are plotted — selection is by *label*, never by
    #: fixed index, so the chart survives a table that gained or lost columns
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    version: Mapped[PresentationVersion] = relationship(back_populates="charts")


class IssueReport(TimestampMixin, Base):
    __tablename__ = "issue_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("presentation_versions.id", ondelete="CASCADE"), index=True
    )
    department: Mapped[Department] = mapped_column(
        SAEnum(Department, native_enum=False, length=16), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(300), default="")
    language: Mapped[str] = mapped_column(String(10), default="en")  # language it was authored in
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    version: Mapped[PresentationVersion] = relationship(back_populates="issue_reports")
    columns: Mapped[list["IssueReportColumn"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="IssueReportColumn.index"
    )
    rows: Mapped[list["IssueReportRow"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="IssueReportRow.index"
    )
    cells: Mapped[list["IssueReportCell"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class IssueReportColumn(Base):
    __tablename__ = "issue_report_columns"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_report_id: Mapped[int] = mapped_column(
        ForeignKey("issue_reports.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="")
    width: Mapped[float | None] = mapped_column(Float)
    align: Mapped[str] = mapped_column(String(10), default="left")

    report: Mapped[IssueReport] = relationship(back_populates="columns")


class IssueReportRow(Base):
    __tablename__ = "issue_report_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_report_id: Mapped[int] = mapped_column(
        ForeignKey("issue_reports.id", ondelete="CASCADE"), index=True
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[float | None] = mapped_column(Float)

    report: Mapped[IssueReport] = relationship(back_populates="rows")


class IssueReportCell(Base):
    __tablename__ = "issue_report_cells"
    __table_args__ = (UniqueConstraint("row_id", "column_id", name="uq_issue_cell"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_report_id: Mapped[int] = mapped_column(
        ForeignKey("issue_reports.id", ondelete="CASCADE"), index=True
    )
    row_id: Mapped[int] = mapped_column(ForeignKey("issue_report_rows.id", ondelete="CASCADE"))
    column_id: Mapped[int] = mapped_column(ForeignKey("issue_report_columns.id", ondelete="CASCADE"))
    #: TipTap/ProseMirror document — text, marks, hard breaks and images live
    #: here together, which is what makes format-preserving translation possible
    doc: Mapped[dict] = mapped_column(JSON, default=dict)
    align: Mapped[str] = mapped_column(String(10), default="left")
    valign: Mapped[str] = mapped_column(String(10), default="top")

    report: Mapped[IssueReport] = relationship(back_populates="cells")


# --------------------------------------------------------------------------- #
# Support
# --------------------------------------------------------------------------- #
class Translation(Base):
    """Translation cache keyed by the *content hash* of the source document."""

    __tablename__ = "translations"
    __table_args__ = (
        UniqueConstraint("source_hash", "target_language", "provider", name="uq_translation"),
        Index("ix_translations_lookup", "source_hash", "target_language"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_language: Mapped[str] = mapped_column(String(10), nullable=False)
    target_language: Mapped[str] = mapped_column(String(10), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="null")
    model: Mapped[str | None] = mapped_column(String(60))
    source_preview: Mapped[str | None] = mapped_column(Text)  # first chars, for debugging
    content: Mapped[dict] = mapped_column(JSON, default=dict)  # translated rich document
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)


class Asset(TimestampMixin, Base):
    """An image on disk.  SQLite stores metadata only — never the bytes."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)  # relative to data_dir
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    original_filename: Mapped[str | None] = mapped_column(String(255))


class AssetUsage(Base):
    """Where an asset is referenced, so orphans can be found and cleaned up."""

    __tablename__ = "asset_usages"
    __table_args__ = (UniqueConstraint("asset_id", "cell_id", name="uq_asset_usage"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    cell_id: Mapped[int | None] = mapped_column(
        ForeignKey("issue_report_cells.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("presentation_versions.id", ondelete="CASCADE")
    )
