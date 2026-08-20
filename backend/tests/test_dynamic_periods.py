"""The next week's file must work without touching a single line of code."""

from __future__ import annotations

from pathlib import Path

from app.excel import parse_file


def test_week_window_shifts_and_a_month_appears(fixture_files: dict[str, Path]) -> None:
    """``iqc_w33`` is the same report one week later.

    It gained ``Sep``, dropped ``W30``, gained ``W33`` and gained a ``Cost``
    metric row — the parser adapts to all of it.
    """
    week32 = parse_file(fixture_files["iqc_w32.xlsx"]).tables[0]
    week33 = parse_file(fixture_files["iqc_w33.xlsx"]).tables[0]

    weeks_before = [p.week for p in week32.periods if p.kind.value == "week"]
    weeks_after = [p.week for p in week33.periods if p.kind.value == "week"]
    assert weeks_before == [30, 31, 32]
    assert weeks_after == [31, 32, 33]

    months_before = [p.month for p in week32.periods if p.kind.value == "month"]
    months_after = [p.month for p in week33.periods if p.kind.value == "month"]
    assert months_after == months_before + [9]  # September showed up

    # the structural reading is identical even though the shape grew
    assert week33.header_row_count == week32.header_row_count
    assert week33.label_col_count == week32.label_col_count
    assert week33.col_count == week32.col_count + 1
    assert week33.row_count == week32.row_count + 3  # one extra metric per section


def test_new_metric_row_is_picked_up(fixture_files: dict[str, Path]) -> None:
    week33 = parse_file(fixture_files["iqc_w33.xlsx"]).tables[0]
    metrics = {row.label_path[1] for row in week33.rows if not row.is_header_row and len(row.label_path) > 1}
    assert "Cost" in metrics


def test_period_sort_keys_are_stable_across_weeks(fixture_files: dict[str, Path]) -> None:
    week32 = parse_file(fixture_files["iqc_w32.xlsx"]).tables[0]
    week33 = parse_file(fixture_files["iqc_w33.xlsx"]).tables[0]
    common = {p.label: p.sort_key for p in week32.periods} | {p.label: p.sort_key for p in week33.periods}
    assert common["W32"] == "0000-W32"
    assert common["Aug"] == "0000-M08"
    # a chart built on labels keeps matching after the shift
    shared = {p.label for p in week32.periods} & {p.label for p in week33.periods}
    assert {"W31", "W32", "Aug", "2026"} <= shared
