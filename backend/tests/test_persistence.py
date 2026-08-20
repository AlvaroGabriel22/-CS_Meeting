"""Parse -> persist -> serialize must not lose anything."""

from __future__ import annotations

from pathlib import Path

from app.db.models import Department, DepartmentData, RawDataFile
from app.excel import parse_file
from app.services.import_service import persist_parsed_workbook
from app.services.serializers import import_out, table_out


def test_round_trip_keeps_structure_and_values(session, fixture_files: dict[str, Path]) -> None:
    path = fixture_files["iqc_w32.xlsx"]
    parsed = parse_file(path)
    source = parsed.tables[0]

    raw = RawDataFile(
        department=Department.IQC,
        original_filename=path.name,
        stored_path=f"raw/IQC/{path.name}",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=path.stat().st_size,
        sha256="0" * 64,
    )
    session.add(raw)
    session.flush()

    data = persist_parsed_workbook(session, department=Department.IQC, raw_file=raw, parsed=parsed)
    session.flush()

    stored = session.get(DepartmentData, data.id)
    definition = stored.tables[0]
    restored = table_out(definition)

    assert restored.header_row_count == source.header_row_count
    assert restored.label_col_count == source.label_col_count
    assert len(restored.columns) == len(source.columns)
    assert len(restored.rows) == len(source.rows)
    assert len(restored.cells) == len(source.cells)
    assert restored.merged_ranges == source.merged_ranges
    assert restored.styles.keys() == source.styles.keys()

    stored_periods = [column.period.label for column in restored.columns if column.period]
    assert stored_periods == [period.label for period in source.periods]

    stored_errors = {cell.source for cell in restored.cells if cell.error_code}
    source_errors = {cell.source_address for cell in source.cells if cell.error_code}
    assert stored_errors == source_errors and stored_errors


def test_import_summary_lists_periods(session, fixture_files: dict[str, Path]) -> None:
    parsed = parse_file(fixture_files["iqc_w33.xlsx"])
    raw = RawDataFile(
        department=Department.IQC,
        original_filename="iqc_w33.xlsx",
        stored_path="raw/IQC/iqc_w33.xlsx",
        mime_type="application/octet-stream",
        size_bytes=1,
        sha256="1" * 64,
    )
    session.add(raw)
    session.flush()
    data = persist_parsed_workbook(session, department=Department.IQC, raw_file=raw, parsed=parsed)
    session.flush()

    payload = import_out(data)
    assert payload.summary["tableCount"] == 1
    assert {"W31", "W32", "W33", "Sep"} <= set(payload.summary["periodLabels"])
    assert payload.tables[0].row_count > 0


def test_reimport_creates_a_new_immutable_dataset(session, fixture_files: dict[str, Path]) -> None:
    parsed = parse_file(fixture_files["iqc_w32.xlsx"])
    raw = RawDataFile(
        department=Department.IQC,
        original_filename="iqc_w32.xlsx",
        stored_path="raw/IQC/iqc_w32.xlsx",
        mime_type="application/octet-stream",
        size_bytes=1,
        sha256="2" * 64,
    )
    session.add(raw)
    session.flush()
    first = persist_parsed_workbook(session, department=Department.IQC, raw_file=raw, parsed=parsed)
    second = persist_parsed_workbook(session, department=Department.IQC, raw_file=raw, parsed=parsed)
    session.flush()
    assert first.id != second.id
    assert first.tables[0].id != second.tables[0].id
