"""PDF export — the department page, laid out for paper.

Structured, not screenshotted: text stays text, tables stay tables and the
charts are drawn natively, so the file is searchable and prints cleanly.

It carries what the page carries, in the page's order — the charts, the tables,
then the report the author built (ADR-0036).  The report keeps its shape: its
columns, its rows, and inside each cell the text, images and shapes in the
order they were placed (ADR-0038).  Nothing is composed here: no summary, no
commentary, no figure the workbook does not hold.

The tables keep their structure — merges become spans, the empty cell of a
headline row stays empty — because only the *representation* may be adapted to
the medium, never the model.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Circle, Drawing, Line as SLine, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Image,
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

#: one colour per category, in the order the workbook lists them
PALETTE = [
    colors.HexColor("#1E3A5F"),
    colors.HexColor("#4F7FB5"),
    colors.HexColor("#9DBADD"),
    colors.HexColor("#C7D9EF"),
]
LINE_COLOR = colors.HexColor("#B3382F")
#: a pair chart: closing years, the months of this one, and the target line
YEAR_BAR = colors.HexColor("#1E3A5F")
MONTH_BAR = colors.HexColor("#9DBADD")
TARGET_LINE = colors.HexColor("#4A7FBF")

PAGE = landscape(A4)
CONTENT_WIDTH = PAGE[0] - 30 * mm

#: The built-in PDF fonts have no Hangul: a Korean export written in Helvetica
#: is a page of empty boxes.  ReportLab ships CID fonts for exactly this, so the
#: file stays small and needs nothing installed on the reader's machine.
CJK_FONTS = {"ko": "HYSMyeongJo-Medium"}
_registered: set[str] = set()


def _font_for(language: str | None) -> str:
    """The typeface that can actually draw this language."""
    name = CJK_FONTS.get(language or "")
    if name is None:
        return "Helvetica"
    if name not in _registered:
        pdfmetrics.registerFont(UnicodeCIDFont(name))
        # the face has no bold cut; map bold and italic onto it so <b> in a
        # paragraph renders text rather than falling back to a Latin font
        for bold in (0, 1):
            for italic in (0, 1):
                addMapping(name, bold, italic, name)
        _registered.add(name)
    return name


def _styles(font: str = "Helvetica") -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    bold = "Helvetica-Bold" if font == "Helvetica" else font
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], textColor=BRAND, fontSize=20,
            alignment=TA_LEFT, fontName=bold,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], textColor=MUTED, fontSize=10, fontName=font
        ),
        "heading": ParagraphStyle(
            "heading", parent=base["Heading2"], textColor=BRAND, fontSize=13,
            spaceBefore=10, fontName=bold,
        ),
        "block_title": ParagraphStyle(
            "block_title", parent=base["Normal"], textColor=BRAND, fontSize=11,
            spaceAfter=2, fontName=bold,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], textColor=INK, fontSize=10, leading=14, fontName=font
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"], textColor=MUTED, fontSize=7.5, fontName=font
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
            context.version_label,
            f"Metric {context.metric}" if context.metric else None,
            context.raw_file,
        )
        if part
    )
    return [
        Paragraph(context.title, styles["title"]),
        Paragraph(meta, styles["subtitle"]),
        Spacer(1, 5 * mm),
    ]




def _value_range(chart: dict[str, Any]) -> tuple[float, float]:
    """The scale every layer of one drawing is measured against.

    A stacked column is as tall as its parts together, so that is what the
    range has to hold; a grouped one is as tall as its tallest part.
    """
    columns = len(chart["periods"])
    bars = [[point["value"] for point in series["points"]] for series in chart["bars"]]
    heights: list[float] = []
    for index in range(columns):
        values = [row[index] for row in bars if index < len(row) and row[index] is not None]
        if not values:
            continue
        heights.append(sum(values) if chart.get("stacked") else max(values))
    if chart.get("line"):
        heights.extend(
            point["value"] for point in chart["line"]["points"] if point["value"] is not None
        )
    if not heights:
        return 0.0, 1.0
    high = max(heights)
    low = min(0.0, min(heights))
    return low, (high * 1.08 if high > 0 else 1.0)

def _blocks(breaks: list[int], length: int) -> list[tuple[int, int]]:
    """The index ranges a line is drawn in, split at every break."""
    edges = [0, *[index for index in breaks if 0 < index < length], length]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]

def _one_chart(
    chart: dict[str, Any], width: float, height: float, context: ExportContext | None = None
) -> Drawing:
    """One table's chart: vertical bars per category, with the line over them."""
    term = context.term if context else (lambda value: value or "")
    font = _font_for(context.language if context else None)
    labels = [term(period["label"]) for period in chart["periods"]]
    drawing = Drawing(width, height)

    # every layer of this drawing must be measured against the same scale: the
    # bar chart and the line charts each compute their own otherwise, and a
    # line drawn to a different range says something the numbers do not
    low, high = _value_range(chart)

    bars = VerticalBarChart()
    bars.x = 26
    bars.y = 26
    bars.width = max(width - 36, 40)
    bars.height = max(height - 48, 40)
    bars.data = [[point["value"] for point in series["points"]] for series in chart["bars"]] or [[]]
    bars.categoryAxis.categoryNames = labels
    bars.valueAxis.valueMin, bars.valueAxis.valueMax = low, high
    bars.categoryAxis.labels.fontSize = 6
    bars.categoryAxis.labels.fontName = font
    bars.valueAxis.labels.fontSize = 6
    bars.valueAxis.labels.fontName = font
    bars.barSpacing = 0.5
    bars.groupSpacing = 6
    # the parts of a whole are drawn on top of each other, exactly as on screen
    if chart.get("stacked"):
        bars.categoryAxis.style = "stacked"
    for index in range(len(bars.data)):
        bars.bars[index].fillColor = PALETTE[index % len(PALETTE)]
        bars.bars[index].strokeColor = None
    # a pair chart separates the closing years from the months of this one by
    # colour, the same way the page does
    if chart.get("kind") == "pair":
        for column, period in enumerate(chart["periods"]):
            for index in range(len(bars.data)):
                bars.bars[(index, column)].fillColor = (
                    YEAR_BAR if period.get("kind") == "year" else MONTH_BAR
                )
    drawing.add(bars)

    if chart.get("line"):
        values = [point["value"] for point in chart["line"]["points"]]
        # one line per block, each blank outside its own: same categories, so
        # everything stays under the bars it belongs to, and nothing is drawn
        # across the seam where years become months (ADR-0047)
        for start, end in _blocks(chart.get("breaks") or [], len(values)):
            line = HorizontalLineChart()
            line.x, line.y = bars.x, bars.y
            line.width, line.height = bars.width, bars.height
            line.data = [
                [value if start <= index < end else None for index, value in enumerate(values)]
            ]
            line.categoryAxis.visible = False
            line.valueAxis.visible = False
            line.valueAxis.valueMin, line.valueAxis.valueMax = low, high
            line.lines[0].strokeColor = TARGET_LINE if chart.get("kind") == "pair" else LINE_COLOR
            line.lines[0].strokeWidth = 1.4
            drawing.add(line)

    is_pair = chart.get("kind") == "pair"
    legend = [term(series["label"]) for series in chart["bars"]]
    if chart.get("line"):
        legend.append(term(chart["line"]["label"]))
    step = width / max(len(legend), 1)
    for index, label in enumerate(legend):
        is_line = chart.get("line") and index == len(legend) - 1
        if is_line:
            colour = TARGET_LINE if is_pair else LINE_COLOR
        else:
            colour = YEAR_BAR if is_pair else PALETTE[index % len(PALETTE)]
        drawing.add(
            String(26 + index * step, 8, label[:16], fontSize=6.5, fillColor=colour, fontName=font)
        )
    return drawing


