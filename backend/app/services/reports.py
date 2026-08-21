"""The report — a table the author builds by hand.

The system stores it and serves it.  It never writes a word of it, never
suggests a row and never derives anything from the numbers (ADR-0036).

The shape is a small document, not a spreadsheet:

* **columns** the author creates and names;
* **rows** the author adds, as many as wanted;
* every **cell** holds an ordered list of **blocks** — text, image or shape —
  so a cell can be "text, then a photo, then more text", in that order, with
  the alignment the author chose (ADR-0038).

Only two things are ever computed from it: its plain text (for translation and
search) and its content hash (the translation cache key).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationError
from app.db.models import Asset, PresentationVersion, ReportMedia, VersionReport
from app.services.translation import documents

logger = logging.getLogger(__name__)

BLOCK_TYPES = ("text", "image", "shape")
ALIGNMENTS = ("left", "center", "right")
SHAPES = ("rectangle", "circle", "line", "arrow", "divider")
TEXT_SIZES = ("small", "normal", "large", "heading")

MAX_COLUMNS = 12
MAX_ROWS = 200
MAX_BLOCKS_PER_CELL = 40


def empty_content() -> dict[str, Any]:
    """A report nobody has written yet: a title slot and no columns."""
    return {"title": "", "columns": [], "rows": []}


# --------------------------------------------------------------------------- #
# Validation — the shape is the author's, the rules are ours
# --------------------------------------------------------------------------- #
def _identifier(value: Any) -> str:
    text = str(value or "").strip()
    return text or uuid4().hex[:8]


def _clean_block(raw: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(raw.get("type") or "").strip()
    if kind not in BLOCK_TYPES:
        return None
    align = raw.get("align") if raw.get("align") in ALIGNMENTS else "left"
    block: dict[str, Any] = {"id": _identifier(raw.get("id")), "type": kind, "align": align}

    if kind == "text":
        block["text"] = str(raw.get("text") or "")
        block["bold"] = bool(raw.get("bold"))
        block["italic"] = bool(raw.get("italic"))
        block["size"] = raw.get("size") if raw.get("size") in TEXT_SIZES else "normal"
        return block

    if kind == "image":
        asset_id = raw.get("assetId")
        if asset_id is None:
            return None
        block["assetId"] = int(asset_id)
        block["url"] = f"/api/assets/{int(asset_id)}"
        block["caption"] = str(raw.get("caption") or "")
        width = raw.get("width")
        block["width"] = max(10, min(100, int(width))) if width else 100
        return block

    block["shape"] = raw.get("shape") if raw.get("shape") in SHAPES else "rectangle"
    block["color"] = str(raw.get("color") or "#1E3A5F")
    size = raw.get("size")
    block["size"] = max(4, min(400, int(size))) if size else 48
    return block


def clean_content(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Accept what the author sent, refuse what would not render.

    Unknown block types and empty columns are dropped rather than stored; a
    report that is too large to be a report is refused by name.
    """
    raw = raw or {}
    columns_in = raw.get("columns") or []
    rows_in = raw.get("rows") or []
    if len(columns_in) > MAX_COLUMNS:
        raise ValidationError(
            "Too many columns for one report", {"columns": len(columns_in), "max": MAX_COLUMNS}
        )
    if len(rows_in) > MAX_ROWS:
        raise ValidationError(
            "Too many rows for one report", {"rows": len(rows_in), "max": MAX_ROWS}
        )

    columns = [
        {"id": _identifier(column.get("id")), "name": str(column.get("name") or "")}
        for column in columns_in
    ]
    known = {column["id"] for column in columns}

    rows: list[dict[str, Any]] = []
    for row in rows_in:
        cells: dict[str, list[dict[str, Any]]] = {}
        for column_id, blocks in (row.get("cells") or {}).items():
            if column_id not in known:
                continue  # a cell of a column that no longer exists
            cleaned = [
                block
                for block in (_clean_block(item) for item in (blocks or [])[:MAX_BLOCKS_PER_CELL])
                if block is not None
            ]
            cells[column_id] = cleaned
        rows.append({"id": _identifier(row.get("id")), "cells": cells})

    return {"title": str(raw.get("title") or ""), "columns": columns, "rows": rows}


