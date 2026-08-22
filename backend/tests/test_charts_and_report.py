"""The department page: three charts, three tables, one hand-written report.

The system renders; it does not calculate.  The user does the arithmetic in
Excel and uploads the result, so every number on a chart must be a number the
file already held, at the cell the chart says it came from (ADR-0036).

The report is the other half: nothing in the system writes it, and the only
thing that ever happens to it automatically is translation.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from app.excel import parse_file
from app.services import charts
from app.services.interpretation import from_normalized

import base64

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


def _tables(path: Path, department: str = "IQC"):
    return [from_normalized(table, department) for table in parse_file(path, department).tables]


def _workbook_numbers(path: Path, sheet_name: str = "IQC") -> dict[str, float]:
    sheet = openpyxl.load_workbook(path, data_only=True)[sheet_name]
    return {
        cell.coordinate: float(cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool)
    }


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def test_one_chart_per_table_in_the_workbook_order(iqc_real: Path) -> None:
    built = charts.build_charts(_tables(iqc_real), department="IQC")
    assert [chart["table"] for chart in built["charts"]] == ["TTL", "SEC", "TNP"]
    assert built["metric"] == "PPM"  # the department's headline metric


def test_the_iqc_bars_are_the_parts_that_add_up_and_they_stack(iqc_real: Path) -> None:
    """IQC declares stacked bars: SKD + CKD + Local, with Total as the line."""
    chart = charts.build_charts(_tables(iqc_real), department="IQC")["charts"][0]

    assert chart["stacked"] is True
    assert [series["label"] for series in chart["bars"]] == ["SKD", "CKD", "Local"]
    assert chart["line"]["label"] == "Total"
    # the whole is the line, never also a bar
    assert all(series["label"] != "Total" for series in chart["bars"])


def test_a_department_that_has_not_declared_stacking_gets_grouped_bars(
    fixture_files,
) -> None:
    """OQC and FIELD are not invented: they keep the neutral default."""
    from app.domain.departments import schema_for

    assert schema_for("IQC").chart_bars == "stacked"
    assert schema_for("OQC").chart_bars == "grouped"
    assert schema_for("FIELD").chart_bars == "grouped"

    tables = [from_normalized(table, None) for table in parse_file(
        fixture_files["iqc_dataset_c.xlsx"]
    ).tables]
    built = charts.build_charts(tables, department=None)
    assert built["charts"][0]["stacked"] is False


def test_the_periods_are_the_file_s_own_columns(iqc_real: Path) -> None:
    chart = charts.build_charts(_tables(iqc_real), department="IQC")["charts"][0]
    assert [period["label"] for period in chart["periods"]] == [
        "'25", "'26", "1Q", "2Q", "3Q", "Aug",
    ]
    for series in chart["bars"] + [chart["line"]]:
        assert [point["period"] for point in series["points"]] == [
            "'25", "'26", "1Q", "2Q", "3Q", "Aug",
        ]


def test_every_plotted_number_comes_from_cells_the_file_holds(iqc_real: Path) -> None:
    """A point is either a cell of the workbook, or a share of three of them.

    The bars of IQC are the total PPM shared out among the parts (ADR-0046), so
    they are not in any single cell — but every figure that produced them is,
    and the point says which.  Nothing is plotted that the file cannot account
    for.
    """
    expected = _workbook_numbers(iqc_real)
    built = charts.build_charts(_tables(iqc_real), department="IQC")

    plotted = shared = 0
    for chart in built["charts"]:
        for series in chart["bars"] + [chart["line"]]:
            for point in series["points"]:
                if point["value"] is None:
                    continue
                plotted += 1
                if point["source"]:
                    assert point["value"] == pytest.approx(expected[point["source"]])
                    continue
                origin = point["derivedFrom"]
                whole = expected[origin["whole"]]
                weight = expected[origin["weight"]]
                weight_total = expected[origin["weightTotal"]]
                assert point["value"] == pytest.approx(
                    whole * weight / weight_total if weight_total else 0.0
                )
                shared += 1
    assert plotted > 0 and shared > 0


def test_the_stack_adds_up_to_the_line_it_sits_under(iqc_real: Path) -> None:
    """The whole point of sharing a rate: the column *is* the total.

    Plotting each part's own PPM built a column many times taller than the
    total drawn over it, which said nothing.  Shared by rejected lots, the
    segments close on the line.
    """
    for chart in charts.build_charts(_tables(iqc_real), department="IQC")["charts"]:
        assert chart["shared"] is True
        assert chart["share"] == {"whole": "PPM", "weight": "Rej. Lot"}
        for index, point in enumerate(chart["line"]["points"]):
            parts = [series["points"][index]["value"] for series in chart["bars"]]
            if point["value"] is None or any(part is None for part in parts):
                continue
            assert sum(parts) == pytest.approx(point["value"])


def test_a_period_with_nothing_rejected_shares_out_as_zero(iqc_real: Path) -> None:
    """TNP in August: no rejected lots at all, so no part carries any of it."""
    chart = next(
        chart
        for chart in charts.build_charts(_tables(iqc_real), department="IQC")["charts"]
        if chart["table"] == "TNP"
    )
    august = chart["periods"].index(
        next(period for period in chart["periods"] if period["label"] == "Aug")
    )
    assert chart["line"]["points"][august]["value"] == 0
    assert [series["points"][august]["value"] for series in chart["bars"]] == [0.0, 0.0, 0.0]


def test_a_missing_reading_is_a_gap_never_a_zero(iqc_evolution) -> None:
    built = charts.build_charts(_tables(iqc_evolution["a"]), department="IQC")
    for chart in built["charts"]:
        for series in chart["bars"] + ([chart["line"]] if chart["line"] else []):
            for point in series["points"]:
                assert point["value"] is None or isinstance(point["value"], float)


def test_the_charts_are_deterministic(iqc_real: Path) -> None:
    tables = _tables(iqc_real)
    assert charts.build_charts(tables, department="IQC") == charts.build_charts(
        tables, department="IQC"
    )


def test_the_metric_comes_from_the_file_even_without_a_department(fixture_files) -> None:
    """With no schema to declare a headline metric, the file decides."""
    path = fixture_files["iqc_dataset_c.xlsx"]
    tables = [from_normalized(table, None) for table in parse_file(path).tables]
    built = charts.build_charts(tables, department=None)

    present = [row.metric for table in tables for row in table.rows if row.metric]
    assert built["metric"] == present[0], "the first metric the file carries"
    assert built["charts"]


def test_a_workbook_with_no_metric_is_charted_by_its_series(fixture_files) -> None:
    """FIELD measures nothing it calls a metric: it sets a target and meets it.

    So its chart is a pair — the result as bars, the target as the line — and
    the headline metric stays ``None`` rather than being invented.
    """
    tables = [
        from_normalized(table, "FIELD")
        for table in parse_file(fixture_files["field_asr_casr.xlsx"], "FIELD").tables
    ]
    built = charts.build_charts(tables, department="FIELD")

    assert built["metric"] is None
    assert built["charts"], "a target and a result are enough to draw"
    for chart in built["charts"]:
        assert chart["kind"] == "pair"
        assert [series["label"] for series in chart["bars"]] == ["Result"]
        assert chart["line"]["label"] == "Target"


def test_the_charts_endpoint_serves_the_same_thing(client, iqc_real: Path) -> None:
    created = _upload(client, iqc_real)
    body = client.get(f"/api/versions/{created['versionId']}/charts").json()

    assert body["metric"] == "PPM"
    assert [chart["table"] for chart in body["charts"]] == ["TTL", "SEC", "TNP"]
    chart = body["charts"][0]
    assert chart["stacked"] is True
    assert chart["line"]["label"] == "Total"
    assert [series["label"] for series in chart["bars"]] == ["SKD", "CKD", "Local"]
    assert chart["sourceRange"] == "B2:I17"


# --------------------------------------------------------------------------- #
# The report — a table the author builds
# --------------------------------------------------------------------------- #
def _report(client, version_id: int, **overrides):
    content = {
        "title": "Relatório semanal",
        "columns": [{"id": "c1", "name": "Item"}, {"id": "c2", "name": "Evidência"}],
        "rows": [
            {
                "id": "r1",
                "cells": {
                    "c1": [
                        {"id": "b1", "type": "text", "text": "Fornecedor Local",
                         "align": "center", "bold": True, "size": "large"},
                        {"id": "b2", "type": "shape", "shape": "divider", "color": "#B3382F"},
                        {"id": "b3", "type": "text", "text": "Contenção aplicada."},
                    ],
                    "c2": [],
                },
            }
        ],
    }
    content.update(overrides)
    return client.put(f"/api/versions/{version_id}/report", json={"content": content}).json()


def test_a_new_snapshot_has_no_report(client, iqc_real: Path) -> None:
    """Nothing is written on the author's behalf."""
    created = _upload(client, iqc_real)
    body = client.get(f"/api/versions/{created['versionId']}/report").json()
    assert body["content"]["title"] == ""
    assert body["content"]["columns"] == [] and body["content"]["rows"] == []


