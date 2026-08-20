"""PowerPoint export — the executive review as editable slides.

Everything that can be an object *is* one: text frames stay editable, the chart
is a native PowerPoint chart with its data behind it, tables are real tables
with their merges, and only the issue photographs are pictures (Sprint 5 §15).

The slides show the same version, period, table and metric the screen showed —
both formats read the same :class:`ExportContext` (ADR-0030).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Emu, Inches, Pt

from .context import ExportContext

logger = logging.getLogger(__name__)

BRAND = RGBColor(0x1E, 0x3A, 0x5F)
BRAND_LIGHT = RGBColor(0xE2, 0xEC, 0xF8)
INK = RGBColor(0x14, 0x20, 0x2E)
MUTED = RGBColor(0x6B, 0x7D, 0x94)
POSITIVE = RGBColor(0x1D, 0x7A, 0x5F)
NEGATIVE = RGBColor(0xB3, 0x38, 0x2F)

SEVERITY_COLOR = {
    "positive": POSITIVE,
    "negative": NEGATIVE,
    "high": NEGATIVE,
    "medium": RGBColor(0xB5, 0x76, 0x1F),
}

SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)
MARGIN = Inches(0.6)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _blank(presentation: Presentation):
    return presentation.slides.add_slide(presentation.slide_layouts[6])


def _textbox(slide, left, top, width, height):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    return frame


def _write(frame, text: str, *, size=14, bold=False, color=INK, space_after=4, first=False):
    paragraph = frame.paragraphs[0] if first else frame.add_paragraph()
    paragraph.text = text
    paragraph.space_after = Pt(space_after)
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return paragraph


def _title_bar(slide, title: str, subtitle: str) -> None:
    frame = _textbox(slide, MARGIN, Inches(0.35), SLIDE_WIDTH - 2 * MARGIN, Inches(1.0))
    _write(frame, title, size=26, bold=True, color=BRAND, first=True)
    _write(frame, subtitle, size=11, color=MUTED)


def _footer(slide, context: ExportContext) -> None:
    frame = _textbox(slide, MARGIN, SLIDE_HEIGHT - Inches(0.55), SLIDE_WIDTH - 2 * MARGIN, Inches(0.35))
    _write(
        frame,
        f"{context.department} · {context.subtitle} · CS Meeting · "
        f"{context.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
        size=8,
        color=MUTED,
        first=True,
    )


# --------------------------------------------------------------------------- #
# Slides
# --------------------------------------------------------------------------- #
def _overview_slide(presentation: Presentation, context: ExportContext) -> None:
    slide = _blank(presentation)
    period = (context.period or {}).get("label", "—")
    _title_bar(
        slide,
        f"{context.department} — Executive overview",
        f"Period {period} · Version {context.version_number}"
        + (f" · {context.raw_file}" if context.raw_file else ""),
    )

    columns = max(len(context.kpis), 1)
    width = (SLIDE_WIDTH - 2 * MARGIN) / columns
    for index, kpi in enumerate(context.kpis):
        frame = _textbox(slide, MARGIN + Emu(int(width * index)), Inches(1.7), Emu(int(width)) - Inches(0.2), Inches(2.0))
        _write(frame, kpi["label"], size=11, color=MUTED, first=True)
        _write(frame, kpi.get("display") or "—", size=30, bold=True, color=BRAND)
        if kpi.get("delta") is not None:
            percent = f" ({kpi['deltaPercent']:+.1f}%)" if kpi.get("deltaPercent") is not None else ""
            reference = (kpi.get("previousPeriod") or {}).get("label") or "—"
            _write(
                frame,
                f"{kpi['delta']:+,.0f}{percent} vs {reference}",
                size=11,
                color=SEVERITY_COLOR.get(kpi.get("severity"), MUTED),
            )
        if kpi.get("target") is not None:
            _write(frame, f"Target {kpi['targetDisplay']} · {kpi['targetStatus']}", size=10, color=MUTED)
        _write(frame, f"{kpi.get('sourceRange') or ''} · {kpi.get('source') or ''}", size=8, color=MUTED)

    if context.warnings:
        frame = _textbox(slide, MARGIN, Inches(4.1), SLIDE_WIDTH - 2 * MARGIN, Inches(1.0))
        _write(frame, "Notes", size=11, bold=True, color=BRAND, first=True)
        for warning in context.warnings:
            _write(frame, f"• {warning.replace('_', ' ')}", size=10, color=MUTED)
    _footer(slide, context)


def _insight_slide(presentation: Presentation, context: ExportContext) -> None:
    if not context.insights:
        return
    slide = _blank(presentation)
    _title_bar(slide, "Executive insights", context.subtitle)
    frame = _textbox(slide, MARGIN, Inches(1.6), SLIDE_WIDTH - 2 * MARGIN, Inches(5.0))

    first = True
    for insight in context.insights:
        _write(
            frame,
            f"• {insight['text']}",
            size=14,
            color=SEVERITY_COLOR.get(insight.get("severity"), INK),
            first=first,
        )
        first = False
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
        trend = insight.get("trend") or {}
        if trend.get("classification") not in (None, "insufficient_data"):
            origin += f" · trend {trend['classification']}"
            if trend.get("quality") not in (None, "unknown"):
                origin += f" ({trend['quality']})"
        _write(frame, f"    {origin}", size=9, color=MUTED, space_after=8)
    _footer(slide, context)


def _issue_slides(presentation: Presentation, context: ExportContext) -> None:
    for issue in context.issues:
        slide = _blank(presentation)
        _title_bar(slide, issue["title"], f"Issue report · {context.subtitle}")

        frame = _textbox(slide, MARGIN, Inches(1.6), Inches(6.4), Inches(4.6))
        meta = " · ".join(
            part
            for part in (
                issue.get("table"),
                issue.get("category"),
                issue.get("subcategory"),
                issue.get("metric"),
                issue.get("period"),
            )
            if part
        )
        _write(frame, meta, size=11, color=MUTED, first=True)
        _write(
            frame,
            f"status {issue['status']} · severity {issue['severity']}",
            size=11,
            color=SEVERITY_COLOR.get(issue["severity"], MUTED),
        )
        if issue.get("value") is not None:
            line = f"{issue['value']:,.0f}"
            if issue.get("previousValue") is not None:
                line += f"  (from {issue['previousValue']:,.0f}"
                if issue.get("deltaPercent") is not None:
                    line += f", {issue['deltaPercent']:+.1f}%"
                line += ")"
            _write(frame, line, size=20, bold=True, color=BRAND)
        if issue.get("description"):
            for line in issue["description"].split("\n"):
                _write(frame, line, size=13)
        _write(
            frame,
            f"{issue.get('sourceRange') or ''} · {issue.get('source') or ''}",
            size=9,
            color=MUTED,
        )

        for index, image in enumerate(issue.get("images", [])[:2]):
            try:
                slide.shapes.add_picture(
                    image["path"],
                    Inches(7.2),
                    Inches(1.6) + Inches(2.6) * index,
                    height=Inches(2.4),
                )
            except Exception:  # pragma: no cover - never lose the slide over an image
                logger.warning("could not embed %s", image.get("path"))
        _footer(slide, context)


def _chart_slide(presentation: Presentation, context: ExportContext) -> None:
    series = [item for item in context.series if any(p["value"] is not None for p in item["points"])]
    if not series or not context.periods:
        return
    slide = _blank(presentation)
    heading = " · ".join(part for part in (context.table, context.metric) if part)
    _title_bar(slide, f"Trend — {heading}" if heading else "Trend", context.subtitle)

    labels = [period["label"] for period in context.periods]
    data = CategoryChartData()
    data.categories = labels
    for item in series[:5]:
        values = [
            next(
                (point["value"] for point in item["points"] if point["period"]["label"] == label),
                None,
            )
            for label in labels
        ]
        data.add_series(item["label"], values)

    # a native chart: the numbers stay behind it and stay editable
    frame = slide.shapes.add_chart(
        XL_CHART_TYPE.LINE_MARKERS,
        MARGIN,
        Inches(1.6),
        SLIDE_WIDTH - 2 * MARGIN,
        Inches(5.0),
        data,
    )
    chart = frame.chart
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.BOTTOM
    chart.legend.include_in_layout = False
    chart.font.size = Pt(11)
    _footer(slide, context)


def _table_slides(presentation: Presentation, context: ExportContext) -> None:
    for view in context.tables:
        slide = _blank(presentation)
        _title_bar(
            slide,
            view["title"] or view["sheet"],
            f"{view['sheet']}!{view['sourceRange']} · {context.subtitle}",
        )

        rows, columns = view["rowCount"], view["columnCount"]
        label_columns = view["labelColumnCount"]
        shape = slide.shapes.add_table(
            rows,
            columns,
            MARGIN,
            Inches(1.5),
            SLIDE_WIDTH - 2 * MARGIN,
            Inches(5.2),
        )
        table = shape.table

        label_width = int((SLIDE_WIDTH - 2 * MARGIN) * 0.13)
        value_width = int(
            ((SLIDE_WIDTH - 2 * MARGIN) - label_width * label_columns)
            / max(columns - label_columns, 1)
        )
        for index in range(columns):
            table.columns[index].width = Emu(label_width if index < label_columns else value_width)

        for row in view["rows"]:
            for cell in row["cells"]:
                target = table.cell(cell["row"], cell["col"])
                if cell["rowSpan"] > 1 or cell["colSpan"] > 1:
                    target.merge(
                        table.cell(
                            cell["row"] + cell["rowSpan"] - 1,
                            cell["col"] + cell["colSpan"] - 1,
                        )
                    )
                text = cell["text"] or (cell["inferredText"] or "")
                target.text = text
                paragraph = target.text_frame.paragraphs[0]
                paragraph.alignment = None
                for run in paragraph.runs:
                    run.font.size = Pt(9)
                    run.font.bold = bool(cell["bold"] or cell["isHeadline"])
                    run.font.color.rgb = BRAND if row["kind"] == "header" else INK
        _footer(slide, context)


def _comparison_slide(presentation: Presentation, context: ExportContext) -> None:
    comparison = context.comparison
    if not comparison or not comparison.get("rows"):
        return
    slide = _blank(presentation)
    _title_bar(
        slide,
        "Version comparison",
        f"v{comparison.get('versionNumber')} → v{comparison.get('comparedVersionNumber')} · "
        f"{(context.period or {}).get('label', '')}",
    )

    rows = comparison["rows"][:12]
    shape = slide.shapes.add_table(
        len(rows) + 1, 5, MARGIN, Inches(1.6), SLIDE_WIDTH - 2 * MARGIN, Inches(4.8)
    )
    table = shape.table
    headers = [
        "Row",
        f"v{comparison.get('versionNumber')}",
        f"v{comparison.get('comparedVersionNumber')}",
        "Delta",
        "Source",
    ]
    for index, header in enumerate(headers):
        table.cell(0, index).text = header

    for index, row in enumerate(rows, start=1):
        delta = row["delta"]
        text = "—"
        if delta["delta"] is not None:
            percent = f" ({delta['deltaPercent']:+.1f}%)" if delta["deltaPercent"] is not None else ""
            text = f"{delta['delta']:+,.0f}{percent}"
        values = [
            row["label"],
            delta.get("displayA") or "—",
            delta.get("displayB") or "—",
            text,
            " → ".join(part for part in (row.get("sourceA"), row.get("sourceB")) if part),
        ]
        for column, value in enumerate(values):
            cell = table.cell(index, column)
            cell.text = value
            for run in cell.text_frame.paragraphs[0].runs:
                run.font.size = Pt(10)
    _footer(slide, context)


# --------------------------------------------------------------------------- #
def render_pptx(context: ExportContext, path: Path) -> Path:
    """Write the executive review as a PowerPoint deck."""
    presentation = Presentation()
    presentation.slide_width = SLIDE_WIDTH
    presentation.slide_height = SLIDE_HEIGHT

    _overview_slide(presentation, context)
    _insight_slide(presentation, context)
    _issue_slides(presentation, context)
    _chart_slide(presentation, context)
    _comparison_slide(presentation, context)
    _table_slides(presentation, context)

    presentation.save(str(path))
    logger.info(
        "wrote PPTX %s (%d slides, %d bytes)",
        path.name,
        len(presentation.slides._sldIdLst),
        path.stat().st_size,
    )
    return path


def default_filename(context: ExportContext, when: datetime | None = None) -> str:
    stamp = (when or context.generated_at).strftime("%Y%m%d-%H%M%S")
    period = (context.period or {}).get("label", "period").replace("/", "-").replace("'", "")
    return f"{context.department}_{period}_v{context.version_number}_{stamp}.pptx"
