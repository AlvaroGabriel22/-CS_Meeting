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


def test_reading_a_snapshot_never_changes_it(client, iqc_evolution) -> None:
    first = _upload(client, iqc_evolution["a"])
    before = client.get(f"/api/versions/{first['versionId']}/view").json()

    client.get(f"/api/versions/{first['versionId']}/analytics/series")
    client.get(f"/api/versions/{first['versionId']}/charts")

    after = client.get(f"/api/versions/{first['versionId']}/view").json()
    assert before == after  # reading never writes


def test_the_api_offers_no_comparison_or_executive_endpoint(client, iqc_real: Path) -> None:
    """The page has three containers; nothing else is served (ADR-0036)."""
    created = _upload(client, iqc_real)
    version = created["versionId"]
    for path in (
        f"/api/versions/{version}/analytics/comparison",
        f"/api/versions/{version}/analytics/executive",
        f"/api/versions/{version}/analytics/versus/{version}",
        f"/api/versions/{version}/issues",
    ):
        assert client.get(path).status_code == 404, path