def _charts_block(context: ExportContext, styles: dict[str, ParagraphStyle]) -> list[Any]:
    """The charts, side by side, in the workbook's table order."""
    if not context.charts:
        return []
    width = CONTENT_WIDTH / max(len(context.charts), 1)
    cells = [
        [
            Paragraph(
                " · ".join(
                    part
                    for part in (chart.get("title") or chart["table"], chart.get("metric"))
                    if part
                ),
                styles["block_title"],
            ),
            _one_chart(chart, width - 6 * mm, 72 * mm, context),
        ]
        for chart in context.charts
    ]
    table = Table(
        [[Table([[part] for part in cell]) for cell in cells]], colWidths=[width] * len(cells)
    )
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [table, Spacer(1, 4 * mm)]


def _grid(
    view: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    context: ExportContext | None = None,
) -> tuple[list[list[Any]], list[Any]]:
    """The render model, turned into a ReportLab grid with its spans.

    Labels and period headers go through the glossary; a value never does.
    """
    rows: list[list[Any]] = [
        ["" for _ in range(view["columnCount"])] for _ in range(view["rowCount"])
    ]
    spans: list[Any] = []
    for row in view["rows"]:
        for cell in row["cells"]:
            text = cell["text"] or (cell["inferredText"] or "")
            if context is not None and cell["kind"] in ("label", "corner", "period"):
                text = context.term(text)
            rows[cell["row"]][cell["col"]] = Paragraph(
                f"<b>{text}</b>" if cell["bold"] or cell["isHeadline"] else text, styles["small"]
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


def _one_table(
    view: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    width: float,
    context: ExportContext | None = None,
) -> Any:
    rows, spans = _grid(view, styles, context)
    if not rows:
        return Paragraph("", styles["small"])
    columns = view["columnCount"]
    labels = view["labelColumnCount"]
    label_width = width * 0.22
    value_width = max((width - label_width * labels) / max(columns - labels, 1), 5 * mm)
    widths = [label_width] * labels + [value_width] * (columns - labels)

    table = Table(rows, colWidths=widths, repeatRows=view["headerRowCount"])
    style = [
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("FONTNAME", (0, 0), (-1, -1), styles["small"].fontName),
        ("BACKGROUND", (0, 0), (-1, view["headerRowCount"] - 1), BRAND_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 5.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]
    style.extend(spans)
    table.setStyle(TableStyle(style))
    return table


def _tables_block(context: ExportContext, styles: dict[str, ParagraphStyle]) -> list[Any]:
    """The tables, side by side, in the same order as the charts."""
    if not context.tables:
        return []
    width = CONTENT_WIDTH / max(len(context.tables), 1)
    cells = [
        [
            Paragraph(view["title"] or view["sheet"], styles["block_title"]),
            _one_table(view, styles, width - 4 * mm, context),
        ]
        for view in context.tables
    ]
    table = Table(
        [[Table([[part] for part in cell]) for cell in cells]], colWidths=[width] * len(cells)
    )
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [table, Spacer(1, 4 * mm)]


ALIGNMENT = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT}


def _cell_flowables(
    blocks: list[dict[str, Any]], context: ExportContext, styles: dict[str, ParagraphStyle], width: float
) -> list[Any]:
    """One cell of the report: its blocks, in the author's order.

    Text, images and shapes are drawn where the author put them — a cell is a
    little column of content, not a single string (ADR-0038).
    """
    parts: list[Any] = []
    for block in blocks or []:
        align = ALIGNMENT.get(block.get("align", "left"), TA_LEFT)

        if block["type"] == "text":
            style = ParagraphStyle(
                f"cell-{block['id']}",
                parent=styles["body"],
                alignment=align,
                fontSize={"small": 8, "normal": 9.5, "large": 12, "heading": 14}.get(
                    block.get("size"), 9.5
                ),
                leading=14,
                fontName=styles["body"].fontName
                if not block.get("bold")
                else styles["heading"].fontName,
            )
            text = (block.get("text") or "").replace("\n", "<br/>")
            if block.get("italic"):
                text = f"<i>{text}</i>"
            parts.append(Paragraph(text or "&nbsp;", style))

        elif block["type"] == "image":
            path = context.report_images.get(block.get("assetId"))
            if not path:
                continue
            try:
                image_width = width * (block.get("width", 100) / 100.0)
                image = Image(path, width=image_width, height=image_width, kind="proportional")
                image.hAlign = block.get("align", "left").upper()
                parts.append(image)
                if block.get("caption"):
                    parts.append(
                        Paragraph(
                            block["caption"],
                            ParagraphStyle(f"cap-{block['id']}", parent=styles["small"], alignment=align),
                        )
                    )
            except Exception:  # pragma: no cover - a broken image must not kill the export
                logger.warning("could not embed image %s", path)

        else:
            parts.append(_shape_drawing(block, width))
    return parts or [Paragraph("&nbsp;", styles["small"])]


def _shape_drawing(block: dict[str, Any], width: float) -> Drawing:
    """A rectangle, circle, line, arrow or divider the author placed."""
    size = float(block.get("size") or 48)
    colour = colors.HexColor(block.get("color") or "#1E3A5F")
    drawing = Drawing(width, size + 4)
    offset = {"left": 0.0, "center": (width - size) / 2, "right": width - size}.get(
        block.get("align", "left"), 0.0
    )
    offset = max(offset, 0.0)
    shape = block.get("shape", "rectangle")

    if shape == "circle":
        radius = size / 2
        drawing.add(Circle(offset + radius, radius + 2, radius, fillColor=colour, strokeColor=None))
    elif shape in ("line", "divider"):
        span = width if shape == "divider" else size
        drawing = Drawing(width, 6)
        drawing.add(SLine(offset, 3, offset + span, 3, strokeColor=colour, strokeWidth=1.2))
    elif shape == "arrow":
        drawing = Drawing(width, 10)
        drawing.add(SLine(offset, 5, offset + size, 5, strokeColor=colour, strokeWidth=1.4))
        drawing.add(
            Polygon(
                [offset + size, 5, offset + size - 6, 9, offset + size - 6, 1],
                fillColor=colour,
                strokeColor=None,
            )
        )
    else:
        drawing.add(Rect(offset, 2, size, size, fillColor=colour, strokeColor=None))
    return drawing


def _report_block(context: ExportContext, styles: dict[str, ParagraphStyle]) -> list[Any]:
    """The report, drawn as the table the author built."""
    if not context.has_report:
        return []
    report = context.report
    blocks: list[Any] = []
    if report.get("title"):
        blocks.append(Paragraph(report["title"], styles["heading"]))

    columns = report.get("columns") or []
    rows = report.get("rows") or []
    if not columns:
        return blocks

    width = CONTENT_WIDTH / len(columns)
    grid: list[list[Any]] = [
        [Paragraph(f"<b>{column.get('name') or ''}</b>", styles["body"]) for column in columns]
    ]
    for row in rows:
        cells = row.get("cells") or {}
        grid.append(
            [
                _cell_flowables(cells.get(column["id"]) or [], context, styles, width - 8 * mm)
                for column in columns
            ]
        )

    table = Table(grid, colWidths=[width] * len(columns), repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                ("FONTNAME", (0, 0), (-1, -1), styles["body"].fontName),
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    blocks.append(table)
    return blocks


def _decorate(canvas: Any, doc: Any, context: ExportContext) -> None:
    canvas.saveState()
    canvas.setFont(_font_for(context.language), 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(15 * mm, 9 * mm, f"{context.department} · {context.subtitle} · CS Meeting")
    canvas.drawRightString(PAGE[0] - 15 * mm, 9 * mm, f"page {doc.page}")
    canvas.restoreState()


def render_pdf(context: ExportContext, path: Path) -> Path:
    """Write the department page to ``path``."""
    styles = _styles(_font_for(context.language))
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
    story += _charts_block(context, styles)
    if context.tables:
        story.append(PageBreak())
        story += _tables_block(context, styles)
    if context.has_report:
        story.append(PageBreak())
        story += _report_block(context, styles)

    document.build(
        story,
        onFirstPage=lambda canvas, doc: _decorate(canvas, doc, context),
        onLaterPages=lambda canvas, doc: _decorate(canvas, doc, context),
    )
    logger.info("wrote PDF %s (%d bytes)", path.name, path.stat().st_size)
    return path


def default_filename(context: ExportContext, when: datetime | None = None) -> str:
    stamp = (when or context.generated_at).strftime("%Y%m%d-%H%M%S")
    label = (context.version_label or "version").replace("/", "-").replace("'", "")
    return f"{context.department}_{label}_v{context.version_number}_{stamp}.pdf"
