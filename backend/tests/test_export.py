"""Export validation: the file exists, opens, and says what the page said."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from pypdf import PdfReader
from pptx import Presentation

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


def _pdf_text(content: bytes, tmp_path: Path) -> tuple[int, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "export.pdf"
    path.write_bytes(content)
    reader = PdfReader(str(path))
    return len(reader.pages), "\n".join(page.extract_text() or "" for page in reader.pages)


def _deck(content: bytes, tmp_path: Path) -> Presentation:
    path = tmp_path / "export.pptx"
    path.write_bytes(content)
    return Presentation(str(path))


def _deck_text(deck: Presentation) -> str:
    return "\n".join(
        shape.text_frame.text
        for slide in deck.slides
        for shape in slide.shapes
        if shape.has_text_frame
    )


# --------------------------------------------------------------------------- #
# 20, 22-24, 27. PDF
# --------------------------------------------------------------------------- #
def test_20_the_pdf_is_generated_and_opens(client, iqc_real: Path, tmp_path: Path) -> None:
    version = _upload(client, iqc_real)["versionId"]
    response = client.post(f"/api/versions/{version}/export/pdf", json={"table": "TTL"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 0

    pages, text = _pdf_text(response.content, tmp_path)
    assert pages >= 3
    assert "IQC" in text
    assert "Key indicators" in text and "Executive insights" in text


def test_22_23_the_pdf_states_the_version_and_the_period(
    client, iqc_real: Path, tmp_path: Path
) -> None:
    created = _upload(client, iqc_real)
    response = client.post(
        f"/api/versions/{created['versionId']}/export/pdf",
        json={"table": "TTL", "period": "Aug", "metric": "PPM"},
    )
    _pages, text = _pdf_text(response.content, tmp_path)

    assert f"Version {created['versionNumber']}" in text
    assert "Period Aug" in text
    assert "Metric PPM" in text
    assert "IQC" in text


def test_23_a_different_period_produces_a_different_export(
    client, iqc_evolution, tmp_path: Path
) -> None:
    version = _upload(client, iqc_evolution["c"])["versionId"]

    august = client.post(
        f"/api/versions/{version}/export/pdf", json={"table": "TTL", "period": "Aug"}
    )
    october = client.post(
        f"/api/versions/{version}/export/pdf", json={"table": "TTL", "period": "Oct"}
    )

    _pages, august_text = _pdf_text(august.content, tmp_path / "a")
    _pages, october_text = _pdf_text(october.content, tmp_path / "b")

    assert "Period Aug" in august_text and "Period Oct" not in august_text
    assert "Period Oct" in october_text


def test_24_27_the_pdf_carries_the_chart_and_the_tables(
    client, iqc_real: Path, tmp_path: Path
) -> None:
    version = _upload(client, iqc_real)["versionId"]
    response = client.post(f"/api/versions/{version}/export/pdf", json={"table": "TTL"})
    _pages, text = _pdf_text(response.content, tmp_path)

    assert "Trend" in text  # the chart block
    for probe in ("TTL", "SEC", "TNP", "Imported", "Local", "SKD", "CKD", "Rej. Lot", "Insp. Lot"):
        assert probe in text, f"{probe} must reach the PDF"
    # the tables keep their structure: no artificial PPM row label
    assert "\nPPM\n" not in text


def test_25_26_issues_and_their_images_reach_the_pdf(
    client, iqc_real: Path, tmp_path: Path
) -> None:
    version = _upload(client, iqc_real)["versionId"]
    issue = client.post(
        f"/api/versions/{version}/issues",
        json={
            "table": "TTL",
            "category": "Local",
            "metric": "PPM",
            "period": "Aug",
            "title": "Local PPM spike",
            "description": "Containment in place at the supplier.",
        },
    ).json()
    client.post(
        f"/api/versions/{version}/issues/{issue['id']}/media",
        files={"file": ("evidence.png", PNG, "image/png")},
        data={"caption": "Defect close-up"},
    )

    response = client.post(f"/api/versions/{version}/export/pdf", json={"table": "TTL"})
    pages, text = _pdf_text(response.content, tmp_path)

    assert "Issue reports" in text
    assert "Local PPM spike" in text
    assert "Containment in place at the supplier." in text
    assert "Defect close-up" in text  # the caption travelled with the image

    reader = PdfReader(str(tmp_path / "export.pdf"))
    images = sum(len(page.images) for page in reader.pages)
    assert images >= 1, "the attached evidence must be embedded"
    assert pages >= 3


# --------------------------------------------------------------------------- #
# 21-27. PowerPoint
# --------------------------------------------------------------------------- #
def test_21_the_deck_is_generated_and_opens(client, iqc_real: Path, tmp_path: Path) -> None:
    version = _upload(client, iqc_real)["versionId"]
    response = client.post(f"/api/versions/{version}/export/ppt", json={"table": "TTL"})

    assert response.status_code == 200
    assert "presentationml" in response.headers["content-type"]
    deck = _deck(response.content, tmp_path)
    assert len(deck.slides) >= 5


def test_22_23_the_deck_states_department_version_and_period(
    client, iqc_real: Path, tmp_path: Path
) -> None:
    created = _upload(client, iqc_real)
    response = client.post(
        f"/api/versions/{created['versionId']}/export/ppt",
        json={"table": "TTL", "period": "Aug"},
    )
    text = _deck_text(_deck(response.content, tmp_path))

    assert "IQC — Executive overview" in text
    assert "Period Aug" in text
    assert f"Version {created['versionNumber']}" in text


def test_24_the_deck_chart_is_a_real_chart(client, iqc_real: Path, tmp_path: Path) -> None:
    version = _upload(client, iqc_real)["versionId"]
    response = client.post(f"/api/versions/{version}/export/ppt", json={"table": "TTL"})
    deck = _deck(response.content, tmp_path)

    charts = [shape for slide in deck.slides for shape in slide.shapes if shape.has_chart]
    assert charts, "the chart must be a native, editable object"
    plot = charts[0].chart.plots[0]
    assert list(plot.categories) == ["'25", "'26", "1Q", "2Q", "3Q", "Aug"]
    assert len(plot.series) >= 1


def test_27_the_deck_tables_keep_their_structure(client, iqc_real: Path, tmp_path: Path) -> None:
    version = _upload(client, iqc_real)["versionId"]
    response = client.post(f"/api/versions/{version}/export/ppt", json={"table": "TTL"})
    deck = _deck(response.content, tmp_path)

    tables = [shape for slide in deck.slides for shape in slide.shapes if shape.has_table]
    assert len(tables) == 3  # TTL, SEC, TNP

    grid = tables[0].table
    texts = [cell.text for row in grid.rows for cell in row.cells]
    assert "TTL" in texts and "Imported" in texts and "Rej. Lot" in texts
    assert "PPM" not in texts  # the headline row keeps its empty label cell
    # a merged cell is one cell in the deck too
    merged = [cell for row in grid.rows for cell in row.cells if cell.is_merge_origin]
    assert merged


def test_25_26_issues_and_images_reach_the_deck(client, iqc_real: Path, tmp_path: Path) -> None:
    version = _upload(client, iqc_real)["versionId"]
    issue = client.post(
        f"/api/versions/{version}/issues",
        json={
            "table": "TTL",
            "category": "Local",
            "metric": "PPM",
            "period": "Aug",
            "title": "Local PPM spike",
            "description": "Supplier audit scheduled.",
        },
    ).json()
    client.post(
        f"/api/versions/{version}/issues/{issue['id']}/media",
        files={"file": ("evidence.png", PNG, "image/png")},
    )

    response = client.post(f"/api/versions/{version}/export/ppt", json={"table": "TTL"})
    deck = _deck(response.content, tmp_path)
    text = _deck_text(deck)

    assert "Local PPM spike" in text and "Supplier audit scheduled." in text
    pictures = [
        shape for slide in deck.slides for shape in slide.shapes if shape.shape_type == 13
    ]
    assert pictures, "the evidence image must be embedded in the deck"


def test_the_export_can_include_a_version_comparison(client, iqc_evolution, tmp_path: Path) -> None:
    first = _upload(client, iqc_evolution["a"])
    second = _upload(client, iqc_evolution["b"])

    response = client.post(
        f"/api/versions/{second['versionId']}/export/pdf",
        json={"table": "TTL", "period": "Aug", "compareWith": first["versionId"]},
    )
    _pages, text = _pdf_text(response.content, tmp_path)
    assert "Version comparison" in text


def test_exporting_twice_does_not_reuse_a_stale_file(client, iqc_evolution, tmp_path: Path) -> None:
    version = _upload(client, iqc_evolution["c"])["versionId"]
    first = client.post(
        f"/api/versions/{version}/export/pdf", json={"table": "TTL", "period": "Aug"}
    ).content
    second = client.post(
        f"/api/versions/{version}/export/pdf", json={"table": "TTL", "period": "Sep"}
    ).content
    assert first != second

    _pages, first_text = _pdf_text(first, tmp_path / "one")
    _pages, second_text = _pdf_text(second, tmp_path / "two")
    assert "Period Aug" in first_text and "Period Sep" in second_text
