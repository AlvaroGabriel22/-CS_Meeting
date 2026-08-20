"""The executive endpoint, and the version/period dimensions that drive it."""

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


def test_01_the_executive_view_answers_for_one_version(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    response = client.get(
        f"/api/versions/{created['versionId']}/analytics/executive",
        params={"table": "TTL"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["versionId"] == created["versionId"]
    assert body["versionNumber"] == created["versionNumber"]
    assert body["department"] == "IQC"
    assert body["period"]["label"] == "Aug"
    assert body["previousPeriod"]["label"] == "3Q"
    assert body["comparisonBasis"] == "preceding"
    assert body["metric"] == "PPM"
    assert [kpi["label"] for kpi in body["kpis"]] == [
        "Total · PPM", "Imported · PPM", "Local · PPM",
    ]
    assert body["insights"] and body["insights"][0]["score"] >= body["insights"][-1]["score"]
    assert body["options"]["tables"] == ["TTL", "SEC", "TNP"]
    assert [period["label"] for period in body["periods"]] == [
        "'25", "'26", "1Q", "2Q", "3Q", "Aug",
    ]


def test_02_03_the_version_and_the_period_drive_the_answer(client, iqc_evolution) -> None:
    first = _upload(client, iqc_evolution["a"])
    second = _upload(client, iqc_evolution["c"])

    older = client.get(
        f"/api/versions/{first['versionId']}/analytics/executive", params={"table": "TTL"}
    ).json()
    newer = client.get(
        f"/api/versions/{second['versionId']}/analytics/executive", params={"table": "TTL"}
    ).json()

    # each version answers with its own period axis
    assert older["period"]["label"] == "Aug"
    assert newer["period"]["label"] == "Oct" and newer["period"]["quarter"] == "4Q"
    assert newer["previousPeriod"]["label"] == "Sep"
    assert newer["comparisonBasis"] == "same_kind"

    # and the period selects the analysis inside one version
    september = client.get(
        f"/api/versions/{second['versionId']}/analytics/executive",
        params={"table": "TTL", "period": "Sep"},
    ).json()
    assert september["period"]["label"] == "Sep"
    assert september["period"]["quarter"] == "3Q"
    assert september["previousPeriod"]["label"] == "Aug"
    assert all(kpi["period"]["label"] == "Sep" for kpi in september["kpis"])
    assert all(insight["period"]["label"] == "Sep" for insight in september["insights"])


def test_the_metric_can_be_switched_without_touching_the_period(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    inspected = client.get(
        f"/api/versions/{created['versionId']}/analytics/executive",
        params={"table": "TTL", "metric": "Insp. Lot"},
    ).json()
    assert inspected["metric"] == "Insp. Lot"
    assert all(kpi["polarity"] == "neutral" for kpi in inspected["kpis"])
    assert all(kpi["label"].endswith("Insp. Lot") for kpi in inspected["kpis"])


def test_12_version_comparison_still_answers_from_the_same_dimensions(
    client, iqc_evolution
) -> None:
    first = _upload(client, iqc_evolution["a"])
    second = _upload(client, iqc_evolution["b"])

    body = client.get(
        f"/api/versions/{first['versionId']}/analytics/versus/{second['versionId']}",
        params={"period": "Aug", "table": "TTL", "metric": "PPM"},
    ).json()
    assert body["kind"] == "versions"
    assert body["periodA"]["label"] == "Aug"
    assert body["rows"] and body["rows"][0]["sourceA"] and body["rows"][0]["sourceB"]


def test_the_executive_view_never_writes(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    before = client.get(f"/api/versions/{created['versionId']}/view").json()
    client.get(f"/api/versions/{created['versionId']}/analytics/executive")
    after = client.get(f"/api/versions/{created['versionId']}/view").json()
    assert before == after
