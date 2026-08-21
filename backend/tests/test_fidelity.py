"""Sprint 6 — upload, interpret, render: the file and nothing but the file.

These tests read the real workbook twice: once with openpyxl, directly, and
once through the whole product (upload → parse → snapshot → API → render
model → chart).  Then they compare.  Anything the product shows that the file
does not hold is a defect, and so is anything the file holds that the product
drops.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest


def _upload(client, path: Path, department: str = "IQC"):
    return client.post(
        "/api/uploads",
        data={"department": department, "createVersion": "true"},
        files={
            "file": (
                path.name,
                path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    ).json()


def _workbook_numbers(path: Path, sheet_name: str = "IQC") -> dict[str, float]:
    """Every number the file holds, by cell address — the reference truth."""
    sheet = openpyxl.load_workbook(path, data_only=True)[sheet_name]
    return {
        cell.coordinate: float(cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
    }


def _served_numbers(client, version_id: int) -> dict[str, float]:
    """Every number the product serves, by the cell it says it came from."""
    imports = client.get(f"/api/versions/{version_id}/imports").json()
    numbers: dict[str, float] = {}
    for item in imports:
        for summary in item["tables"]:
            table = client.get(
                f"/api/imports/{item['id']}/tables/{summary['id']}"
            ).json()
            for cell in table["cells"]:
                if cell["number"] is not None and cell["source"]:
                    numbers[cell["source"]] = float(cell["number"])
    return numbers


# --------------------------------------------------------------------------- #
# 1-2. Import and interpretation
# --------------------------------------------------------------------------- #
def test_the_real_workbook_imports_and_is_interpreted(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)

    assert created["success"] and created["versionId"]
    assert created["tableNames"] == ["TTL", "SEC", "TNP"]  # discovered, not configured
    assert created["periods"] == ["'25", "'26", "1Q", "2Q", "3Q", "Aug"]
    assert created["parserVersion"]
    assert created["rawFile"]["originalFilename"] == "RawdataIQC.xlsx"


# --------------------------------------------------------------------------- #
# 3. Values
# --------------------------------------------------------------------------- #
def test_every_number_served_is_the_number_the_file_holds(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    expected = _workbook_numbers(iqc_real)
    served = _served_numbers(client, created["versionId"])

    assert served, "the snapshot serves numbers"
    for address, value in served.items():
        assert address in expected, f"{address} is not a number in the file"
        assert value == pytest.approx(expected[address]), address


def test_no_number_of_the_data_sheet_is_lost(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    expected = _workbook_numbers(iqc_real)
    served = _served_numbers(client, created["versionId"])
    missing = sorted(set(expected) - set(served))
    assert missing == [], f"these cells were dropped: {missing}"


def test_an_error_cell_is_reported_as_an_error_not_as_a_number(
    client, fixture_files
) -> None:
    """``#DIV/0!`` stays ``#DIV/0!`` — it is never read as zero."""
    created = _upload(client, fixture_files["iqc_dataset_c.xlsx"])
    imports = client.get(f"/api/versions/{created['versionId']}/imports").json()
    cells = [
        cell
        for item in imports
        for summary in item["tables"]
        for cell in client.get(
            f"/api/imports/{item['id']}/tables/{summary['id']}"
        ).json()["cells"]
    ]
    errors = [cell for cell in cells if cell["valueType"] == "error"]
    assert errors, "this fixture carries a division by zero"
    for cell in errors:
        assert cell["number"] is None
        assert cell["rawValue"] and cell["rawValue"].startswith("#")


