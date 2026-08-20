"""Raw data import: upload -> parse -> persist.

This is the only place that writes parsed facts.  An import is immutable: a new
upload creates a new :class:`DepartmentData`, so a version that already points
at an older import keeps showing exactly what it showed before.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.errors import ParseError
from app.db.models import (
    Department,
    DepartmentData,
    RawDataFile,
    TableCell,
    TableColumn,
    TableDefinition,
    TableRow,
)
from app.excel.model import ParsedWorkbook
from app.excel import parse_file
from app.services import storage

logger = logging.getLogger(__name__)


def import_raw_data(
    session: Session,
    *,
    department: Department,
    filename: str,
    content_type: str | None,
    payload: bytes,
) -> DepartmentData:
    """Validate, store, parse and persist one raw-data workbook."""
    suffix = storage.validate_raw_upload(filename, content_type, payload)
    path, digest = storage.store_raw_file(payload, suffix, department.value)

    try:
        parsed = parse_file(path)
    except Exception as exc:  # openpyxl raises a zoo of exceptions
        logger.exception("failed to parse %s", filename)
        raise ParseError("Could not read this workbook", {"reason": str(exc)}) from exc

    raw_file = RawDataFile(
        department=department,
        original_filename=Path(filename).name,
        stored_path=storage.relative_to_data(path),
        mime_type=content_type or "application/octet-stream",
        size_bytes=len(payload),
        sha256=digest,
    )
    session.add(raw_file)
    session.flush()

    data = persist_parsed_workbook(session, department=department, raw_file=raw_file, parsed=parsed)
    logger.info(
        "imported %s for %s: %d table(s)", raw_file.original_filename, department.value, len(data.tables)
    )
    return data


def parse_bytes(payload: bytes, suffix: str = ".xlsx") -> ParsedWorkbook:
    """Parse an in-memory workbook (used by tests and by re-parse tooling)."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as handle:
        handle.write(payload)
        handle.flush()
        return parse_file(handle.name)


def persist_parsed_workbook(
    session: Session,
    *,
    department: Department,
    raw_file: RawDataFile,
    parsed: ParsedWorkbook,
) -> DepartmentData:
    data = DepartmentData(
        department=department,
        raw_data_file_id=raw_file.id,
        parser_version=parsed.parser_version,
        summary=_summary(parsed),
        warnings=list(parsed.warnings),
    )
    session.add(data)
    session.flush()

    for order, table in enumerate(parsed.tables):
        definition = TableDefinition(
            department_data_id=data.id,
            order_index=order,
            sheet_name=table.sheet_name,
            source_range=table.source_range,
            title=table.title,
            department=table.department,
            hierarchy=list(table.hierarchy),
            shape=table.shape.value,
            period_axis=table.period_axis.value,
            header_row_count=table.header_row_count,
            label_col_count=table.label_col_count,
            merged_ranges=list(table.merged_ranges),
            styles={key: style.to_dict() for key, style in table.styles.items()},
            warnings=list(table.warnings),
            meta=dict(table.meta),
        )
        session.add(definition)
        session.flush()

        session.add_all(
            TableColumn(
                table_definition_id=definition.id,
                index=column.index,
                source_column=column.source_column,
                header_path=list(column.header_path),
                label=column.label,
                period=column.period.to_dict() if column.period else None,
                series=column.series,
                semantic=column.semantic.value,
                is_label_column=column.is_label_column,
                width=column.width,
            )
            for column in table.columns
        )
        session.add_all(
            TableRow(
                table_definition_id=definition.id,
                index=row.index,
                source_row=row.source_row,
                label_path=list(row.label_path),
                label=row.label,
                level=row.level,
                category=row.category,
                subcategory=row.subcategory,
                metric=row.metric,
                semantic=row.semantic.value,
                is_header_row=row.is_header_row,
                period=row.period.to_dict() if row.period else None,
                height=row.height,
            )
            for row in table.rows
        )
        session.add_all(
            TableCell(
                table_definition_id=definition.id,
                row_index=cell.row,
                col_index=cell.col,
                role=cell.role.value,
                semantic=cell.semantic.value,
                value_type=cell.value_type.value,
                raw_value=cell.raw_value,
                number_value=cell.number,
                text_value=cell.text,
                display_value=cell.display_value,
                error_code=cell.error_code,
                formula=cell.formula,
                number_format=cell.number_format,
                display=cell.display.to_dict(),
                style_id=cell.style_id,
                source_address=cell.source_address,
                merged_range=cell.merged_range,
                is_merge_anchor=cell.is_merge_anchor,
            )
            for cell in table.cells
        )
    session.flush()
    return data


def _summary(parsed: ParsedWorkbook) -> dict:
    periods: list[str] = []
    for table in parsed.tables:
        periods.extend(period.label for period in table.periods)
    return {
        "filename": parsed.filename,
        "sheets": [sheet.name for sheet in parsed.sheets],
        "tableCount": len(parsed.tables),
        "periodLabels": sorted(set(periods)),
        "shapes": sorted({table.shape.value for table in parsed.tables}),
    }
