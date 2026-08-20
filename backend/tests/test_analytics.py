"""Sprint 3 — charts, period selection and comparison over the normalized model.

Nothing here knows a month, a quarter or a week by name: the fixtures decide
which periods exist, and the same code reads all of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.excel import parse_file
from app.services import analytics as A
from app.services.interpretation import from_normalized


def _tables(path: Path, department: str = "IQC"):
    return [from_normalized(table, department) for table in parse_file(path, department).tables]


def _series(path: Path, **filters):
    return A.build_series_response(_tables(path), filters=filters or None)


def _one(response: dict, label: str) -> dict:
    return next(item for item in response["series"] if item["label"] == label)


def _values(series: dict) -> dict[str, float | None]:
    return {point["period"]["label"]: point["value"] for point in series["points"]}


# --------------------------------------------------------------------------- #
# A / B. Series over one and many periods
# --------------------------------------------------------------------------- #
def test_a_series_over_a_single_period(iqc_real: Path) -> None:
    tables = _tables(iqc_real)
    response = A.build_series_response(tables, filters={"table": "TTL", "metric": "Rej. Lot"})
    series = _one(response, "Total · Rej. Lot")
    august = next(point for point in series["points"] if point["period"]["label"] == "Aug")
    assert august["value"] == 2.0
    assert august["display"] == "2"
    assert august["source"] == "I4"  # traceable to the workbook cell


def test_b_series_over_every_period_of_the_file(iqc_real: Path) -> None:
    response = _series(iqc_real, table="TTL", metric="Insp. Lot")
    assert [period["label"] for period in response["periods"]] == [
        "'25", "'26", "1Q", "2Q", "3Q", "Aug",
    ]
    series = _one(response, "Total · Insp. Lot")
    assert len(series["points"]) == 6
    assert _values(series)["'25"] == 20970.0


# --------------------------------------------------------------------------- #
# C. Ordering by sortKey
# --------------------------------------------------------------------------- #
def test_c_chronological_order_uses_sort_keys(iqc_evolution) -> None:
    tables = _tables(iqc_evolution["c"])
    by_file = A.build_series_response(tables, filters={"table": "TTL"}, order="file")
    by_time = A.build_series_response(tables, filters={"table": "TTL"}, order="chronological")

    assert [period["label"] for period in by_file["periods"]] == [
        "'25", "'26", "1Q", "2Q", "3Q", "4Q", "Aug", "Sep", "Oct",
    ]
    # chronological is the engine's own order: by year, then by granularity,
    # then by ordinal — coarse periods first, each group in time order
    assert [period["label"] for period in by_time["periods"]] == [
        "'25", "'26", "1Q", "2Q", "3Q", "4Q", "Aug", "Sep", "Oct",
    ]
    months = [period for period in by_time["periods"] if period["kind"] == "month"]
    assert [period["label"] for period in months] == ["Aug", "Sep", "Oct"]
    assert [period["sortKey"] for period in months] == ["2026-M08", "2026-M09", "2026-M10"]
    # the points follow the same order as the axis
    series = by_time["series"][0]
    assert [point["period"]["label"] for point in series["points"]] == [
        period["label"] for period in by_time["periods"]
    ]


def test_c_sort_keys_are_carried_on_every_point(iqc_evolution) -> None:
    response = _series(iqc_evolution["e"], table="TTL", metric="Rej. Lot")
    keys = {point["period"]["label"]: point["period"]["sortKey"] for point in response["series"][0]["points"]}
    assert keys["Nov"] == "2026-M11" and keys["W48"] == "2026-W48"
    assert keys["4Q"] == "2026-Q4" and keys["'25"] == "2025-Y"


# --------------------------------------------------------------------------- #
# D-G. The period axis evolves; the code does not
# --------------------------------------------------------------------------- #
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
def test_d_to_g_every_generation_produces_a_chart(iqc_evolution, key: str, expected: list) -> None:
    response = _series(iqc_evolution[key], table="TTL", metric="Rej. Lot")
    assert [period["label"] for period in response["periods"]] == expected
    for series in response["series"]:
        assert [point["period"]["label"] for point in series["points"]] == expected
        assert all(point["value"] is not None for point in series["points"])


def test_months_keep_their_quarter_through_the_chart_layer(iqc_evolution) -> None:
    quarters = {}
    for key in ("a", "b", "c", "d"):
        for period in _series(iqc_evolution[key], table="TTL")["periods"]:
            if period["kind"] == "month":
                quarters[period["label"]] = period["quarter"]
    assert quarters == {
        "Aug": "3Q", "Sep": "3Q", "Oct": "4Q", "Nov": "4Q", "Dec": "4Q",
    }


# --------------------------------------------------------------------------- #
# H-L. Deltas
# --------------------------------------------------------------------------- #
def test_h_i_j_period_comparison_with_absolute_and_percent_delta(iqc_real: Path) -> None:
    comparison = A.compare_periods(
        _tables(iqc_real),
        period_a="3Q",
        period_b="Aug",
        filters={"table": "TTL", "metric": "Rej. Lot"},
        department="IQC",
    )
    row = next(row for row in comparison["rows"] if row["label"] == "Total · Rej. Lot")
    delta = row["delta"]

    assert (delta["valueA"], delta["valueB"]) == (7.0, 2.0)
    assert delta["delta"] == -5.0
    assert delta["deltaPercent"] == pytest.approx(-71.4285, rel=1e-3)
    assert delta["direction"] == "down"
    assert delta["severity"] == "positive"  # fewer rejected lots is better
    assert delta["status"] == "ok"
    # every side keeps its origin
    assert row["sourceA"] and row["sourceB"]


def test_k_a_zero_baseline_never_produces_a_percentage() -> None:
    delta = A.compute_delta(
        {"value": 0.0, "display": "0"},
        {"value": 5.0, "display": "5"},
        metric="Rej. Lot",
        department="IQC",
    )
    assert delta["delta"] == 5.0
    assert delta["deltaPercent"] is None
    assert delta["status"] == "undefined_percent"
    assert delta["direction"] == "up" and delta["severity"] == "negative"


def test_k_zero_to_zero_is_flat_not_a_percentage() -> None:
    delta = A.compute_delta({"value": 0.0}, {"value": 0.0}, metric="PPM", department="IQC")
    assert delta["delta"] == 0.0 and delta["deltaPercent"] is None
    assert delta["direction"] == "flat" and delta["status"] == "undefined_percent"


def test_l_a_missing_period_is_missing_not_zero(iqc_real: Path) -> None:
    comparison = A.compare_periods(
        _tables(iqc_real),
        period_a="Aug",
        period_b="Sep",  # this file has no September
        filters={"table": "TTL", "metric": "Rej. Lot"},
        department="IQC",
    )
    assert "period_not_in_snapshot:Sep" in comparison["warnings"]
    row = comparison["rows"][0]
    assert row["delta"]["valueB"] is None
    assert row["delta"]["delta"] is None and row["delta"]["deltaPercent"] is None
    assert row["delta"]["status"] == "missing_b"


def test_severity_is_unknown_when_the_metric_polarity_is_not_declared() -> None:
    delta = A.compute_delta({"value": 10.0}, {"value": 12.0}, metric="Whatever", department="IQC")
    assert delta["direction"] == "up" and delta["severity"] == "unknown"
    neutral = A.compute_delta({"value": 10.0}, {"value": 12.0}, metric="Insp. Lot", department="IQC")
    assert neutral["severity"] == "neutral"  # a volume is neither good nor bad


# --------------------------------------------------------------------------- #
# M-N. Versions
# --------------------------------------------------------------------------- #
def test_m_comparing_two_snapshots_of_the_same_period(iqc_evolution) -> None:
    older = _tables(iqc_evolution["a"])
    newer = _tables(iqc_evolution["b"])
    comparison = A.compare_versions(
        older, newer, period="Aug", filters={"table": "TTL", "metric": "Rej. Lot"}, department="IQC"
    )

    assert comparison["kind"] == "versions"
    row = next(row for row in comparison["rows"] if row["label"] == "Total · Rej. Lot")
    delta = row["delta"]
    assert delta["valueA"] is not None and delta["valueB"] is not None
    assert delta["delta"] == delta["valueB"] - delta["valueA"]
    assert comparison["periodA"]["label"] == "Aug"


def test_m_a_row_present_in_only_one_version_is_reported_not_zeroed(iqc_evolution) -> None:
    complete = _tables(iqc_evolution["a"])
    partial = [table for table in complete if (table.title or "") != "TNP"]
    comparison = A.compare_versions(
        complete, partial, period="Aug", filters={"metric": "Rej. Lot"}, department="IQC"
    )
    assert any(warning.startswith("rows_only_in_a:") for warning in comparison["warnings"])
    missing = [row for row in comparison["rows"] if row["delta"]["status"] == "missing_b"]
    assert missing and all(row["delta"]["delta"] is None for row in missing)


def test_n_comparison_never_mutates_a_snapshot(iqc_evolution) -> None:
    older = _tables(iqc_evolution["a"])
    newer = _tables(iqc_evolution["d"])
    before = [
        [(cell.row, cell.col, cell.number) for cell in table.cells] for table in older
    ]
    A.compare_versions(older, newer, period="Aug", department="IQC")
    after = [[(cell.row, cell.col, cell.number) for cell in table.cells] for table in older]
    assert before == after


# --------------------------------------------------------------------------- #
# O-S. The IQC tables themselves
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("table_name", ["TTL", "SEC", "TNP"])
def test_o_p_q_every_table_produces_series(iqc_real: Path, table_name: str) -> None:
    response = _series(iqc_real, table=table_name, metric="Insp. Lot")
    assert response["series"], f"{table_name} must produce series"
    assert {series["selector"]["table"] for series in response["series"]} == {table_name}
    assert all(series["sourceRange"] for series in response["series"])  # traceability


def test_r_no_artificial_ppm_is_introduced_by_the_analytics(iqc_real: Path) -> None:
    """PPM exists as a metric of the model; nothing invents rows or values."""
    response = _series(iqc_real, table="TTL")
    metrics = {series["selector"]["metric"] for series in response["series"]}
    assert metrics == {"PPM", "Rej. Lot", "Insp. Lot"}

    ppm = _one(response, "Total · PPM")
    rejected = _one(response, "Total · Rej. Lot")
    inspected = _one(response, "Total · Insp. Lot")
    # the PPM series is read from the sheet, never recomputed here
    august = {series["label"]: _values(series)["Aug"] for series in (ppm, rejected, inspected)}
    assert august["Total · PPM"] == 5495.0
    assert august["Total · Rej. Lot"] == 2.0 and august["Total · Insp. Lot"] == 364.0


def test_s_categories_and_subcategories_are_available_as_series(iqc_real: Path) -> None:
    response = _series(iqc_real, table="TTL", metric="Rej. Lot")
    labels = [series["label"] for series in response["series"]]
    assert labels == [
        "Total · Rej. Lot",
        "Imported · Rej. Lot",
        "Imported · SKD · Rej. Lot",
        "Imported · CKD · Rej. Lot",
        "Local · Rej. Lot",
    ]
    skd = _one(response, "Imported · SKD · Rej. Lot")
    assert skd["selector"]["category"] == "Imported"
    assert skd["selector"]["subcategory"] == "SKD"


def test_selector_options_are_discovered_from_the_snapshot(iqc_real: Path) -> None:
    options = _series(iqc_real)["options"]
    assert options["tables"] == ["TTL", "SEC", "TNP"]
    assert options["categories"] == ["Total", "Imported", "Local"]
    assert options["subcategories"] == ["SKD", "CKD"]
    assert options["metrics"] == ["PPM", "Rej. Lot", "Insp. Lot"]


# --------------------------------------------------------------------------- #
# Executive insights (infrastructure)
# --------------------------------------------------------------------------- #
def test_insights_carry_everything_needed_to_write_and_to_prove_a_sentence(
    iqc_real: Path,
) -> None:
    tables = _tables(iqc_real)
    comparison = A.compare_periods(
        tables,
        period_a="3Q",
        period_b="Aug",
        filters={"table": "TTL", "metric": "Rej. Lot"},
        department="IQC",
    )
    insights = A.build_insights(
        comparison,
        department="IQC",
        version_id=7,
        version_number=2,
        source_ranges={"TTL": "B2:I17"},
        limit=3,
    )
    assert insights
    first = insights[0]
    assert first["department"] == "IQC" and first["table"] == "TTL"
    assert first["metric"] == "Rej. Lot"
    assert first["period"]["label"] == "Aug"
    assert first["referencePeriod"]["label"] == "3Q"
    assert first["value"] is not None and first["previousValue"] is not None
    assert first["direction"] in ("up", "down", "flat")
    assert first["severity"] in ("positive", "negative", "neutral", "unknown")
    assert first["source"] and first["sourceRange"] == "B2:I17"
    assert first["versionId"] == 7 and first["versionNumber"] == 2
    # ranked by the size of the movement
    percents = [abs(item["deltaPercent"]) for item in insights]
    assert percents == sorted(percents, reverse=True)


def test_insights_skip_comparisons_that_have_no_number(iqc_real: Path) -> None:
    comparison = A.compare_periods(
        _tables(iqc_real),
        period_a="Aug",
        period_b="Nov",  # absent from this file
        filters={"table": "TTL"},
        department="IQC",
    )
    assert A.build_insights(comparison, department="IQC", version_id=1) == []
