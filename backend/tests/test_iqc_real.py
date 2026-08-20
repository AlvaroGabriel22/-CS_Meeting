"""Sprint 1 acceptance — the real IQC workbook.

Reference file: ``tests/fixtures/real/RawdataIQC.xlsx`` (three tables side by
side, merged categories, unlabelled PPM rows, SKD/CKD sub-groups).
"""

from __future__ import annotations

from pathlib import Path

from app.excel import parse_file
from app.excel.model import CellRole, SemanticType, TableShape, ValueType


def _tables(iqc_real: Path):
    return parse_file(iqc_real, "IQC").tables


# --------------------------------------------------------------------------- #
# 1-4. Table detection
# --------------------------------------------------------------------------- #
def test_01_detects_three_tables(iqc_real: Path) -> None:
    workbook = parse_file(iqc_real, "IQC")
    assert len(workbook.tables) == 3
    # the README sheet is prose, not raw data
    readme = next(sheet for sheet in workbook.sheets if sheet.name == "README")
    assert readme.tables == []
    assert any(w.startswith("skipped_non_tabular_region") for w in readme.warnings)


def test_02_03_04_detects_ttl_sec_and_tnp(iqc_real: Path) -> None:
    tables = _tables(iqc_real)
    assert [table.title for table in tables] == ["TTL", "SEC", "TNP"]
    # the ranges are *discovered*; they are recorded only as provenance
    assert [table.source_range for table in tables] == ["B2:I17", "K2:R17", "T2:AA17"]
    assert all(table.shape is TableShape.MATRIX for table in tables)


# --------------------------------------------------------------------------- #
# 5. Periods
# --------------------------------------------------------------------------- #
def test_05_detects_the_periods(iqc_real: Path) -> None:
    table = _tables(iqc_real)[0]
    assert [period.label for period in table.periods] == ["'25", "'26", "1Q", "2Q", "3Q", "Aug"]
    kinds = [period.kind.value for period in table.periods]
    assert kinds == ["year", "year", "quarter", "quarter", "quarter", "month"]

    by_label = {period.label: period for period in table.periods}
    assert by_label["'25"].year == 2025 and by_label["'26"].year == 2026
    # the quarters and the month inherit the reporting year, and Aug knows its quarter
    assert by_label["3Q"].year == 2026 and by_label["3Q"].quarter == "3Q"
    assert by_label["3Q"].months == (7, 8, 9)  # Jul/Aug/Sep
    assert by_label["Aug"].year == 2026 and by_label["Aug"].quarter == "3Q"
    assert by_label["Aug"].sort_key == "2026-M08"
    assert by_label["1Q"].quarter == "1Q" and by_label["1Q"].months == (1, 2, 3)
    # the label is canonical, never a bare number
    assert [p.quarter for p in table.periods if p.kind.value == "quarter"] == ["1Q", "2Q", "3Q"]
    assert table.meta["reportingYear"] == 2026


# --------------------------------------------------------------------------- #
# 6. PPM without the word "PPM"
# --------------------------------------------------------------------------- #
def test_06_ppm_is_identified_without_the_word(iqc_real: Path) -> None:
    table = _tables(iqc_real)[0]
    # the workbook never writes it
    assert not any(
        (cell.raw_value or "").strip().upper() == "PPM" for cell in table.cells
    ), "the fixture must not contain the word PPM"

    ppm_rows = [row for row in table.rows if row.metric == "PPM"]
    assert len(ppm_rows) == 5  # one per block
    assert all("metric" in row.inferred for row in ppm_rows)

    # and the inference is confirmed arithmetically: Rej. Lot / Insp. Lot × 1e6
    check = table.meta["headlineCheck"]
    assert check["consistent"] and check["checked"] == 30 and check["matched"] == 30
    assert table.meta["headlineMetricConfirmed"] is True


# --------------------------------------------------------------------------- #
# 7-8. Hierarchy
# --------------------------------------------------------------------------- #
def test_07_detects_the_category_hierarchy(iqc_real: Path) -> None:
    table = _tables(iqc_real)[0]
    assert table.hierarchy == ("category", "subcategory", "metric")
    rows = [row for row in table.rows if not row.is_header_row]
    assert [row.category for row in rows[:3]] == ["Total", "Total", "Total"]
    assert {row.category for row in rows} == {"Total", "Imported", "Local"}
    # "Total" is not written anywhere: it is the unnamed leading block
    assert all("category" in row.inferred for row in rows if row.category == "Total")