# --------------------------------------------------------------------------- #
# Reading the content
# --------------------------------------------------------------------------- #
def iter_blocks(content: dict[str, Any] | None) -> Iterable[dict[str, Any]]:
    for row in (content or {}).get("rows", []) or []:
        for blocks in (row.get("cells") or {}).values():
            yield from blocks or []


def translatable_strings(content: dict[str, Any] | None) -> list[str]:
    """Every word a reader reads: the title, the column names, the text.

    Image captions travel too — they are the author's words about a photo.
    Nothing else in the report is language.
    """
    content = content or {}
    found: list[str] = []
    if content.get("title"):
        found.append(content["title"])
    for column in content.get("columns", []) or []:
        if column.get("name"):
            found.append(column["name"])
    for block in iter_blocks(content):
        if block["type"] == "text" and block.get("text", "").strip():
            found.append(block["text"])
        if block["type"] == "image" and block.get("caption", "").strip():
            found.append(block["caption"])
    return list(dict.fromkeys(found))


def apply_translation(content: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """A copy of the report with its words replaced and its structure intact."""
    import copy

    translated = copy.deepcopy(content)
    if translated.get("title"):
        translated["title"] = mapping.get(translated["title"], translated["title"])
    for column in translated.get("columns", []) or []:
        if column.get("name"):
            column["name"] = mapping.get(column["name"], column["name"])
    for block in iter_blocks(translated):
        if block["type"] == "text" and block.get("text"):
            block["text"] = mapping.get(block["text"], block["text"])
        if block["type"] == "image" and block.get("caption"):
            block["caption"] = mapping.get(block["caption"], block["caption"])
    return translated


def plain_text(content: dict[str, Any] | None) -> str:
    """The report as one string, in reading order."""
    return "\n".join(translatable_strings(content))


def has_content(content: dict[str, Any] | None) -> bool:
    content = content or {}
    return bool(content.get("title") or content.get("columns") or content.get("rows"))


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def get_report(session: Session, version_id: int) -> VersionReport | None:
    return session.scalars(
        select(VersionReport).where(VersionReport.version_id == version_id).limit(1)
    ).first()


def save_report(
    session: Session,
    *,
    version: PresentationVersion,
    content: dict[str, Any] | None,
    language: str = "en",
) -> VersionReport:
    """Create or replace the report of one snapshot."""
    cleaned = clean_content(content)
    report = get_report(session, version.id)
    if report is None:
        report = VersionReport(version_id=version.id)
        session.add(report)

    report.content = cleaned
    report.text = plain_text(cleaned)
    report.translation_key = documents.text_hash(report.text)
    report.language = language
    report.updated_at = datetime.now(timezone.utc)
    session.flush()
    logger.info(
        "report saved on version %d: %d column(s), %d row(s), %s",
        version.id,
        len(cleaned["columns"]),
        len(cleaned["rows"]),
        language,
    )
    return report


def attach_media(
    session: Session, report: VersionReport, asset: Asset, caption: str | None = None
) -> ReportMedia:
    """Register an uploaded image against the report so it is never orphaned."""
    existing = next((item for item in report.media if item.asset_id == asset.id), None)
    if existing is not None:
        return existing
    media = ReportMedia(asset_id=asset.id, caption=caption, order_index=len(report.media))
    report.media.append(media)
    session.flush()
    logger.info("report %d: attached asset %d", report.id, asset.id)
    return media


def require_report(session: Session, version_id: int) -> VersionReport:
    report = get_report(session, version_id)
    if report is None:
        raise NotFound("This version has no report yet", {"versionId": version_id})
    return report