# --------------------------------------------------------------------------- #
# 4. Structure
# --------------------------------------------------------------------------- #
def test_the_merges_of_the_file_reach_the_screen_as_spans(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    view = client.get(f"/api/versions/{created['versionId']}/view").json()
    table = view["tables"][0]

    spans = [
        cell
        for row in table["rows"]
        for cell in row["cells"]
        if cell["rowSpan"] > 1 or cell["colSpan"] > 1
    ]
    assert spans, "the category column of the real file is merged vertically"
    # a covered cell is absent from the grid, exactly as in Excel
    drawn = {(cell["row"], cell["col"]) for row in table["rows"] for cell in row["cells"]}
    for cell in spans:
        for offset in range(1, cell["rowSpan"]):
            assert (cell["row"] + offset, cell["col"]) not in drawn


def test_the_hierarchy_the_file_implies_is_preserved(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    view = client.get(f"/api/versions/{created['versionId']}/view").json()
    table = view["tables"][0]

    assert table["hierarchy"] == ["category", "subcategory", "metric"]
    categories = [row["category"] for row in table["rows"] if row["category"]]
    assert categories[:3] == ["Total", "Total", "Total"]
    assert "Imported" in categories and "Local" in categories
    assert {row["subcategory"] for row in table["rows"]} >= {"SKD", "CKD"}


def test_the_headline_row_keeps_the_empty_cell_the_file_has(client, iqc_real: Path) -> None:
    """The PPM row carries no metric label in the file, and none is drawn."""
    created = _upload(client, iqc_real)
    view = client.get(f"/api/versions/{created['versionId']}/view").json()
    table = view["tables"][0]

    headline = next(row for row in table["rows"] if row["isHeadline"])
    assert headline["metric"] == "PPM"  # inferred
    assert "metric" in headline["inferred"]
    labels = [cell["text"] for cell in headline["cells"] if cell["kind"] == "label"]
    assert all(label != "PPM" for label in labels), "no invented label is drawn"


def test_the_periods_are_the_file_s_own_columns(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    view = client.get(f"/api/versions/{created['versionId']}/view").json()
    for table in view["tables"]:
        assert [period["label"] for period in table["periods"]] == [
            "'25", "'26", "1Q", "2Q", "3Q", "Aug",
        ]


# --------------------------------------------------------------------------- #
# 5. Charts
# --------------------------------------------------------------------------- #
def test_a_chart_is_built_only_from_values_the_file_holds(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    body = client.get(
        f"/api/versions/{created['versionId']}/analytics/series",
        params={"table": "TTL", "metric": "PPM"},
    ).json()
    expected = _workbook_numbers(iqc_real)

    assert body["series"]
    for series in body["series"]:
        for point in series["points"]:
            if point["value"] is None:
                continue
            assert point["source"], "a plotted point proves its cell"
            assert point["value"] == pytest.approx(expected[point["source"]])


def test_the_same_snapshot_always_produces_the_same_chart(client, iqc_real: Path) -> None:
    """Determinism: no sampling, no smoothing, no randomness anywhere."""
    created = _upload(client, iqc_real)
    params = {"table": "TTL", "metric": "PPM", "order": "chronological"}
    first = client.get(
        f"/api/versions/{created['versionId']}/analytics/series", params=params
    ).json()
    second = client.get(
        f"/api/versions/{created['versionId']}/analytics/series", params=params
    ).json()
    assert first == second


def test_a_missing_reading_is_a_gap_never_a_zero(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    body = client.get(
        f"/api/versions/{created['versionId']}/analytics/series", params={"table": "TTL"}
    ).json()
    for series in body["series"]:
        for point in series["points"]:
            if point["value"] is None:
                assert point["valueType"] in ("empty", "na", "error", "text")


# --------------------------------------------------------------------------- #
# 6. Regression — the same file read twice reads the same
# --------------------------------------------------------------------------- #
def test_uploading_the_same_file_twice_reuses_one_interpretation(
    client, iqc_real: Path
) -> None:
    first = _upload(client, iqc_real)
    second = _upload(client, iqc_real)

    assert second["reused"] is True
    assert second["id"] == first["id"]
    assert second["versionId"] != first["versionId"]  # a new snapshot, same data


def test_an_older_snapshot_keeps_showing_what_it_froze(client, iqc_real, iqc_evolution) -> None:
    older = _upload(client, iqc_real)
    _newer = _upload(client, iqc_evolution["c"])

    view = client.get(f"/api/versions/{older['versionId']}/view").json()
    assert [table["title"] for table in view["tables"]] == ["TTL", "SEC", "TNP"]
    assert [period["label"] for period in view["tables"][0]["periods"]] == [
        "'25", "'26", "1Q", "2Q", "3Q", "Aug",
    ]
