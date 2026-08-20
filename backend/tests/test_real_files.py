"""Validation against the real department workbooks.

These tests are skipped until the confidential files are placed in
``tests/fixtures/real/`` (see the README there).  They are deliberately loose:
their job is to prove the heuristics survive contact with the real layout, not
to pin values that change every week.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.excel import parse_file
from app.excel.model import PeriodAxis, TableShape

REAL_DIR = Path(__file__).parent / "fixtures" / "real"
REAL_FILES = sorted(REAL_DIR.glob("*.xls[xm]")) if REAL_DIR.exists() else []

pytestmark = pytest.mark.skipif(
    not REAL_FILES, reason="no real workbook in tests/fixtures/real/ (see its README)"
)


def _department_of(path: Path) -> str | None:
    name = path.name.upper()
    return next((code for code in ("IQC", "OQC", "FIELD") if code in name), None)


@pytest.mark.parametrize("path", REAL_FILES, ids=lambda p: p.name)
def test_real_file_produces_a_usable_model(path: Path) -> None:
    workbook = parse_file(path, _department_of(path))
    assert workbook.tables, f"no table detected in {path.name}"

    matrices = [table for table in workbook.tables if table.shape is TableShape.MATRIX]
    assert matrices, "the weekly report should contain at least one matrix table"

    for table in matrices:
        assert table.cells
        assert table.source_range  # provenance recorded
        if table.period_axis is not PeriodAxis.NONE:
            assert table.periods, f"{table.source_range}: periods must be discovered"


@pytest.mark.parametrize("path", REAL_FILES, ids=lambda p: p.name)
def test_real_file_values_are_never_silently_zeroed(path: Path) -> None:
    for table in parse_file(path, _department_of(path)).tables:
        for cell in table.cells:
            if cell.error_code or cell.value_type.value == "na":
                assert cell.number is None
            if cell.value_type.value == "number":
                assert cell.number is not None and cell.raw_value is not None