def test_the_author_builds_columns_rows_and_blocks(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    saved = _report(client, version_id)

    assert saved["content"]["title"] == "Relatório semanal"
    assert [column["name"] for column in saved["content"]["columns"]] == ["Item", "Evidência"]
    cell = saved["content"]["rows"][0]["cells"]["c1"]
    # the order the author placed them in is the order that comes back
    assert [block["type"] for block in cell] == ["text", "shape", "text"]
    assert cell[0]["align"] == "center" and cell[0]["bold"] is True
    assert cell[0]["size"] == "large"


def test_a_cell_can_mix_text_images_and_shapes_in_any_order(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    uploaded = client.post(
        f"/api/versions/{version_id}/report/media",
        files={"file": ("evidence.png", PNG, "image/png")},
    ).json()

    saved = _report(
        client,
        version_id,
        rows=[
            {
                "id": "r1",
                "cells": {
                    "c1": [
                        {"id": "a", "type": "image", "assetId": uploaded["assetId"],
                         "caption": "antes", "align": "center", "width": 60},
                        {"id": "b", "type": "image", "assetId": uploaded["assetId"],
                         "caption": "depois"},
                        {"id": "c", "type": "text", "text": "Comparação", "align": "right"},
                    ]
                },
            }
        ],
    )
    blocks = saved["content"]["rows"][0]["cells"]["c1"]
    assert [block["type"] for block in blocks] == ["image", "image", "text"]
    assert blocks[0]["url"] == uploaded["url"] and blocks[0]["width"] == 60
    assert blocks[2]["align"] == "right"


def test_as_many_rows_as_the_author_wants(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    rows = [
        {"id": f"r{index}", "cells": {"c1": [{"id": f"t{index}", "type": "text",
                                              "text": f"linha {index}"}]}}
        for index in range(40)
    ]
    saved = _report(client, version_id, rows=rows)
    assert len(saved["content"]["rows"]) == 40


def test_a_block_the_system_cannot_draw_is_refused(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    saved = _report(
        client,
        version_id,
        rows=[{"id": "r1", "cells": {"c1": [
            {"id": "x", "type": "video", "url": "http://example.com"},
            {"id": "y", "type": "text", "text": "kept"},
        ]}}],
    )
    blocks = saved["content"]["rows"][0]["cells"]["c1"]
    assert [block["type"] for block in blocks] == ["text"]


def test_a_cell_of_a_deleted_column_goes_with_it(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    saved = _report(
        client,
        version_id,
        columns=[{"id": "c1", "name": "Item"}],  # c2 removed
    )
    assert list(saved["content"]["rows"][0]["cells"]) == ["c1"]


def test_saving_again_replaces_the_report(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    _report(client, version_id)
    again = _report(client, version_id, title="Outro título")
    assert again["content"]["title"] == "Outro título"


def test_the_report_belongs_to_one_snapshot(client, iqc_real: Path, iqc_evolution) -> None:
    first = _upload(client, iqc_real)["versionId"]
    second = _upload(client, iqc_evolution["c"])["versionId"]
    _report(client, first)

    assert client.get(f"/api/versions/{second}/report").json()["content"]["rows"] == []
    assert client.get(f"/api/versions/{first}/report").json()["content"]["title"]


def test_an_image_is_uploaded_and_served(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    uploaded = client.post(
        f"/api/versions/{version_id}/report/media",
        files={"file": ("evidence.png", PNG, "image/png")},
    ).json()

    assert uploaded["mimeType"] == "image/png"
    served = client.get(uploaded["url"])
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")


def test_the_report_never_touches_the_snapshot(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    before = client.get(f"/api/versions/{version_id}/view").json()

    _report(client, version_id)

    assert client.get(f"/api/versions/{version_id}/view").json() == before


# --------------------------------------------------------------------------- #
# The reports library
# --------------------------------------------------------------------------- #
def test_saved_reports_are_listed_for_download(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    _report(client, version_id)

    listed = client.get("/api/reports").json()
    mine = next(item for item in listed if item["versionId"] == version_id)
    assert mine["department"] == "IQC"
    assert mine["title"] == "Relatório semanal"
    assert mine["columnCount"] == 2 and mine["rowCount"] == 1
    assert mine["versionNumber"] and mine["updatedAt"]


def test_the_library_filters_by_department(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    _report(client, version_id)

    assert client.get("/api/reports", params={"department": "IQC"}).json()
    assert client.get("/api/reports", params={"department": "OQC"}).json() == []


# --------------------------------------------------------------------------- #
# Settings — one per department, the same everywhere
# --------------------------------------------------------------------------- #
def test_every_department_has_its_own_settings(client) -> None:
    for code in ("IQC", "OQC", "FIELD"):
        body = client.get(f"/api/departments/{code}/settings").json()
        assert body["department"] == code
        assert body["chartTitles"] == {} and body["tableTitles"] == {}


def test_titles_are_saved_and_used_by_the_charts(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    client.put(
        "/api/departments/IQC/settings",
        json={"chartTitles": {"TTL": "Total incoming"}, "tableTitles": {"TTL": "Resumo"}},
    )

    body = client.get(f"/api/versions/{version_id}/charts").json()
    assert body["charts"][0]["title"] == "Total incoming"
    assert body["charts"][0]["table"] == "TTL"  # the workbook's own name is kept
    saved = client.get("/api/departments/IQC/settings").json()
    assert saved["tableTitles"] == {"TTL": "Resumo"}


def test_an_unknown_department_is_a_404(client) -> None:
    assert client.get("/api/departments/NOPE/settings").status_code == 404


def test_a_large_image_is_refused_with_the_limit_in_the_message(client, iqc_real: Path) -> None:
    """Large photos are welcome; a file above the ceiling is not, and says so."""
    from app.core.config import get_settings

    version_id = _upload(client, iqc_real)["versionId"]
    limit = get_settings().max_image_mb * 1024 * 1024
    oversized = PNG + b"\x00" * (limit + 1)

    response = client.post(
        f"/api/versions/{version_id}/report/media",
        files={"file": ("huge.png", oversized, "image/png")},
    )
    assert response.status_code == 413 or response.status_code >= 400
    body = response.json()
    assert str(get_settings().max_image_mb) in body["message"]
    assert body["detail"]["limitMb"] == get_settings().max_image_mb


def test_an_image_is_stored_byte_for_byte(client, iqc_real: Path) -> None:
    """Nothing is re-encoded, so nothing loses quality."""
    version_id = _upload(client, iqc_real)["versionId"]
    uploaded = client.post(
        f"/api/versions/{version_id}/report/media",
        files={"file": ("evidence.png", PNG, "image/png")},
    ).json()

    assert uploaded["sizeBytes"] == len(PNG)
    served = client.get(uploaded["url"])
    assert served.content == PNG


# --------------------------------------------------------------------------- #
# The presenter composes the chart (ADR-0041)
# --------------------------------------------------------------------------- #
def _options(client, version_id: int, table: str = "TTL") -> dict[str, str]:
    body = client.get(f"/api/versions/{version_id}/charts").json()
    chart = next(item for item in body["charts"] if item["table"] == table)
    return {option["path"]: option["key"] for option in chart["available"]}


def test_every_row_of_the_table_is_offered(client, iqc_real: Path) -> None:
    """The chooser picks from what the workbook has, never from an invented list."""
    version_id = _upload(client, iqc_real)["versionId"]
    options = _options(client, version_id)

    assert "Total · PPM" in options
    assert "Imported · SKD · PPM" in options
    assert "Local · Insp. Lot" in options  # other metrics are offered too
    assert all(key.startswith("TTL|") for key in options.values())


def test_the_chosen_rows_are_the_ones_plotted(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    options = _options(client, version_id)

    client.put(
        "/api/departments/IQC/settings",
        json={
            "chartSeries": {
                "TTL": {
                    "bars": [options["Imported · PPM"], options["Local · PPM"]],
                    "line": options["Total · PPM"],
                }
            }
        },
    )

    chart = client.get(f"/api/versions/{version_id}/charts").json()["charts"][0]
    assert chart["configured"] is True
    assert [series["label"] for series in chart["bars"]] == ["Imported", "Local"]
    assert chart["line"]["label"] == "Total"
    assert chart["stacked"] is True  # IQC still stacks what it is given


def test_a_composition_may_mix_metrics_and_says_which_is_which(
    client, iqc_real: Path
) -> None:
    """Bars in lots, line in PPM: the labels carry the metric or they read alike."""
    version_id = _upload(client, iqc_real)["versionId"]
    options = _options(client, version_id)

    client.put(
        "/api/departments/IQC/settings",
        json={
            "chartSeries": {
                "TTL": {
                    "bars": [options["Imported · Rej. Lot"], options["Local · Rej. Lot"]],
                    "line": options["Total · PPM"],
                }
            }
        },
    )

    chart = client.get(f"/api/versions/{version_id}/charts").json()["charts"][0]
    assert [series["label"] for series in chart["bars"]] == [
        "Imported · Rej. Lot",
        "Local · Rej. Lot",
    ]
    assert chart["line"]["label"] == "Total · PPM"


def test_the_plotted_values_are_still_the_workbook_s(client, iqc_real: Path) -> None:
    """Choosing what to draw never changes what it says.

    A chosen bar is shared out exactly like a default one — the presenter picks
    which rows are drawn, never what they are worth — and the line is a cell of
    the file, untouched.
    """
    version_id = _upload(client, iqc_real)["versionId"]
    options = _options(client, version_id)
    client.put(
        "/api/departments/IQC/settings",
        json={"chartSeries": {"TTL": {"bars": [options["Imported · SKD · PPM"]]}}},
    )

    chart = client.get(f"/api/versions/{version_id}/charts").json()["charts"][0]
    expected = _workbook_numbers(iqc_real)
    for point in chart["bars"][0]["points"]:
        if point["value"] is None:
            continue
        origin = point["derivedFrom"]
        weight_total = expected[origin["weightTotal"]]
        assert point["value"] == pytest.approx(
            expected[origin["whole"]] * expected[origin["weight"]] / weight_total
            if weight_total
            else 0.0
        )
    # the table next to it was not configured, and its line is a cell of the
    # file, read straight off the workbook
    untouched = client.get(f"/api/versions/{version_id}/charts").json()["charts"][1]
    for point in untouched["line"]["points"]:
        if point["value"] is not None:
            assert point["value"] == pytest.approx(expected[point["source"]])


def test_a_stale_choice_falls_back_instead_of_drawing_nothing(
    client, iqc_real: Path
) -> None:
    """A row the workbook no longer has must not leave an empty chart."""
    version_id = _upload(client, iqc_real)["versionId"]
    client.put(
        "/api/departments/IQC/settings",
        json={"chartSeries": {"TTL": {"bars": ["TTL|Gone||PPM|"], "line": "TTL|Gone||PPM|"}}},
    )

    chart = client.get(f"/api/versions/{version_id}/charts").json()["charts"][0]
    assert chart["configured"] is False
    assert [series["label"] for series in chart["bars"]] == ["SKD", "CKD", "Local"]


def test_only_the_table_that_was_configured_changes(client, iqc_real: Path) -> None:
    version_id = _upload(client, iqc_real)["versionId"]
    options = _options(client, version_id)
    client.put(
        "/api/departments/IQC/settings",
        json={"chartSeries": {"TTL": {"bars": [options["Local · PPM"]]}}},
    )

    charts_out = client.get(f"/api/versions/{version_id}/charts").json()["charts"]
    assert charts_out[0]["configured"] is True
    assert charts_out[1]["configured"] is False  # SEC keeps the default
    assert [s["label"] for s in charts_out[1]["bars"]] == ["SKD", "CKD", "Local"]


def test_the_library_renders_titles_and_terms_for_the_reader(
    client, iqc_real: Path, monkeypatch
) -> None:
    """A report title is authored text; the period beside it is a decided term."""
    from app.services.translation.provider import (
        TranslationRequest,
        TranslationResult,
        register_provider,
    )

    class Prefixing:
        name = "library-fake"
        requests_per_minute = 0
        max_batch = 50

        def __init__(self) -> None:
            self.calls = 0

        def translate(self, request: TranslationRequest) -> TranslationResult:
            self.calls += 1
            return TranslationResult(
                segments=[f"[ko] {segment}" for segment in request.segments],
                provider=self.name,
                model="fake",
            )

    provider = Prefixing()
    register_provider(provider)
    monkeypatch.setattr(
        "app.services.translation.service.get_provider", lambda name=None: provider
    )

    version_id = _upload(client, iqc_real)["versionId"]
    client.put(
        f"/api/versions/{version_id}/report",
        json={"content": {"title": "Analise semanal - IQC", "columns": [], "rows": []},
              "language": "pt-BR"},
    )

    listed = client.get("/api/reports", params={"language": "ko"}).json()
    mine = next(item for item in listed if item["versionId"] == version_id)

    # authored words through the engine, the department through the glossary:
    # the acronym is masked during translation, so putting the agreed Korean in
    # its place afterwards is a substitution, not a guess
    assert mine["title"] == "[ko] Analise semanal - 부품품질"
    assert mine["versionLabel"] == "8월"              # decided: through the glossary
    assert provider.calls == 1, "every title in one request, not one each"


def test_the_library_in_the_report_s_own_language_asks_nothing(
    client, iqc_real: Path, monkeypatch
) -> None:
    from app.services.translation.provider import TranslationResult, register_provider

    class Counting:
        name = "counting-fake"
        requests_per_minute = 0
        max_batch = 50

        def __init__(self) -> None:
            self.calls = 0

        def translate(self, request):
            self.calls += 1
            return TranslationResult(segments=list(request.segments), provider=self.name)

    provider = Counting()
    register_provider(provider)
    monkeypatch.setattr(
        "app.services.translation.service.get_provider", lambda name=None: provider
    )

    version_id = _upload(client, iqc_real)["versionId"]
    client.put(
        f"/api/versions/{version_id}/report",
        json={"content": {"title": "Analise semanal", "columns": [], "rows": []},
              "language": "pt-BR"},
    )

    listed = client.get("/api/reports", params={"language": "pt-BR"}).json()
    assert next(item for item in listed if item["versionId"] == version_id)["title"] == "Analise semanal"
    assert provider.calls == 0
