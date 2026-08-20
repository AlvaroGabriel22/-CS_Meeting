"""Import endpoint: validation, persistence and the wire contract."""

from __future__ import annotations

from pathlib import Path


def _upload(client, path: Path, department: str = "IQC", force: bool = False, name: str | None = None):
    return client.post(
        "/api/uploads",
        data={"department": department, "force": str(force).lower()},
        files={
            "file": (
                name or path.name,
                path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def test_health_exposes_capabilities(client) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["maxActivePresentations"] == 8
    assert body["languages"] == ["en", "pt-BR", "ko"]


def test_upload_parses_and_persists(client, fixture_files: dict[str, Path]) -> None:
    response = _upload(client, fixture_files["iqc_dataset_a.xlsx"])
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["department"] == "IQC"
    assert body["rawFile"]["sha256"]
    assert body["summary"]["tableCount"] == 1
    assert "W32" in body["summary"]["periodLabels"]

    table_summary = body["tables"][0]
    assert table_summary["periodAxis"] == "columns"
    assert table_summary["sourceRange"].startswith("B1:")

    detail = client.get(f"/api/imports/{body['id']}/tables/{table_summary['id']}")
    assert detail.status_code == 200
    table = detail.json()
    assert table["headerRowCount"] == 1
    assert table["labelColCount"] == 3
    assert len(table["cells"]) > 100
    assert any(cell["errorCode"] == "#DIV/0!" for cell in table["cells"])
    assert any(cell["valueType"] == "na" for cell in table["cells"])
    assert all("source" in cell for cell in table["cells"])


def test_import_listing_and_lookup(client, fixture_files: dict[str, Path]) -> None:
    created = _upload(client, fixture_files["field_asr_casr.xlsx"], department="FIELD").json()
    fetched = client.get(f"/api/imports/{created['id']}").json()
    assert fetched["id"] == created["id"]
    assert len(fetched["tables"]) == 2

    listed = client.get("/api/imports", params={"department": "FIELD"}).json()
    assert any(item["id"] == created["id"] for item in listed)


def test_missing_import_returns_structured_error(client) -> None:
    response = client.get("/api/imports/999999")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_rejects_non_spreadsheet_extension(client) -> None:
    response = client.post(
        "/api/imports",
        data={"department": "IQC"},
        files={"file": ("evil.txt", b"PK\x03\x04 not really", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "upload_rejected"


def test_rejects_file_that_only_pretends_to_be_xlsx(client) -> None:
    response = client.post(
        "/api/imports",
        data={"department": "IQC"},
        files={
            "file": (
                "fake.xlsx",
                b"<html>not a workbook</html>",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "upload_rejected"


def test_path_traversal_filename_is_neutralised(client, fixture_files: dict[str, Path]) -> None:
    response = _upload(
        client,
        fixture_files["iqc_dataset_a.xlsx"],
        force=True,
        name="../../../../etc/passwd.xlsx",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["rawFile"]["originalFilename"] == "passwd.xlsx"
    assert "/" not in body["rawFile"]["originalFilename"]


def test_identical_file_is_not_parsed_twice(client, fixture_files: dict[str, Path]) -> None:
    first = _upload(client, fixture_files["iqc_dataset_b.xlsx"]).json()
    assert first["reused"] is False

    second = _upload(client, fixture_files["iqc_dataset_b.xlsx"]).json()
    assert second["reused"] is True
    assert second["id"] == first["id"]  # the stored interpretation is reused

    forced = _upload(client, fixture_files["iqc_dataset_b.xlsx"], force=True).json()
    assert forced["reused"] is False and forced["id"] != first["id"]


def test_interpretation_endpoint_shows_the_meaning(client, fixture_files: dict[str, Path]) -> None:
    created = _upload(client, fixture_files["iqc_dataset_c.xlsx"]).json()
    table_id = created["tables"][0]["id"]

    view = client.get(
        f"/api/imports/{created['id']}/tables/{table_id}/interpretation",
        params={"maxRows": 3},
    )
    assert view.status_code == 200
    body = view.json()
    assert body["department"] == "IQC"
    assert body["hierarchy"] == ["category", "subcategory", "metric"]
    assert body["periods"][:2] == ["2025", "2026"]
    assert {"W33", "W34", "Sep"} <= set(body["periods"])

    row = body["rows"][0]
    assert (row["category"], row["subcategory"], row["metric"]) == ("SEC", "Total", "PPM")
    assert len(row["values"]) == len(body["periods"])
    assert row["values"][0]["period"] == "2025"
