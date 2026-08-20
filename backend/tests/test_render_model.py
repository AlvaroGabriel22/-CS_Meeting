"""Sprint 2 — the render model must be structurally faithful to the workbook.

Everything here is checked against the real IQC file and against the evolution
fixtures: the same builder, five different period axes, no hardcoded month,
quarter or week anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.excel import parse_file
from app.services.interpretation import from_normalized
from app.services.render_model import build_table_view


def _views(path: Path, department: str = "IQC") -> list[dict]:
    return [
        build_table_view(from_normalized(table, department))
        for table in parse_file(path, department).tables
    ]


def _view(path: Path, index: int = 0) -> dict:
    return _views(path)[index]


def _cell(view: dict, row: int, col: int) -> dict | None:
    for entry in view["rows"]:
        if entry["index"] != row:
            continue
        return next((cell for cell in entry["cells"] if cell["col"] == col), None)
    return None


def _texts(view: dict, col: int) -> list[str]:
    return [
        cell["text"]
        for row in view["rows"]
        for cell in row["cells"]
        if cell["col"] == col and cell["kind"] != "period"
    ]


# --------------------------------------------------------------------------- #
# 1-3. The three tables
# --------------------------------------------------------------------------- #
def test_01_02_03_the_three_tables_are_rendered(iqc_real: Path) -> None:
    views = _views(iqc_real)
    assert [view["title"] for view in views] == ["TTL", "SEC", "TNP"]
    assert [view["sourceRange"] for view in views] == ["B2:I17", "K2:R17", "T2:AA17"]
    for view in views:
        assert view["department"] == "IQC"
        assert view["columnCount"] == 8 and view["rowCount"] == 16
        assert view["labelColumnCount"] == 2 and view["headerRowCount"] == 1
        assert view["rows"] and all(row["cells"] for row in view["rows"])


# --------------------------------------------------------------------------- #
# 4-7. Hierarchy
# --------------------------------------------------------------------------- #
def test_04_hierarchy_is_preserved_with_indentation(iqc_real: Path) -> None:
    view = _view(iqc_real)
    assert view["hierarchy"] == ["category", "subcategory", "metric"]

    data_rows = [row for row in view["rows"] if row["kind"] == "data"]
    assert [row["depth"] for row in data_rows[:9]] == [0, 1, 1, 0, 1, 1, 1, 2, 2]
    #     Total   Rej Insp  Imported Rej Insp  SKD  Rej Insp
    assert [row["isHeadline"] for row in data_rows[:9]] == [
        True, False, False, True, False, False, True, False, False
    ]


@pytest.mark.parametrize("group", ["SKD", "CKD", "Local", "Imported"])
def test_05_06_07_groups_are_rendered(iqc_real: Path, group: str) -> None:
    view = _view(iqc_real)
    labels = {cell["text"] for row in view["rows"] for cell in row["cells"]}
    assert group in labels

    rows = [
        row
        for row in view["rows"]
        if group in (row["category"], row["subcategory"])
    ]
    assert rows, f"{group} must own rows in the model"
    headline = next(row for row in rows if row["isHeadline"])
    # sub-groups sit one level deeper than the group that contains them
    expected_depth = 1 if group in ("SKD", "CKD") else 0
    assert headline["depth"] == expected_depth


def test_skd_and_ckd_belong_to_imported(iqc_real: Path) -> None:
    view = _view(iqc_real)
    for name in ("SKD", "CKD"):
        rows = [row for row in view["rows"] if row["subcategory"] == name]
        assert rows and all(row["category"] == "Imported" for row in rows)
        assert [row["depth"] for row in rows] == [1, 2, 2]


# --------------------------------------------------------------------------- #
# 8-10. Metrics and values
# --------------------------------------------------------------------------- #
def test_08_09_rej_lot_and_insp_lot_are_rendered(iqc_real: Path) -> None:
    view = _view(iqc_real)
    metric_labels = [text for text in _texts(view, 1) if text]
    assert metric_labels.count("Rej. Lot") == 5  # one per block
    assert metric_labels.count("Insp. Lot") == 5
    assert set(metric_labels) == {"Rej. Lot", "Insp. Lot", "SKD", "CKD"}


def test_10_values_are_preserved_and_formatted_not_recomputed(iqc_real: Path) -> None:
    view = _view(iqc_real)
    # first block: PPM 6629 / Rej. Lot 139 / Insp. Lot 20970 in the '25 column
    assert _cell(view, 1, 2)["text"] == "6,629"
    assert _cell(view, 2, 2)["text"] == "139"
    assert _cell(view, 3, 2)["text"] == "20,970"
    assert _cell(view, 3, 2)["value"] == 20970.0
    # alignment comes from the workbook, not from a rule of ours
    assert _cell(view, 3, 2)["align"] == "center"
    assert _cell(view, 3, 2)["source"] == "D5"  # traceable to the workbook


# --------------------------------------------------------------------------- #
# The PPM rule: the value is the metric, the word is not drawn
# --------------------------------------------------------------------------- #
def test_no_artificial_ppm_label_is_rendered(iqc_real: Path) -> None:
    for view in _views(iqc_real):
        drawn = {cell["text"].strip().upper() for row in view["rows"] for cell in row["cells"]}
        assert "PPM" not in drawn
        inferred = {
            (cell["inferredText"] or "").upper()
            for row in view["rows"]
            for cell in row["cells"]
        }
        assert "PPM" not in inferred
        # it stays available as metadata
        assert view["meta"]["headlineMetric"] == "PPM"
        assert view["meta"]["headlineConfirmed"] is True


def test_headline_rows_keep_their_metric_cell_empty(iqc_real: Path) -> None:
    view = _view(iqc_real)
    for row in view["rows"]:
        if row["kind"] != "data" or not row["isHeadline"] or row["subcategory"]:
            continue
        metric_cell = next((cell for cell in row["cells"] if cell["col"] == 1), None)
        assert metric_cell is not None
        assert metric_cell["kind"] == "empty" and metric_cell["text"] == ""
        # the workbook draws only the vertical rules there — no horizontal line
        # closes the cell, and the renderer must not add one
        assert set(metric_cell["borders"]) == {"left", "right"}


def test_the_unnamed_first_block_is_offered_as_inferred_not_as_content(
    iqc_real: Path,
) -> None:
    view = _view(iqc_real)
    first = next(row for row in view["rows"] if row["kind"] == "data")
    label = next(cell for cell in first["cells"] if cell["col"] == 0)
    assert label["text"] == ""  # the workbook says nothing there
    assert label["inferredText"] == "Total"  # the parser's reading, kept apart
    assert "category" in first["inferred"]


# --------------------------------------------------------------------------- #
# Merged cells
# --------------------------------------------------------------------------- #
def test_merges_become_spans_and_covered_cells_are_not_drawn(iqc_real: Path) -> None:
    view = _view(iqc_real)

    corner = _cell(view, 0, 0)
    assert corner["text"] == "TTL" and corner["colSpan"] == 2 and corner["kind"] == "corner"
    assert _cell(view, 0, 1) is None  # covered by the corner merge

    imported = _cell(view, 4, 0)
    assert imported["text"] == "Imported" and imported["rowSpan"] == 9
    assert all(_cell(view, row, 0) is None for row in range(5, 13))

    local = _cell(view, 13, 0)
    assert local["text"] == "Local" and local["rowSpan"] == 3
    assert _cell(view, 14, 0) is None and _cell(view, 15, 0) is None


def test_the_grid_has_no_duplicate_or_missing_positions(iqc_real: Path) -> None:
    for view in _views(iqc_real):
        drawn: set[tuple[int, int]] = set()
        for row in view["rows"]:
            for cell in row["cells"]:
                for r in range(cell["row"], cell["row"] + cell["rowSpan"]):
                    for c in range(cell["col"], cell["col"] + cell["colSpan"]):
                        assert (r, c) not in drawn, f"{(r, c)} drawn twice"
                        drawn.add((r, c))
        expected = {
            (r, c) for r in range(view["rowCount"]) for c in range(view["columnCount"])
        }
        assert drawn == expected  # every coordinate covered exactly once


# --------------------------------------------------------------------------- #
# 11-20. Periods — dynamic, never hardcoded
# --------------------------------------------------------------------------- #
def test_11_to_15_quarters_and_month_of_the_real_file(iqc_real: Path) -> None:
    view = _view(iqc_real)
    header = [cell for row in view["rows"] if row["kind"] == "header" for cell in row["cells"]]
    period_cells = [cell for cell in header if cell["kind"] == "period"]

    assert [cell["text"] for cell in period_cells] == ["'25", "'26", "1Q", "2Q", "3Q", "Aug"]
    assert [period["label"] for period in view["periods"]] == [
        "'25", "'26", "1Q", "2Q", "3Q", "Aug",
    ]
    quarters = [period for period in view["periods"] if period["kind"] == "quarter"]
    assert [period["quarter"] for period in quarters] == ["1Q", "2Q", "3Q"]
    august = next(period for period in view["periods"] if period["label"] == "Aug")
    assert august["quarter"] == "3Q" and august["year"] == 2026


@pytest.mark.parametrize(
    "key,expected",
    [
        ("a", ["'25", "'26", "1Q", "2Q", "3Q", "Aug"]),
        ("b", ["'25", "'26", "1Q", "2Q", "3Q", "Aug", "Sep"]),
        ("c", ["'25", "'26", "1Q", "2Q", "3Q", "4Q", "Aug", "Sep", "Oct"]),
        ("d", ["'25", "'26", "1Q", "2Q", "3Q", "4Q", "Nov", "Dec"]),
        ("e", ["'25", "'26", "1Q", "2Q", "3Q", "4Q", "Nov", "Dec", "W48"]),
    ],
)
def test_16_to_20_the_same_renderer_draws_every_generation(
    iqc_evolution, key: str, expected: list[str]
) -> None:
    view = _view(iqc_evolution[key])
    header_texts = [
        cell["text"]
        for row in view["rows"]
        if row["kind"] == "header"
        for cell in row["cells"]
        if cell["kind"] == "period"
    ]
    assert header_texts == expected
    assert view["columnCount"] == view["labelColumnCount"] + len(expected)
    # the structure is identical whatever the period axis holds
    assert view["hierarchy"] == ["category", "subcategory", "metric"]
    assert view["title"] == "TTL"
    assert len([row for row in view["rows"] if row["kind"] == "data"]) == 15


def test_20_weeks_are_rendered_as_their_own_kind(iqc_evolution) -> None:
    view = _view(iqc_evolution["e"])
    week = next(period for period in view["periods"] if period["kind"] == "week")
    assert week["label"] == "W48" and week["week"] == 48
    assert week["quarter"] is None  # a week is not a month and not a quarter
    assert week["sortKey"] == "2026-W48"
    column = next(col for col in view["columns"] if col["period"] and col["period"]["week"] == 48)
    assert column["kind"] == "period"


def test_periods_are_never_duplicated_in_the_header(iqc_evolution) -> None:
    for key in ("a", "b", "c", "d", "e"):
        view = _view(iqc_evolution[key])
        labels = [period["label"] for period in view["periods"]]
        assert len(labels) == len(set(labels))
        period_columns = [column for column in view["columns"] if column["kind"] == "period"]
        assert len(period_columns) == len(labels)


def test_period_columns_carry_the_engine_ordering(iqc_evolution) -> None:
    """The renderer keeps file order, and every column knows its sortKey."""
    from app.excel.model import Period, PeriodKind
    from app.excel import period_engine as PE

    view = _view(iqc_evolution["d"])
    keys = [period["sortKey"] for period in view["periods"]]
    assert keys == ["2025-Y", "2026-Y", "2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4",
                    "2026-M11", "2026-M12"]

    # the renderer keeps the file's order; the engine can still order by meaning
    periods = [
        Period(
            kind=PeriodKind(period["kind"]),
            label=period["label"],
            year=period["year"],
            quarter=period["quarter"],
            month=period["month"],
            week=period["week"],
        )
        for period in view["periods"]
    ]
    assert [period.label for period in PE.in_order(periods)] == [
        "'25", "'26", "1Q", "2Q", "3Q", "4Q", "Nov", "Dec",
    ]


# --------------------------------------------------------------------------- #
# Styles and borders come from the workbook
# --------------------------------------------------------------------------- #
def test_style_metadata_travels_to_the_renderer(iqc_real: Path) -> None:
    view = _view(iqc_real)
    corner = _cell(view, 0, 0)
    assert corner["bold"] is True
    period_cell = _cell(view, 0, 2)
    assert period_cell["bold"] is True and period_cell["align"] == "center"

    # the workbook centres its numbers and boxes them: both survive untouched
    value = _cell(view, 2, 2)
    assert value["align"] == "center"
    assert set(value["borders"]) == {"top", "right", "bottom", "left"}


def test_label_cells_are_left_aligned_and_indented_by_hierarchy(iqc_real: Path) -> None:
    view = _view(iqc_real)
    skd = next(
        cell
        for row in view["rows"]
        for cell in row["cells"]
        if cell["text"] == "SKD"
    )
    assert skd["align"] == "left"
    metric_under_skd = _cell(view, 8, 1)
    assert metric_under_skd["text"] == "Rej. Lot"
    assert metric_under_skd["indent"] > skd["indent"]
