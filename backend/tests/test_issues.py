"""Issue reports: editorial half editable, analytical half proven."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

#: the smallest valid PNG, used as an attachment in the tests
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


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


@pytest.fixture()
def version(client, iqc_real: Path) -> int:
    return _upload(client, iqc_real)["versionId"]


# --------------------------------------------------------------------------- #
# 1, 4-6. Creation, provenance, version and period
# --------------------------------------------------------------------------- #
def test_01_an_issue_is_raised_from_a_reading(client, version: int) -> None:
    response = client.post(
        f"/api/versions/{version}/issues",
        json={"table": "TTL", "category": "Local", "metric": "PPM", "period": "Aug"},
    )
    assert response.status_code == 201
    issue = response.json()

    assert issue["title"] == "Local · PPM increase"  # named after what happened
    assert issue["status"] == "open"
    assert issue["severity"] == "medium"  # PPM rising is bad, no target breached
    assert issue["versionId"] == version


def test_04_the_numbers_come_from_the_snapshot_not_from_the_client(
    client, version: int
) -> None:
    issue = client.post(
        f"/api/versions/{version}/issues",
        json={
            "table": "TTL",
            "category": "Local",
            "metric": "PPM",
            "period": "Aug",
            # a client claiming its own numbers must be ignored
            "title": "Local PPM",
        },
    ).json()

    assert issue["value"] == 35714.0  # cell I15 of the real workbook
    assert issue["previousValue"] == 9709.0
    assert issue["delta"] == 26005.0
    assert issue["deltaPercent"] == pytest.approx(267.8, rel=1e-3)
    assert issue["sourceCell"] == "I15"
    assert issue["sourceRange"] == "B2:I17"
    assert issue["analyticalSeverity"] == "negative"
    assert issue["trend"]["classification"] in ("rising", "falling", "stable", "volatile")


def test_05_06_an_issue_is_bound_to_its_version_and_period(client, version: int) -> None:
    issue = client.post(
        f"/api/versions/{version}/issues",
        json={"table": "TTL", "category": "Total", "metric": "PPM", "period": "Aug"},
    ).json()
    assert issue["period"]["label"] == "Aug"
    assert issue["period"]["quarter"] == "3Q"  # the engine, not the issue layer
    assert issue["referencePeriod"]["label"] == "3Q"

    listed = client.get(f"/api/versions/{version}/issues", params={"period": "Aug"}).json()
    assert any(item["id"] == issue["id"] for item in listed)
    assert client.get(f"/api/versions/{version}/issues", params={"period": "1Q"}).json() == []


def test_an_issue_about_a_reading_that_does_not_exist_is_refused(client, version: int) -> None:
    response = client.post(
        f"/api/versions/{version}/issues",
        json={"table": "TTL", "category": "Nowhere", "metric": "PPM", "period": "Aug"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


# --------------------------------------------------------------------------- #
# 2-3. Editing and status
# --------------------------------------------------------------------------- #
def test_02_the_editorial_half_is_editable(client, version: int) -> None:
    issue = client.post(
        f"/api/versions/{version}/issues",
        json={"table": "TTL", "category": "Local", "metric": "PPM", "period": "Aug"},
    ).json()

    updated = client.patch(
        f"/api/versions/{version}/issues/{issue['id']}",
        json={
            "title": "Local PPM spike under investigation",
            "description": "Supplier audit scheduled.\nContainment in place.",
            "severity": "high",
        },
    ).json()

    assert updated["title"] == "Local PPM spike under investigation"
    assert "Containment in place." in updated["description"]
    assert updated["severity"] == "high"
    # the numbers did not move
    assert updated["value"] == issue["value"] and updated["sourceCell"] == issue["sourceCell"]


def test_02_derived_fields_cannot_be_edited(client, version: int) -> None:
    issue = client.post(
        f"/api/versions/{version}/issues",
        json={"table": "TTL", "category": "Local", "metric": "PPM", "period": "Aug"},
    ).json()
    response = client.patch(
        f"/api/versions/{version}/issues/{issue['id']}", json={"value": 1.0}
    )
    assert response.status_code == 422
    assert "value" in response.json()["detail"]["fields"]


def test_03_status_moves_only_when_a_human_moves_it(client, version: int) -> None:
    issue = client.post(
        f"/api/versions/{version}/issues",
        json={"table": "TTL", "category": "Imported", "metric": "PPM", "period": "Aug"},
    ).json()
    # this reading improved; the issue is still open until someone closes it
    assert issue["analyticalSeverity"] == "positive"
    assert issue["status"] == "open"

    for status in ("in_progress", "resolved", "closed"):
        updated = client.patch(
            f"/api/versions/{version}/issues/{issue['id']}", json={"status": status}
        ).json()
        assert updated["status"] == status

    assert len(client.get(f"/api/versions/{version}/issues", params={"status": "closed"}).json()) >= 1


# --------------------------------------------------------------------------- #
# 7-8. Image and translation key
# --------------------------------------------------------------------------- #
def test_07_an_image_can_be_attached_and_served(client, version: int) -> None:
    issue = client.post(
        f"/api/versions/{version}/issues",
        json={"table": "TTL", "category": "Local", "metric": "PPM", "period": "Aug"},
    ).json()

    with_media = client.post(
        f"/api/versions/{version}/issues/{issue['id']}/media",
        files={"file": ("evidence.png", PNG, "image/png")},
        data={"caption": "Defect close-up"},
    )
    assert with_media.status_code == 201
    media = with_media.json()["media"]
    assert len(media) == 1
    assert media[0]["mimeType"] == "image/png" and media[0]["caption"] == "Defect close-up"

    served = client.get(media[0]["url"])
    assert served.status_code == 200
    assert served.content == PNG  # the bytes live on disk, not in SQLite


def test_07_a_file_that_is_not_an_image_is_refused(client, version: int) -> None:
    issue = client.post(
        f"/api/versions/{version}/issues",
        json={"table": "TTL", "category": "Local", "metric": "PPM", "period": "Aug"},
    ).json()
    response = client.post(
        f"/api/versions/{version}/issues/{issue['id']}/media",
        files={"file": ("evil.png", b"<html>not an image</html>", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "upload_rejected"


def test_08_the_description_carries_a_translation_key(client, version: int) -> None:
    issue = client.post(
        f"/api/versions/{version}/issues",
        json={
            "table": "TTL",
            "category": "Local",
            "metric": "PPM",
            "period": "Aug",
            "description": "Excessive rejection observed on incoming lots.",
        },
    ).json()

    assert issue["translationKey"] and len(issue["translationKey"]) == 64
    assert issue["descriptionDoc"]["type"] == "doc"  # rich document, as designed

    # the key follows the words: editing the text changes it
    edited = client.patch(
        f"/api/versions/{version}/issues/{issue['id']}",
        json={"description": "Rejection rate returned to normal."},
    ).json()
    assert edited["translationKey"] != issue["translationKey"]

    # and the same words give the same key, so a translation is reused
    from app.services.issues import text_to_doc
    from app.services.translation import documents

    assert edited["translationKey"] == documents.content_hash(
        text_to_doc("Rejection rate returned to normal.")
    )


# --------------------------------------------------------------------------- #
# 10. Issue ← insight
# --------------------------------------------------------------------------- #
def test_an_issue_can_record_the_insight_it_came_from(client, version: int) -> None:
    executive = client.get(
        f"/api/versions/{version}/analytics/executive", params={"table": "TTL"}
    ).json()
    insight = executive["insights"][0]

    issue = client.post(
        f"/api/versions/{version}/issues",
        json={
            "table": insight["table"],
            "category": insight["category"],
            "metric": insight["metric"],
            "period": insight["period"]["label"],
            "title": insight["text"][:120],
            "origin": {"kind": insight["kind"], "template": insight["template"], "score": insight["score"]},
        },
    ).json()

    assert issue["origin"]["kind"] == insight["kind"]
    assert issue["origin"]["score"] == insight["score"]
    # the issue proves itself from the model, not from the insight payload
    assert issue["value"] == insight["value"]
    assert issue["sourceCell"] == insight["source"]
