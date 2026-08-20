"""Database rows -> wire contract."""

from __future__ import annotations

from app.db.models import DepartmentData, PresentationVersion, TableDefinition
from app.db.models import Presentation  # noqa: F401  (typing)
from app.schemas.imports import ImportOut, RawFileOut
from app.schemas.presentation import PresentationOut, PresentationVersionOut
from app.schemas.table import (
    CellStyleOut,
    PeriodOut,
    TableCellOut,
    TableColumnOut,
    TableOut,
    TableRowOut,
    TableSummaryOut,
)


def _period(payload: dict | None) -> PeriodOut | None:
    return PeriodOut.model_validate(payload) if payload else None


def table_out(definition: TableDefinition) -> TableOut:
    return TableOut(
        id=definition.id,
        sheet_name=definition.sheet_name,
        source_range=definition.source_range,
        title=definition.title,
        department=definition.department,
        hierarchy=definition.hierarchy or [],
        shape=definition.shape,
        period_axis=definition.period_axis,
        header_row_count=definition.header_row_count,
        label_col_count=definition.label_col_count,
        columns=[
            TableColumnOut(
                index=column.index,
                source_column=column.source_column,
                header_path=column.header_path or [],
                label=column.label,
                period=_period(column.period),
                series_type=column.series_type,
                semantic=column.semantic or "unknown",
                is_label_column=column.is_label_column,
                width=column.width,
            )
            for column in definition.columns
        ],
        rows=[
            TableRowOut(
                index=row.index,
                source_row=row.source_row,
                label_path=row.label_path or [],
                label=row.label,
                level=row.level,
                category=row.category,
                subcategory=row.subcategory,
                metric=row.metric,
                series_type=row.series_type,
                semantic=row.semantic or "unknown",
                is_header_row=row.is_header_row,
                period=_period(row.period),
                height=row.height,
            )
            for row in definition.rows
        ],
        cells=[
            TableCellOut(
                row=cell.row_index,
                col=cell.col_index,
                role=cell.role,
                semantic=cell.semantic or "unknown",
                value_type=cell.value_type,
                raw_value=cell.raw_value,
                number=cell.number_value,
                text=cell.text_value,
                display_value=cell.display_value,
                error_code=cell.error_code,
                formula=cell.formula,
                number_format=cell.number_format,
                display=cell.display,
                style_id=cell.style_id,
                source=cell.source_address,
                merged_range=cell.merged_range,
                is_merge_anchor=cell.is_merge_anchor,
            )
            for cell in sorted(definition.cells, key=lambda c: (c.row_index, c.col_index))
        ],
        merged_ranges=definition.merged_ranges or [],
        styles={key: CellStyleOut.model_validate(value) for key, value in (definition.styles or {}).items()},
        warnings=definition.warnings or [],
        meta=definition.meta or {},
    )


def table_summary_out(definition: TableDefinition) -> TableSummaryOut:
    if definition.period_axis == "rows":
        periods = [row.period for row in definition.rows if row.period]
    else:
        periods = [column.period for column in definition.columns if column.period]
    return TableSummaryOut(
        id=definition.id,
        sheet_name=definition.sheet_name,
        source_range=definition.source_range,
        title=definition.title,
        department=definition.department,
        hierarchy=definition.hierarchy or [],
        shape=definition.shape,
        period_axis=definition.period_axis,
        row_count=len(definition.rows),
        col_count=len(definition.columns),
        periods=[PeriodOut.model_validate(period) for period in periods],
        warnings=definition.warnings or [],
    )


def version_out(version: PresentationVersion) -> "PresentationVersionOut":
    return PresentationVersionOut(
        id=version.id,
        presentation_id=version.presentation_id,
        number=version.number,
        label=version.label,
        status=version.status.value if hasattr(version.status, "value") else version.status,
        notes=version.notes,
        created_at=version.created_at,
        published_at=version.published_at,
        parent_version_id=version.parent_version_id,
        summary=version.summary or {},
        warnings=version.warnings or [],
        import_ids=[item.id for item in version.imports],
    )


def presentation_out(presentation: "Presentation") -> "PresentationOut":
    versions = sorted(presentation.versions, key=lambda v: v.number)
    latest = versions[-1] if versions else None
    return PresentationOut(
        id=presentation.id,
        department=presentation.department.value,
        name=presentation.name,
        period_label=presentation.period_label,
        status=presentation.status.value
        if hasattr(presentation.status, "value")
        else presentation.status,
        created_at=presentation.created_at,
        updated_at=presentation.updated_at,
        archived_at=presentation.archived_at,
        trashed_at=presentation.trashed_at,
        latest_version=version_out(latest) if latest else None,
        version_count=len(versions),
    )


def import_out(
    data: DepartmentData,
    *,
    reused: bool = False,
    version: "PresentationVersion | None" = None,
) -> ImportOut:
    raw = data.raw_file
    summary = data.summary or {}
    return ImportOut(
        id=data.id,
        reused=reused,
        presentation_id=version.presentation_id if version else None,
        version_id=version.id if version else None,
        version_number=version.number if version else None,
        table_names=list(summary.get("tableNames") or []),
        periods=list(summary.get("periodLabels") or []),
        department=data.department.value,
        parser_version=data.parser_version,
        parsed_at=data.parsed_at,
        summary=data.summary or {},
        warnings=data.warnings or [],
        raw_file=(
            RawFileOut(
                id=raw.id,
                original_filename=raw.original_filename,
                mime_type=raw.mime_type,
                size_bytes=raw.size_bytes,
                sha256=raw.sha256,
                created_at=raw.created_at,
            )
            if raw
            else None
        ),
        tables=[table_summary_out(table) for table in sorted(data.tables, key=lambda t: t.order_index)],
    )
