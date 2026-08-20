"""PDF export — the executive page, laid out for paper.

Structured, not screenshotted: text stays text, tables stay tables and the
chart is drawn natively, so the file is searchable and prints cleanly.

The IQC tables keep their structure — merges become spans, the empty cell of a
headline row stays empty — because only the *representation* may be adapted to
the medium, never the model (Sprint 5 §26).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .context import ExportContext

logger = logging.getLogger(__name__)

BRAND = colors.HexColor("#1E3A5F")
BRAND_LIGHT = colors.HexColor("#E2ECF8")
INK = colors.HexColor("#14202E")
MUTED = colors.HexColor("#6B7D94")
LINE = colors.HexColor("#B7C4D6")
POSITIVE = colors.HexColor("#1D7A5F")
NEGATIVE = colors.HexColor("#B3382F")

SEVERITY_COLOR = {
    "positive": POSITIVE,
    "negative": NEGATIVE,
    "neutral": MUTED,
    "unknown": MUTED,
    "high": NEGATIVE,
    "medium": colors.HexColor("#B5761F"),
    "low": MUTED,
    "info": MUTED,
}

PAGE = landscape(A4)
CONTENT_WIDTH = PAGE[0] - 30 * mm


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], textColor=BRAND, fontSize=20, alignment=TA_LEFT
        ),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], textColor=MUTED, fontSize=10),
        "heading": ParagraphStyle(
            "heading", parent=base["Heading2"], textColor=BRAND, fontSize=13, spaceBefore=10
        ),
        "body": ParagraphStyle("body", parent=base["Normal"], textColor=INK, fontSize=9.5, leading=13),
        "small": ParagraphStyle("small", parent=base["Normal"], textColor=MUTED, fontSize=7.5),
        "kpi_label": ParagraphStyle("kpi_label", parent=base["Normal"], textColor=MUTED, fontSize=8),
        "kpi_value": ParagraphStyle(
            "kpi_value", parent=base["Normal"], textColor=BRAND, fontSize=17, leading=20
        ),
    }


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #
def _header(context: ExportContext, styles: dict[str, ParagraphStyle]) -> list[Any]:
    meta = " · ".join(
        part
        for part in (
            f"Version {context.version_number}" if context.version_number else None,
            f"Period {(context.period or {}).get('label')}" if context.period else None,
            f"Metric {context.metric}" if context.metric else None,
            f"Table {context.table}" if context.table else None,
            context.raw_file,
        )
        if part
    )
    return [
        Paragraph(context.title, styles["title"]),
        Paragraph(meta, styles["subtitle"]),
        Paragraph(
            f"Generated {context.generated_at.strftime('%Y-%m-%d %H:%M UTC')}", styles["small"]
        ),
        Spacer(1, 6 * mm),
    ]


def _kpi_block(context: ExportContext, styles: dict[str, ParagraphStyle]) -> list[Any]:
    if not context.kpis:
        return []
    cells = []
    for kpi in context.kpis:
        delta = ""
        if kpi.get("delta") is not None:
            percent = (
                f" ({kpi['deltaPercent']:+.1f}%)" if kpi.get("deltaPercent") is not None else ""
            )
            reference = (kpi.get("previousPeriod") or {}).get("label") or "—"
            delta = f"{kpi['delta']:+,.0f}{percent} vs {reference}"
        target = (
            f"Target {kpi['targetDisplay']} · {kpi['targetStatus']}"
            if kpi.get("target") is not None
            else ""
        )
        cells.append(
            [
                Paragraph(kpi["label"], styles["kpi_label"]),
                Paragraph(kpi.get("display") or "—", styles["kpi_value"]),
                Paragraph(delta, styles["small"]),
                Paragraph(target or (kpi.get("sourceRange") or ""), styles["small"]),
            ]
        )

    columns = [cells[index : index + 3] for index in range(0, len(cells), 3)]
    blocks: list[Any] = [Paragraph("Key indicators", styles["heading"])]
    for row in columns:
        while len(row) < 3:
            row.append([Paragraph("", styles["small"])])
        table = Table(
            [[Table([[part] for part in cell], colWidths=[CONTENT_WIDTH / 3 - 6 * mm]) for cell in row]],
            colWidths=[CONTENT_WIDTH / 3] * 3,
        )
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        blocks.append(table)
        blocks.append(Spacer(1, 3 * mm))
    return blocks


def _insight_block(context: ExportContext, styles: dict[str, ParagraphStyle]) -> list[Any]:
    if not context.insights:
        return []
    rows = []
    for insight in context.insights:
        marker = Paragraph(
            f'<font color="{SEVERITY_COLOR.get(insight.get("severity"), MUTED).hexval()}">■</font>',
            styles["body"],
        )
        origin = " · ".join(
            part
            for part in (
                insight.get("table"),
                insight.get("category"),
                insight.get("metric"),
                (insight.get("period") or {}).get("label"),
                insight.get("source"),
            )
            if part
        )
        rows.append(
            [
                marker,
                [
                    Paragraph(insight["text"], styles["body"]),
                    Paragraph(origin, styles["small"]),
                ],
            ]
        )
    table = Table(rows, colWidths=[8 * mm, CONTENT_WIDTH - 8 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
            ]
        )
    )
    return [Paragraph("Executive insights", styles["heading"]), table, Spacer(1, 4 * mm)]


def _issue_block(context: ExportContext, styles: dict[str, ParagraphStyle]) -> list[Any]:
    if not context.issues:
        return []
    blocks: list[Any] = [Paragraph("Issue reports", styles["heading"])]
    for issue in context.issues:
        meta = " · ".join(
            part
            for part in (
                issue.get("table"),
                issue.get("category"),
                issue.get("metric"),
                issue.get("period"),
                f"status {issue['status']}",
                f"severity {issue['severity']}",
                issue.get("sourceRange"),
            )
            if part
        )
        numbers = ""
        if issue.get("value") is not None:
            numbers = f"{issue['value']:,.0f}"
            if issue.get("previousValue") is not None:
                numbers += f" (from {issue['previousValue']:,.0f}"
                if issue.get("deltaPercent") is not None:
                    numbers += f", {issue['deltaPercent']:+.1f}%"
                numbers += ")"

        parts: list[Any] = [
            Paragraph(f"<b>{issue['title']}</b>", styles["body"]),
            Paragraph(meta, styles["small"]),
        ]
        if numbers:
            parts.append(Paragraph(numbers, styles["body"]))
        if issue.get("description"):
            parts.append(Paragraph(issue["description"].replace("\n", "<br/>"), styles["body"]))
        for image in issue.get("images", []):
            try:
                parts.append(Spacer(1, 2 * mm))
                parts.append(Image(image["path"], width=90 * mm, height=55 * mm, kind="proportional"))
                if image.get("caption"):
                    parts.append(Paragraph(image["caption"], styles["small"]))
            except Exception:  # pragma: no cover - a broken image must not kill the export
                logger.warning("could not embed image %s", image.get("path"))
        parts.append(Spacer(1, 4 * mm))
        blocks.append(KeepTogether(parts))
    return blocks


def _chart_block(context: ExportContext, styles: dict[str, ParagraphStyle]) -> list[Any]:
    series = [item for item in context.series if any(p["value"] is not None for p in item["points"])]
    if not series or not context.periods:
        return []

    labels = [period["label"] for period in context.periods]
    drawing = Drawing(CONTENT_WIDTH, 90 * mm)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 30
    chart.width = CONTENT_WIDTH - 70
    chart.height = 90 * mm - 60
    chart.data = [
        [
            next(
                (
                    point["value"]
                    for point in item["points"]
                    if point["period"]["label"] == label
                ),
                None,
            )
            for label in labels
        ]
        for item in series[:5]
    ]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontSize = 7
    chart.barSpacing = 1
    palette = [BRAND, colors.HexColor("#3A6499"), colors.HexColor("#6A8FBE"),
               colors.HexColor("#9DBADD"), colors.HexColor("#C7D9EF")]
    for index, _ in enumerate(chart.data):
        chart.bars[index].fillColor = palette[index % len(palette)]
    drawing.add(chart)

    legend_y = 8
    for index, item in enumerate(series[:5]):
        drawing.add(
            String(
                40 + index * (CONTENT_WIDTH / 5),
                legend_y,
                item["label"][:34],
                fontSize=7,
                fillColor=palette[index % len(palette)],
            )
        )

    heading = f"{context.table or ''} · {context.metric or ''}".strip(" ·")
    return [
        Paragraph(f"Trend — {heading}" if heading else "Trend", styles["heading"]),
        drawing,
        Spacer(1, 4 * mm),
    ]


def _table_blocks(context: ExportContext, styles: dict[str, ParagraphStyle]) -> list[Any]:
    blocks: list[Any] = []
    for view in context.tables:
        rows, spans = _grid(view, styles)
        if not rows:
            continue
        column_count = view["columnCount"]
        label_columns = view["labelColumnCount"]
        label_width = 26 * mm
        value_width = max(
            (CONTENT_WIDTH - label_width * label_columns) / max(column_count - label_columns, 1),
            14 * mm,
        )
        widths = [label_width] * label_columns + [value_width] * (column_count - label_columns)

        table = Table(rows, colWidths=widths, repeatRows=view["headerRowCount"])
        style = [
            ("GRID", (0, 0), (-1, -1), 0.3, LINE),
            ("BACKGROUND", (0, 0), (-1, view["headerRowCount"] - 1), BRAND_LIGHT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
        style.extend(spans)
        table.setStyle(TableStyle(style))
        blocks.append(
            KeepTogether(
                [
                    Paragraph(
                        f"{view['title'] or view['sheet']} · {view['sheet']}!{view['sourceRange']}",
                        styles["heading"],
                    ),
                    table,
                    Spacer(1, 5 * mm),
                ]
            )
        )
    return blocks


def _grid(view: dict[str, Any], styles: dict[str, ParagraphStyle]) -> tuple[list[list[Any]], list[Any]]:
    """The render model, turned into a ReportLab grid with its spans."""
    rows: list[list[Any]] = [
        ["" for _ in range(view["columnCount"])] for _ in range(view["rowCount"])
    ]
    spans: list[Any] = []
    for row in view["rows"]:
        for cell in row["cells"]:
            text = cell["text"] or (cell["inferredText"] or "")
            rows[cell["row"]][cell["col"]] = Paragraph(
                f"<b>{text}</b>" if cell["bold"] or cell["isHeadline"] else text,
                styles["small"] if cell["kind"] == "value" else styles["small"],
            )
            if cell["rowSpan"] > 1 or cell["colSpan"] > 1:
                spans.append(
                    (
                        "SPAN",
                        (cell["col"], cell["row"]),
                        (cell["col"] + cell["colSpan"] - 1, cell["row"] + cell["rowSpan"] - 1),
                    )
                )
    return rows, spans


def _comparison_block(context: ExportContext, styles: dict[str, ParagraphStyle]) -> list[Any]:
    comparison = context.comparison
    if not comparison or not comparison.get("rows"):
        return []
    header = [
        "Row",
        f"v{comparison.get('versionNumber')}",
        f"v{comparison.get('comparedVersionNumber')}",
        "Delta",
        "Source",
    ]
    rows = [[Paragraph(f"<b>{part}</b>", styles["small"]) for part in header]]
    for row in comparison["rows"][:20]:
        delta = row["delta"]
        text = "—"
        if delta["delta"] is not None:
            percent = (
                f" ({delta['deltaPercent']:+.1f}%)" if delta["deltaPercent"] is not None else ""
            )
            text = f"{delta['delta']:+,.0f}{percent}"
        rows.append(
            [
                Paragraph(row["label"], styles["small"]),
                Paragraph(delta.get("displayA") or "—", styles["small"]),
                Paragraph(delta.get("displayB") or "—", styles["small"]),
                Paragraph(text, styles["small"]),
                Paragraph(
                    " → ".join(part for part in (row.get("sourceA"), row.get("sourceB")) if part),
                    styles["small"],
                ),
            ]
        )
    table = Table(rows, colWidths=[CONTENT_WIDTH * 0.34, *[CONTENT_WIDTH * 0.165] * 4])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [Paragraph("Version comparison", styles["heading"]), table, Spacer(1, 4 * mm)]


# --------------------------------------------------------------------------- #
def _decorate(canvas: Any, doc: Any, context: ExportContext) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(15 * mm, 12 * mm, PAGE[0] - 15 * mm, 12 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(
        15 * mm,
        8 * mm,
        f"{context.department} · {context.subtitle} · CS Meeting",
    )
    canvas.drawRightString(PAGE[0] - 15 * mm, 8 * mm, f"page {doc.page}")
    canvas.restoreState()


def render_pdf(context: ExportContext, path: Path) -> Path:
    """Write the executive review to ``path``."""
    styles = _styles()
    document = SimpleDocTemplate(
        str(path),
        pagesize=PAGE,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"{context.department} {context.subtitle}",
        author="CS Meeting",
    )

    story: list[Any] = []
    story += _header(context, styles)
    story += _kpi_block(context, styles)
    story += _insight_block(context, styles)
    story += _issue_block(context, styles)
    if context.series:
        story.append(PageBreak())
        story += _chart_block(context, styles)
    if context.comparison:
        story += _comparison_block(context, styles)
    if context.tables:
        story.append(PageBreak())
        story += _table_blocks(context, styles)

    document.build(
        story,
        onFirstPage=lambda canvas, doc: _decorate(canvas, doc, context),
        onLaterPages=lambda canvas, doc: _decorate(canvas, doc, context),
    )
    logger.info("wrote PDF %s (%d bytes)", path.name, path.stat().st_size)
    return path


def default_filename(context: ExportContext, when: datetime | None = None) -> str:
    stamp = (when or context.generated_at).strftime("%Y%m%d-%H%M%S")
    period = (context.period or {}).get("label", "period").replace("/", "-").replace("'", "")
    return f"{context.department}_{period}_v{context.version_number}_{stamp}.pdf"
