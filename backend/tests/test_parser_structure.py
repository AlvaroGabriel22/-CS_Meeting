"""End-to-end parsing of the raw-data fixtures."""

from __future__ import annotations

from pathlib import Path

from app.excel.model import CellRole, PeriodAxis, TableShape, ValueType
from app.excel import parse_file


def _table(path: Path, index: int = 0):
    tables = parse_file(path).tables
    assert tables, f"no table detected in {path.name}"
    return tables[index]


# --------------------------------------------------------------------------- #
# Matrix table (IQC / OQC weekly)
# --------------------------------------------------------------------------- #
def test_matrix_structure_is_inferred(fixture_files: dict[str, Path]) -> None:
    table = _table(fixture_files["iqc_w32.xlsx"])
    assert table.shape is TableShape.MATRIX
    assert table.period_axis is PeriodAxis.COLUMNS
    assert table.title and "IQC" in table.title
    assert table.header_row_count == 1
    assert table.label_col_count == 2  # Section + Metric


def test_periods_are_discovered_in_source_order(fixture_files: dict[str, Path]) -> None:
    table = _table(fixture_files["iqc_w32.xlsx"])
    labels = [period.label for period in table.periods]
    assert labels == ["2025", "2026", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "W30", "W31", "W32"]
    kinds = {period.label: period.kind.value for period in table.periods}
    assert kinds["2026"] == "year" and kinds["Aug"] == "month" and kinds["W32"] == "week"


def test_merged_section_labels_are_carried_to_every_row(fixture_files: dict[str, Path]) -> None:
    table = _table(fixture_files["iqc_w32.xlsx"])
    data_rows = [row for row in table.rows if not row.is_header_row]
    # "SEC" is written once and merged over its four metric rows
    assert [row.label_path for row in data_rows[:4]] == [
        ("SEC", "Inspected Qty"),
        ("SEC", "Defect Qty"),
        ("SEC", "PPM"),
        ("SEC", "Target PPM"),
    ]
    assert {row.label_path[0] for row in data_rows} == {"SEC", "TNP", "TECPLAM"}


def test_merged_ranges_and_source_coordinates_are_kept_as_provenance(
    fixture_files: dict[str, Path],
) -> None:
    table = _table(fixture_files["iqc_w32.xlsx"])
    assert table.source_range.startswith("B1:")
    assert any(":" in rng for rng in table.merged_ranges)
    merged_cells = [cell for cell in table.cells if cell.merged_range]
    assert merged_cells and all(cell.source_address for cell in merged_cells)
    anchors = [cell for cell in merged_cells if cell.is_merge_anchor]
    assert anchors, "a merged range must expose its anchor"


def test_na_and_division_errors_survive_the_import(fixture_files: dict[str, Path]) -> None:
    table = _table(fixture_files["iqc_w32.xlsx"])
    values = [cell for cell in table.cells if cell.role is CellRole.VALUE]
    errors = [cell for cell in values if cell.value_type is ValueType.ERROR]
    nas = [cell for cell in values if cell.value_type is ValueType.NA]
    assert errors and all(cell.error_code == "#DIV/0!" and cell.number is None for cell in errors)
    assert nas and all(cell.number is None for cell in nas)


def test_number_format_reaches_the_display_hint(fixture_files: dict[str, Path]) -> None:
    table = _table(fixture_files["iqc_w32.xlsx"])
    numbers = [
        cell
        for cell in table.cells
        if cell.role is CellRole.VALUE and cell.value_type is ValueType.NUMBER
    ]
    assert numbers
    assert all(cell.display.thousands for cell in numbers)
    assert {cell.display.kind for cell in numbers} <= {"integer", "decimal"}


# --------------------------------------------------------------------------- #
# Nested / merged header (OQC TECPLAM)
# --------------------------------------------------------------------------- #
def test_nested_header_yields_period_plus_series(fixture_files: dict[str, Path]) -> None:
    table = _table(fixture_files["oqc_tecplam.xlsx"])
    assert table.header_row_count == 3
    data_columns = [column for column in table.columns if not column.is_label_column]
    assert [column.series for column in data_columns] == [
        "Target",
        "Result",
        "Target",
        "Result",
        "Target",
        "Result",
    ]
    # the merged "2026" cell is inherited by every month underneath it
    assert {column.period.year for column in data_columns} == {2026}
    assert [column.period.month for column in data_columns] == [6, 6, 7, 7, 8, 8]


# --------------------------------------------------------------------------- #
# Two tables in one sheet (FIELD: ASR + CASR)
# --------------------------------------------------------------------------- #
def test_side_by_side_tables_are_split(fixture_files: dict[str, Path]) -> None:
    tables = parse_file(fixture_files["field_asr_casr.xlsx"]).tables
    assert len(tables) == 2
    corners = [table.meta.get("cornerLabel") for table in tables]
    assert corners == ["ASR", "CASR"]
    assert all(len(table.periods) == 3 for table in tables)
    assert tables[0].source_range != tables[1].source_range


def test_percentage_table_keeps_raw_fraction(fixture_files: dict[str, Path]) -> None:
    asr = parse_file(fixture_files["field_asr_casr.xlsx"]).tables[0]
    numbers = [
        cell for cell in asr.cells if cell.role is CellRole.VALUE and cell.value_type is ValueType.NUMBER
    ]
    assert numbers
    assert all(0 <= cell.number <= 1 for cell in numbers)  # stored value untouched
    assert all(cell.display.kind == "percent" for cell in numbers)


# --------------------------------------------------------------------------- #
# Transposed and flat shapes
# --------------------------------------------------------------------------- #
def test_transposed_table_puts_periods_on_rows(fixture_files: dict[str, Path]) -> None:
    table = _table(fixture_files["field_transposed.xlsx"])
    assert table.period_axis is PeriodAxis.ROWS
    assert [period.label for period in table.periods] == ["W30", "W31", "W32", "W33"]
    assert [column.label for column in table.columns][1:] == ["Sales", "Defects", "ASR", "CASR"]


def test_flat_long_format_is_recognised(fixture_files: dict[str, Path]) -> None:
    table = _table(fixture_files["flat_long.xlsx"])
    assert table.shape is TableShape.FLAT
    assert table.meta["flatPeriodColumns"] == {"year": 0, "month": 1}
