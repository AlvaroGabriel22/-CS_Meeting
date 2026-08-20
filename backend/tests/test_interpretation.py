"""Sprint 0 acceptance: the model proves it understood the file.

    RAW EXCEL -> PARSER -> INTERPRETER -> NORMALIZED MODEL

and the result is inspectable as meaning, not as coordinates.
"""

from __future__ import annotations

from pathlib import Path

from app.excel import parse_file
from app.services.interpretation import from_normalized, interpretation_view
from app.tools.inspect_raw import build_report, render


def _view(fixture_files: dict[str, Path], name: str, department: str, index: int = 0):
    table = parse_file(fixture_files[name], department).tables[index]
    return interpretation_view(from_normalized(table, department))


def test_acceptance_shape_of_the_semantic_view(fixture_files: dict[str, Path]) -> None:
    view = _view(fixture_files, "iqc_dataset_c.xlsx", "IQC")

    assert view["department"] == "IQC"
    assert view["hierarchy"] == ["category", "subcategory", "metric"]
    assert view["periods"][:2] == ["2025", "2026"]
    assert view["periods"][-2:] == ["W33", "W34"]
    assert "Sep" in view["periods"]

    first = view["rows"][0]
    assert first["category"] == "SEC"
    assert first["subcategory"] == "Total"
    assert first["metric"] == "PPM"
    assert [value["period"] for value in first["values"]] == view["periods"]

    # every value carries original *and* interpretation
    numeric = next(value for value in first["values"] if value["type"] == "number")
    assert numeric["raw"] is not None
    assert numeric["value"] == float(numeric["raw"])
    assert numeric["display"]
    assert numeric["source"]  # traceable back to the workbook


def test_na_and_errors_are_visible_in_the_view(fixture_files: dict[str, Path]) -> None:
    view = _view(fixture_files, "iqc_dataset_a.xlsx", "IQC")
    values = [value for row in view["rows"] for value in row["values"]]
    assert any(value["type"] == "na" for value in values)
    errors = [value for value in values if value["type"] == "error"]
    assert errors and all(value["error"] == "#DIV/0!" for value in errors)


def test_field_view_names_indicator_model_and_series(fixture_files: dict[str, Path]) -> None:
    view = _view(fixture_files, "field_asr_casr.xlsx", "FIELD", index=1)
    assert view["table"] == "CASR — Field Quality"
    assert view["periods"] == ["W31", "W32", "W33"]
    assert view["hierarchy"] == ["category", "subcategory", "series"]
    assert {row["category"] for row in view["rows"]} == {"CASR"}
    assert {row["subcategory"] for row in view["rows"]} == {"MX", "Mobile"}
    assert {row["seriesType"] for row in view["rows"]} == {"Target", "Result"}
    assert {row["metric"] for row in view["rows"]} == {None}


def test_transposed_view_is_period_first(fixture_files: dict[str, Path]) -> None:
    view = _view(fixture_files, "field_transposed.xlsx", "FIELD")
    assert view["periodAxis"] == "rows"
    assert [row["period"] for row in view["rows"]] == ["W30", "W31", "W32", "W33"]
    assert {value["metric"] for value in view["rows"][0]["values"]} == {
        "Sales",
        "Defects",
        "ASR",
        "CASR",
    }


def test_inspection_tool_renders_a_readable_report(fixture_files: dict[str, Path]) -> None:
    report = build_report(fixture_files["iqc_dataset_a.xlsx"], "IQC", max_rows=3)
    assert report["parserVersion"]
    text = render(report)
    assert "hierarchy: category > subcategory > metric" in text
    assert "SEC / Total / PPM" in text
    assert "W32=" in text
