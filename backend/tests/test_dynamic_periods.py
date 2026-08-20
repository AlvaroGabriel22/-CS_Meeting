"""Next week's file must work without touching a single line of code.

Dataset A -> B -> C is the same report over three weeks: the week window moves,
then a new month and a new metric appear.
"""

from __future__ import annotations

from pathlib import Path

from app.excel import parse_file


def _table(fixture_files: dict[str, Path], dataset: str):
    return parse_file(fixture_files[f"iqc_dataset_{dataset}.xlsx"], "IQC").tables[0]


def test_week_window_moves(fixture_files: dict[str, Path]) -> None:
    a, b = _table(fixture_files, "a"), _table(fixture_files, "b")
    assert [p.label for p in a.periods if p.kind.value == "week"] == ["W31", "W32"]
    assert [p.label for p in b.periods if p.kind.value == "week"] == ["W33", "W34"]
    assert a.col_count == b.col_count and a.row_count == b.row_count


def test_a_new_month_appears(fixture_files: dict[str, Path]) -> None:
    b, c = _table(fixture_files, "b"), _table(fixture_files, "c")
    months_b = [p.month for p in b.periods if p.kind.value == "month"]
    months_c = [p.month for p in c.periods if p.kind.value == "month"]
    assert months_c == months_b + [9]  # September joined, nothing else moved
    assert c.header_row_count == b.header_row_count
    assert c.label_col_count == b.label_col_count
    assert c.hierarchy == b.hierarchy


def test_a_new_row_is_picked_up(fixture_files: dict[str, Path]) -> None:
    """Dataset C adds a Target row under every group."""
    b, c = _table(fixture_files, "b"), _table(fixture_files, "c")
    assert {row.metric for row in c.rows if row.metric} == {row.metric for row in b.rows if row.metric}
    assert {row.series_type for row in b.rows if row.series_type} == set()
    assert {row.series_type for row in c.rows if row.series_type} == {"Target"}
    assert c.row_count == b.row_count + 9  # one added row per section/group pair


def test_period_identity_is_stable_across_files(fixture_files: dict[str, Path]) -> None:
    """A chart bound to labels/sortKeys keeps matching after the shift."""
    b, c = _table(fixture_files, "b"), _table(fixture_files, "c")
    keys_b = {p.label: p.sort_key for p in b.periods}
    keys_c = {p.label: p.sort_key for p in c.periods}
    shared = set(keys_b) & set(keys_c)
    assert {"W33", "W34", "Aug", "2026"} <= shared
    assert all(keys_b[label] == keys_c[label] for label in shared)
    assert keys_c["W34"] == "0000-W34" and keys_c["Sep"] == "0000-M09"


def test_no_dataset_needs_a_code_path_of_its_own(fixture_files: dict[str, Path]) -> None:
    """Same call, three files, three valid models."""
    for dataset in ("a", "b", "c"):
        table = _table(fixture_files, dataset)
        assert table.shape.value == "matrix"
        assert table.period_axis.value == "columns"
        assert table.hierarchy == ("category", "subcategory", "metric")
        assert table.periods and table.cells and not table.warnings
