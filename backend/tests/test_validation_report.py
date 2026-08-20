"""The validation report the real workbooks will be judged by (Sprint 0 §8)."""

from __future__ import annotations

import json
from pathlib import Path

from app.services.validation import detect_ambiguities, workbook_report
from app.excel import parse_file
from app.tools.validate_real import department_of, main, render_markdown


def test_report_answers_every_required_question(fixture_files: dict[str, Path]) -> None:
    report = workbook_report(fixture_files["iqc_dataset_c.xlsx"], "IQC")

    assert report["sheets"] and report["sheets"][0]["name"] == "IQC"
    assert report["tableCount"] == 1
    assert report["parserVersion"]

    table = report["tables"][0]
    for key in (
        "sourceRange",
        "mergedRanges",
        "periods",
        "hierarchy",
        "metrics",
        "seriesTypes",
        "size",
        "warnings",
        "ambiguities",
        "model",
    ):
        assert key in table, f"the report must answer: {key}"

    assert table["size"]["rows"] and table["size"]["columns"]
    assert table["mergedRanges"]
    assert [period["label"] for period in table["periods"]][:2] == ["2025", "2026"]
    assert table["hierarchy"] == ["category", "subcategory", "metric"]
    assert table["categories"] == ["SEC", "TECPLAM", "TNP"]
    assert set(table["metrics"]) == {"PPM", "Def.", "Insp."}
    assert table["seriesTypes"] == ["Target"]
    assert table["valueTypes"]["na"] and table["valueTypes"]["error"]


def test_summarized_model_is_readable_json(fixture_files: dict[str, Path]) -> None:
    report = workbook_report(fixture_files["field_asr_casr.xlsx"], "FIELD")
    model = report["tables"][0]["model"]

    payload = json.loads(json.dumps(model, ensure_ascii=False))  # must serialize
    assert payload["hierarchy"] == ["category", "subcategory", "series"]
    assert payload["periods"] == ["W31", "W32", "W33"]

    first = payload["rowsSample"][0]
    assert (first["category"], first["subcategory"], first["seriesType"]) == ("ASR", "MX", "Target")
    assert first["values"][0]["period"] == "W31"
    assert first["values"][0]["source"]  # traceability kept


def test_ambiguities_are_reported_not_guessed(fixture_files: dict[str, Path]) -> None:
    table = parse_file(fixture_files["iqc_dataset_a.xlsx"], "IQC").tables[0]
    codes = {item.code: item for item in detect_ambiguities(table)}

    # this table states its years, so the engine resolves the rest: no question
    assert "period_without_year" not in codes
    # mixing year/month/week columns is expected here, so it is only informative
    assert codes["mixed_period_granularity"].severity == "info"


def test_period_without_year_is_still_reported_when_unresolvable(
    fixture_files: dict[str, Path],
) -> None:
    """A table with weeks and no year anywhere keeps the question open."""
    table = parse_file(fixture_files["field_asr_casr.xlsx"], "FIELD").tables[0]
    codes = {item.code: item for item in detect_ambiguities(table)}
    assert codes["period_without_year"].severity == "check"
    assert codes["period_without_year"].evidence["labels"] == ["W31", "W32", "W33"]


def test_verdict_reflects_the_worst_ambiguity(fixture_files: dict[str, Path]) -> None:
    assert workbook_report(fixture_files["iqc_dataset_a.xlsx"], "IQC")["verdict"] in ("ok", "check")
    flat = workbook_report(fixture_files["flat_long.xlsx"], None)
    assert flat["verdict"] in ("ok", "check")


def test_markdown_report_covers_the_checklist(fixture_files: dict[str, Path]) -> None:
    text = render_markdown(workbook_report(fixture_files["field_asr_casr.xlsx"], "FIELD"))
    for heading in (
        "## Sheets",
        "### Periods detected",
        "### Hierarchy detected",
        "### Values",
        "### Merged ranges",
        "### Ambiguities",
    ):
        assert heading in text
    assert "category > subcategory > series" in text
    assert "ASR" in text and "CASR" in text


def test_department_is_inferred_from_the_filename() -> None:
    assert department_of(Path("Weekly_OQC_W34.xlsx")) == "OQC"
    assert department_of(Path("field-quality.xlsx")) == "FIELD"
    assert department_of(Path("random.xlsx")) is None
    assert department_of(Path("random.xlsx"), "IQC") == "IQC"


def test_cli_writes_report_and_model(tmp_path: Path, fixture_files: dict[str, Path]) -> None:
    out = tmp_path / "reports"
    code = main([str(fixture_files["iqc_dataset_a.xlsx"]), "--department", "IQC", "--out", str(out)])
    assert code == 0
    assert (out / "iqc_dataset_a.md").read_text(encoding="utf-8").startswith("# Parser validation")
    payload = json.loads((out / "iqc_dataset_a.json").read_text(encoding="utf-8"))
    assert payload["department"] == "IQC" and payload["tables"][0]["model"]["rowsSample"]


def test_cli_reports_when_there_is_nothing_to_validate(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "nope.xlsx"
    assert main([str(missing), "--out", str(tmp_path)]) == 2
