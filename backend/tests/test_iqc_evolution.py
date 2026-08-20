"""The period axis moves; the code does not.

Fixtures A→E are the same IQC report as months pass (see
``tests/fixtures/build_iqc_fixtures.py``).  One call, five files, five valid
models — this is the real acceptance criterion of Sprint 1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.excel import parse_file
from app.excel import period_engine as PE

EXPECTED_PERIODS = {
    "a": ["'25", "'26", "1Q", "2Q", "3Q", "Aug"],
    "b": ["'25", "'26", "1Q", "2Q", "3Q", "Aug", "Sep"],
    "c": ["'25", "'26", "1Q", "2Q", "3Q", "Aug", "Sep", "Oct"],
    "d": ["'25", "'26", "1Q", "2Q", "3Q", "4Q", "Nov", "Dec"],
    "e": ["'25", "'26", "1Q", "2Q", "3Q", "4Q", "Nov", "Dec", "W48"],
}


def _table(iqc_evolution: dict[str, Path], key: str, index: int = 0):
    return parse_file(iqc_evolution[key], "IQC").tables[index]


@pytest.mark.parametrize("key", sorted(EXPECTED_PERIODS))
def test_every_generation_is_read_by_the_same_code(iqc_evolution, key: str) -> None:
    workbook = parse_file(iqc_evolution[key], "IQC")
    assert [table.title for table in workbook.tables] == ["TTL", "SEC", "TNP"]
    for table in workbook.tables:
        assert table.hierarchy == ("category", "subcategory", "metric")
        assert table.meta["blocks"] == 5
        assert table.meta["metricCycle"] == ["Rej. Lot", "Insp. Lot"]
        assert table.meta["subgroups"] == ["SKD", "CKD"]
        assert table.meta["headlineCheck"]["consistent"]  # PPM still adds up


@pytest.mark.parametrize("key,expected", sorted(EXPECTED_PERIODS.items()))
def test_18_new_period_columns_are_picked_up(iqc_evolution, key: str, expected: list[str]) -> None:
    table = _table(iqc_evolution, key)
    assert [period.label for period in table.periods] == expected
    assert table.col_count == 2 + len(expected)  # two label columns + the periods


def test_19_a_closed_quarter_is_understood(iqc_evolution) -> None:
    """Fixture D replaced the running months with 4Q, Nov and Dec."""
    before = _table(iqc_evolution, "c")
    after = _table(iqc_evolution, "d")

    quarters_before = [p.quarter for p in before.periods if p.kind.value == "quarter"]
    quarters_after = [p.quarter for p in after.periods if p.kind.value == "quarter"]
    assert quarters_before == ["1Q", "2Q", "3Q"]
    assert quarters_after == ["1Q", "2Q", "3Q", "4Q"]

    by_label = {period.label: period for period in after.periods}
    assert by_label["Nov"].quarter == "4Q" and by_label["Dec"].quarter == "4Q"
    # 4Q covers Oct/Nov/Dec, so it contains both new months
    assert by_label["4Q"].months == (10, 11, 12)
    assert by_label["4Q"].contains(by_label["Nov"])
    assert by_label["4Q"].contains(by_label["Dec"])


def test_20_new_months_keep_their_quarter_and_year(iqc_evolution) -> None:
    table = _table(iqc_evolution, "c")
    months = {p.label: p for p in table.periods if p.kind.value == "month"}
    assert {"Aug": "3Q", "Sep": "3Q", "Oct": "4Q"} == {
        label: p.quarter for label, p in months.items()
    }
    assert all(period.year == 2026 for period in months.values())
    assert all(period.year_source == "inferred" for period in months.values())


def test_weeks_are_accepted_wherever_they_appear(iqc_evolution) -> None:
    table = _table(iqc_evolution, "e")
    week = next(period for period in table.periods if period.kind.value == "week")
    assert week.label == "W48" and week.week == 48
    assert week.year == 2026 and week.sort_key == "2026-W48"


def test_periods_are_ordered_by_meaning_not_by_column(iqc_evolution) -> None:
    table = _table(iqc_evolution, "e")
    ordered = [period.label for period in PE.in_order(table.periods)]
    assert ordered[0] == "'25"  # 2025 first, whatever its column
    assert ordered[1:] == ["'26", "1Q", "2Q", "3Q", "4Q", "Nov", "Dec", "W48"]


def test_the_same_period_keeps_its_identity_across_generations(iqc_evolution) -> None:
    """A chart bound to "3Q" or "Aug" keeps matching after the file changes."""
    keys = {
        key: {period.label: period.sort_key for period in _table(iqc_evolution, key).periods}
        for key in ("a", "b", "c")
    }
    shared = set(keys["a"]) & set(keys["b"]) & set(keys["c"])
    assert {"'25", "'26", "1Q", "2Q", "3Q", "Aug"} <= shared
    for label in shared:
        assert keys["a"][label] == keys["b"][label] == keys["c"][label]


def test_structure_survives_a_full_year_of_changes(iqc_evolution) -> None:
    """A→E: rows, hierarchy and labels are identical; only periods differ."""
    tables = {key: _table(iqc_evolution, key) for key in EXPECTED_PERIODS}
    signatures = {
        key: [(row.category, row.subcategory, row.metric) for row in table.rows if not row.is_header_row]
        for key, table in tables.items()
    }
    reference = signatures["a"]
    assert all(signature == reference for signature in signatures.values())
    assert reference[0] == ("Total", None, "PPM")
    assert reference[6] == ("Imported", "SKD", "PPM")


def test_the_synthetic_fixtures_match_the_real_file_structure(iqc_evolution, iqc_real) -> None:
    """Fixture A must be structurally indistinguishable from the real workbook."""
    real = parse_file(iqc_real, "IQC").tables[0]
    synthetic = _table(iqc_evolution, "a")

    assert synthetic.title == real.title
    assert synthetic.hierarchy == real.hierarchy
    assert synthetic.header_row_count == real.header_row_count
    assert synthetic.label_col_count == real.label_col_count
    assert synthetic.meta["blocks"] == real.meta["blocks"]
    assert synthetic.meta["metricCycle"] == real.meta["metricCycle"]
    assert synthetic.meta["subgroups"] == real.meta["subgroups"]
    assert [period.label for period in synthetic.periods] == [
        period.label for period in real.periods
    ]
    assert [
        (row.category, row.subcategory, row.metric)
        for row in synthetic.rows
        if not row.is_header_row
    ] == [
        (row.category, row.subcategory, row.metric) for row in real.rows if not row.is_header_row
    ]
