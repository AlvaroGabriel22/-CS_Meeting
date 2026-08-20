"""Shapes the parser must handle beyond the standard weekly matrix."""

from __future__ import annotations

from pathlib import Path

from app.excel import parse_file
from app.excel.model import CellRole, PeriodAxis, SemanticType, TableShape, ValueType


# --------------------------------------------------------------------------- #
# Nested / merged header (year > month > series)
# --------------------------------------------------------------------------- #
def test_nested_header_yields_period_plus_series(fixture_files: dict[str, Path]) -> None:
    table = parse_file(fixture_files["oqc_tecplam.xlsx"], "OQC").tables[0]
    assert table.header_row_count == 3
    data_columns = [column for column in table.columns if not column.is_label_column]
    assert [column.series_type for column in data_columns] == [
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
    assert all(column.semantic is SemanticType.PERIOD for column in data_columns)


def test_single_unknown_label_column_is_a_category(fixture_files: dict[str, Path]) -> None:
    table = parse_file(fixture_files["oqc_tecplam.xlsx"], "OQC").tables[0]
    assert table.hierarchy == ("category",)
    categories = [row.category for row in table.rows if not row.is_header_row]
    assert categories == ["TECPLAM 1", "TECPLAM 2", "TECPLAM 3"]


# --------------------------------------------------------------------------- #
# FIELD — ASR and CASR in one sheet
# --------------------------------------------------------------------------- #
def test_percentage_table_keeps_raw_fraction(fixture_files: dict[str, Path]) -> None:
    asr = parse_file(fixture_files["field_asr_casr.xlsx"], "FIELD").tables[0]
    numbers = [
        cell
        for cell in asr.cells
        if cell.role is CellRole.VALUE and cell.value_type is ValueType.NUMBER
    ]
    assert numbers
    assert all(0 <= cell.number <= 1 for cell in numbers)  # stored value untouched
    assert all(cell.display.kind == "percent" for cell in numbers)
    assert all(cell.display_value.endswith("%") for cell in numbers)


def test_ppm_table_keeps_integer_formatting(fixture_files: dict[str, Path]) -> None:
    casr = parse_file(fixture_files["field_asr_casr.xlsx"], "FIELD").tables[1]
    numbers = [
        cell
        for cell in casr.cells
        if cell.role is CellRole.VALUE and cell.value_type is ValueType.NUMBER
    ]
    assert numbers and all(cell.display.kind == "integer" for cell in numbers)


# --------------------------------------------------------------------------- #
# Transposed and flat shapes
# --------------------------------------------------------------------------- #
def test_transposed_table_puts_periods_on_rows(fixture_files: dict[str, Path]) -> None:
    table = parse_file(fixture_files["field_transposed.xlsx"], "FIELD").tables[0]
    assert table.period_axis is PeriodAxis.ROWS
    assert [period.label for period in table.periods] == ["W30", "W31", "W32", "W33"]
    assert [column.label for column in table.columns][1:] == ["Sales", "Defects", "ASR", "CASR"]
    # a row that *is* a period is not also a metric
    period_rows = [row for row in table.rows if row.period]
    assert period_rows and all(row.metric is None for row in period_rows)
    assert all(row.semantic is SemanticType.PERIOD for row in period_rows)


def test_flat_long_format_is_recognised(fixture_files: dict[str, Path]) -> None:
    table = parse_file(fixture_files["flat_long.xlsx"]).tables[0]
    assert table.shape is TableShape.FLAT
    assert table.period_axis is PeriodAxis.NONE
    assert table.meta["flatPeriodColumns"] == {"year": 0, "month": 1}


# --------------------------------------------------------------------------- #
# Semantic typing of cells
# --------------------------------------------------------------------------- #
def test_cells_carry_their_meaning(fixture_files: dict[str, Path]) -> None:
    table = parse_file(fixture_files["iqc_dataset_a.xlsx"], "IQC").tables[0]
    semantics = {cell.semantic for cell in table.cells}
    assert {
        SemanticType.TITLE,
        SemanticType.PERIOD,
        SemanticType.CATEGORY,
        SemanticType.SUBCATEGORY,
        SemanticType.METRIC,
        SemanticType.VALUE,
    } <= semantics

    # "W32" in the header is a period, not a value
    week_cell = next(
        cell
        for cell in table.cells
        if cell.role is CellRole.HEADER and cell.raw_value == "W32"
    )
    assert week_cell.semantic is SemanticType.PERIOD
    # "PPM" in the label column is a metric
    ppm_cell = next(
        cell for cell in table.cells if cell.role is CellRole.LABEL and cell.raw_value == "PPM"
    )
    assert ppm_cell.semantic is SemanticType.METRIC
