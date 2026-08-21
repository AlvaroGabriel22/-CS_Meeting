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
# The layer selects and arranges; it does not calculate (ADR-0036)
# --------------------------------------------------------------------------- #
def test_the_analytics_layer_does_no_arithmetic() -> None:
    """The user calculates in Excel; this layer reads what the file holds."""
    for name in ("compute_delta", "compare_periods", "compare_versions",
                 "build_insights", "build_trends"):
        assert not hasattr(A, name), f"{name} would be the system calculating"


def test_a_series_carries_only_what_the_file_says(iqc_real: Path) -> None:
    series = A.table_series(_tables(iqc_real)[0], filters={"metric": "PPM"})
    assert series
    for item in series:
        assert set(item) == {
            "key", "label", "selector", "sheet", "sourceRange", "tableId", "points",
        }
        for point in item["points"]:
            assert set(point) == {"period", "value", "display", "valueType", "source"}
