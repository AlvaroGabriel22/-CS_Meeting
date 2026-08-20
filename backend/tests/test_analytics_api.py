"""The analytics endpoints: model-oriented, version-scoped, traceable."""

from __future__ import annotations

from pathlib import Path


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


def test_series_endpoint_serves_chart_ready_data(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    response = client.get(
        f"/api/versions/{created['versionId']}/analytics/series",
        params={"table": "TTL", "metric": "Rej. Lot"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["versionId"] == created["versionId"]
    assert body["department"] == "IQC"
    assert [period["label"] for period in body["periods"]] == [
        "'25", "'26", "1Q", "2Q", "3Q", "Aug",
    ]
    assert body["options"]["tables"] == ["TTL", "SEC", "TNP"]
    assert body["options"]["metrics"] == ["PPM", "Rej. Lot", "Insp. Lot"]

    series = body["series"][0]
    assert series["selector"]["metric"] == "Rej. Lot"
    assert series["sourceRange"] == "B2:I17"  # traceable to the workbook
    assert series["points"][0]["source"]


def test_series_endpoint_can_order_chronologically(client, iqc_evolution) -> None:
    created = _upload(client, iqc_evolution["c"])
    body = client.get(
        f"/api/versions/{created['versionId']}/analytics/series",
        params={"table": "TTL", "metric": "PPM", "order": "chronological"},
    ).json()
    assert body["order"] == "chronological"
    months = [period for period in body["periods"] if period["kind"] == "month"]
    assert [period["label"] for period in months] == ["Aug", "Sep", "Oct"]
    assert [period["quarter"] for period in months] == ["3Q", "3Q", "4Q"]


def test_period_comparison_endpoint(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    body = client.get(
        f"/api/versions/{created['versionId']}/analytics/comparison",
        params={"periodA": "3Q", "periodB": "Aug", "table": "TTL", "metric": "Rej. Lot"},
    ).json()

    assert body["kind"] == "periods"
    assert body["periodA"]["label"] == "3Q" and body["periodB"]["label"] == "Aug"
    row = body["rows"][0]
    assert row["delta"]["delta"] is not None
    assert row["delta"]["status"] == "ok"
    assert body["insights"] and body["insights"][0]["versionId"] == created["versionId"]
    assert body["insights"][0]["sourceRange"] == "B2:I17"


def test_period_comparison_reports_an_absent_period(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    body = client.get(
        f"/api/versions/{created['versionId']}/analytics/comparison",
        params={"periodA": "Aug", "periodB": "Dec", "table": "TTL"},
    ).json()
    assert "period_not_in_snapshot:Dec" in body["warnings"]
    assert all(row["delta"]["status"] == "missing_b" for row in body["rows"])
    assert body["insights"] == []


def test_version_comparison_endpoint(client, iqc_evolution) -> None:
    first = _upload(client, iqc_evolution["a"])
    second = _upload(client, iqc_evolution["b"])

    body = client.get(
        f"/api/versions/{first['versionId']}/analytics/versus/{second['versionId']}",
        params={"period": "Aug", "table": "TTL", "metric": "Insp. Lot"},
    ).json()

    assert body["kind"] == "versions"
    assert body["versionId"] == first["versionId"]
    assert body["comparedVersionId"] == second["versionId"]
    assert body["periodA"]["label"] == "Aug"
    row = body["rows"][0]
    assert row["delta"]["valueA"] is not None and row["delta"]["valueB"] is not None
    assert row["sourceA"] and row["sourceB"]


def test_comparing_a_version_with_itself_is_refused(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    response = client.get(
        f"/api/versions/{created['versionId']}/analytics/versus/{created['versionId']}",
        params={"period": "Aug"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_analytics_never_changes_a_snapshot(client, iqc_evolution) -> None:
    first = _upload(client, iqc_evolution["a"])
    before = client.get(f"/api/versions/{first['versionId']}/view").json()

    second = _upload(client, iqc_evolution["d"])
    client.get(
        f"/api/versions/{first['versionId']}/analytics/versus/{second['versionId']}",
        params={"period": "Aug"},
    )
    client.get(
        f"/api/versions/{first['versionId']}/analytics/comparison",
        params={"periodA": "3Q", "periodB": "Aug"},
    )

    after = client.get(f"/api/versions/{first['versionId']}/view").json()
    assert before == after  # reading never writes