def test_08_detects_skd_and_ckd_as_subgroups(iqc_real: Path) -> None:
    table = _tables(iqc_real)[0]
    rows = [row for row in table.rows if not row.is_header_row]
    assert {row.subcategory for row in rows} == {None, "SKD", "CKD"}
    skd = [row for row in rows if row.subcategory == "SKD"]
    assert [row.metric for row in skd] == ["PPM", "Rej. Lot", "Insp. Lot"]
    assert all(row.category == "Imported" for row in skd)  # they live under Imported
    assert table.meta["metricCycle"] == ["Rej. Lot", "Insp. Lot"]
    assert table.meta["subgroups"] == ["SKD", "CKD"]
    assert table.meta["blocks"] == 5


# --------------------------------------------------------------------------- #
# 9-10. Visual structure
# --------------------------------------------------------------------------- #
def test_09_preserves_merges(iqc_real: Path) -> None:
    table = _tables(iqc_real)[0]
    assert set(table.merged_ranges) == {"B2:C2", "B6:B14", "B15:B17"}
    anchors = [cell for cell in table.cells if cell.is_merge_anchor]
    assert {cell.raw_value for cell in anchors} == {"TTL", "Imported", "Local"}
    covered = [cell for cell in table.cells if cell.merged_range and not cell.is_merge_anchor]
    assert covered, "cells covered by a merge keep the range they belong to"


def test_10_preserves_structural_empty_cells(iqc_real: Path) -> None:
    table = _tables(iqc_real)[0]
    # the PPM rows have an empty label cell — that emptiness carries meaning
    ppm_rows = [row for row in table.rows if row.metric == "PPM" and not row.subcategory]
    for row in ppm_rows:
        label_cell = next(
            (cell for cell in table.cells if cell.row == row.index and cell.col == 1), None
        )
        assert label_cell is None or not (label_cell.raw_value or "").strip()
    # the layout is recoverable: sizes, widths and styles came along
    assert table.header_row_count == 1 and table.label_col_count == 2
    assert any(column.width for column in table.columns)
    assert table.styles


# --------------------------------------------------------------------------- #
# 11-13. Values
# --------------------------------------------------------------------------- #
def test_11_12_numbers_stay_numbers_and_get_a_display(iqc_real: Path) -> None:
    table = _tables(iqc_real)[0]
    values = [
        cell
        for cell in table.cells
        if cell.role is CellRole.VALUE and cell.value_type is ValueType.NUMBER
    ]
    assert len(values) == 90  # 15 rows × 6 periods
    assert all(isinstance(cell.number, float) for cell in values)

    big = next(cell for cell in values if cell.number and cell.number >= 10_000)
    assert "," in big.display_value  # thousands separator is presentation only
    assert float(big.raw_value) == big.number  # the stored value is untouched


def test_13_na_and_errors_keep_their_meaning(iqc_real: Path) -> None:
    table = _tables(iqc_real)[0]
    for cell in table.cells:
        if cell.value_type in (ValueType.NA, ValueType.ERROR):
            assert cell.number is None
            assert cell.raw_value  # the original spelling survives


# --------------------------------------------------------------------------- #
# 14. Warnings
# --------------------------------------------------------------------------- #
def test_14_reports_what_it_had_to_infer(iqc_real: Path) -> None:
    table = _tables(iqc_real)[0]
    assert set(table.warnings) == {"headline_metric_inferred", "implicit_group_label"}
    # inference is visible per row, not buried in a log
    inferred = {field for row in table.rows for field in row.inferred}
    assert inferred == {"category", "metric"}


def test_semantics_are_attached_to_the_cells(iqc_real: Path) -> None:
    table = _tables(iqc_real)[0]
    semantics = {cell.semantic for cell in table.cells}
    assert {SemanticType.PERIOD, SemanticType.CATEGORY, SemanticType.VALUE} <= semantics
    skd_cell = next(cell for cell in table.cells if cell.raw_value == "SKD")
    assert skd_cell.semantic is SemanticType.SUBCATEGORY  # not a metric
