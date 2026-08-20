"""Snapshots: every upload freezes a version, and old versions never move."""

from __future__ import annotations

from pathlib import Path

from app.db.models import Department, PresentationVersion, VersionStatus
from app.excel import parse_file
from app.services import presentation_service


def _upload(client, path: Path, department: str = "IQC", create_version: bool = True):
    return client.post(
        "/api/uploads",
        data={"department": department, "createVersion": str(create_version).lower()},
        files={
            "file": (
                path.name,
                path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


# --------------------------------------------------------------------------- #
# 15-16. Snapshot created and stored
# --------------------------------------------------------------------------- #
def test_15_16_upload_creates_a_snapshot_in_sqlite(client, iqc_real: Path) -> None:
    body = _upload(client, iqc_real).json()

    assert body["success"] is True
    assert body["department"] == "IQC"
    assert body["versionId"] and body["presentationId"]
    assert body["versionNumber"] >= 1  # other uploads may already have run
    assert body["parserVersion"]
    assert body["tableNames"] == ["TTL", "SEC", "TNP"]
    assert body["periods"] == ["'25", "'26", "1Q", "2Q", "3Q", "Aug"]

    version = client.get(f"/api/versions/{body['versionId']}").json()
    assert version["status"] == "published"
    assert version["summary"]["tableNames"] == ["TTL", "SEC", "TNP"]
    assert version["summary"]["rawFile"] == iqc_real.name
    assert version["importIds"] == [body["id"]]


def test_17_the_snapshot_can_be_read_back(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real).json()
    imports = client.get(f"/api/versions/{created['versionId']}/imports").json()

    assert len(imports) == 1
    tables = imports[0]["tables"]
    assert [table["title"] for table in tables] == ["TTL", "SEC", "TNP"]
    assert tables[0]["hierarchy"] == ["category", "subcategory", "metric"]

    detail = client.get(f"/api/imports/{imports[0]['id']}/tables/{tables[0]['id']}").json()
    assert detail["title"] == "TTL"
    assert len(detail["cells"]) > 100
    assert detail["mergedRanges"] == ["B2:C2", "B6:B14", "B15:B17"]


def test_preview_does_not_create_a_version(client, iqc_evolution) -> None:
    body = _upload(client, iqc_evolution["b"], create_version=False).json()
    assert body["versionId"] is None and body["success"] is True
    assert body["tableNames"] == ["TTL", "SEC", "TNP"]
    # confirming afterwards costs no second parse (content hash reuse)
    confirmed = _upload(client, iqc_evolution["b"], create_version=True).json()
    assert confirmed["reused"] is True and confirmed["versionId"]


def test_each_upload_adds_a_version_and_never_rewrites_the_previous(
    client, iqc_evolution
) -> None:
    first = _upload(client, iqc_evolution["c"]).json()
    second = _upload(client, iqc_evolution["d"]).json()
    third = _upload(client, iqc_evolution["e"]).json()

    numbers = [first["versionNumber"], second["versionNumber"], third["versionNumber"]]
    assert numbers == sorted(numbers) and len(set(numbers)) == 3
    assert first["presentationId"] == second["presentationId"] == third["presentationId"]

    # version 1 still shows what it showed when it was saved
    old = client.get(f"/api/versions/{first['versionId']}").json()
    assert old["summary"]["periodLabels"] == ["'25", "'26", "1Q", "2Q", "3Q", "Aug", "Sep", "Oct"]
    new = client.get(f"/api/versions/{third['versionId']}").json()
    assert "4Q" in new["summary"]["periodLabels"] and "W48" in new["summary"]["periodLabels"]
    assert new["parentVersionId"] == second["versionId"]

    versions = client.get(f"/api/presentations/{first['presentationId']}/versions").json()
    assert [version["number"] for version in versions] == sorted(
        (version["number"] for version in versions), reverse=True
    )


def test_presentation_is_created_once_per_department(client, session, iqc_real: Path) -> None:
    _upload(client, iqc_real)
    listed = client.get("/api/presentations", params={"department": "IQC"}).json()
    assert len(listed) == 1
    assert listed[0]["department"] == "IQC"
    assert listed[0]["versionCount"] >= 1
    assert listed[0]["latestVersion"]["status"] == "published"


def test_snapshot_service_links_the_import_without_copying_it(session, iqc_real: Path) -> None:
    from app.db.models import RawDataFile
    from app.services.import_service import persist_parsed_workbook

    parsed = parse_file(iqc_real, "IQC")
    raw = RawDataFile(
        department=Department.IQC,
        original_filename=iqc_real.name,
        stored_path=f"raw/IQC/{iqc_real.name}",
        mime_type="application/octet-stream",
        size_bytes=iqc_real.stat().st_size,
        sha256="f" * 64,
    )
    session.add(raw)
    session.flush()
    data = persist_parsed_workbook(session, department=Department.IQC, raw_file=raw, parsed=parsed)
    session.flush()

    version = presentation_service.snapshot_for_import(
        session, department=Department.IQC, data=data
    )
    session.flush()

    stored = session.get(PresentationVersion, version.id)
    assert stored.status is VersionStatus.PUBLISHED
    assert [item.id for item in stored.imports] == [data.id]  # referenced, not copied
    assert stored.summary["tableNames"] == ["TTL", "SEC", "TNP"]
    assert stored.label == "Aug"  # named after the last period in the file
