"""Export the executive review as PDF or PowerPoint.

The request carries the page's own state — version, period, table, metric and
the version being compared — so the file is exactly what the user was looking
at (ADR-0030).  Both formats are produced from one context, so they can never
tell different stories.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import get_session
from app.schemas.common import CamelModel
from app.services.export import context as export_context
from app.services.export import pdf as pdf_export
from app.services.export import powerpoint as pptx_export

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/versions", tags=["export"])


class ExportRequest(CamelModel):
    """The state of the page being exported."""

    period: str | None = None
    table: str | None = None
    metric: str | None = None
    #: when the page is showing a version comparison
    compare_with: int | None = None
    include_tables: bool = True
    include_charts: bool = True


def _context(session: Session, version_id: int, request: ExportRequest):
    return export_context.build_context(
        session,
        version_id=version_id,
        period=request.period,
        table=request.table,
        metric=request.metric,
        compare_with=request.compare_with,
        include_tables=request.include_tables,
        include_charts=request.include_charts,
    )


@router.post("/{version_id}/export/pdf")
def export_pdf(
    version_id: int,
    request: ExportRequest | None = None,
    session: Session = Depends(get_session),
) -> FileResponse:
    """A structured PDF of the current executive view."""
    request = request or ExportRequest()
    context = _context(session, version_id, request)
    settings = get_settings()
    path = settings.exports_dir / pdf_export.default_filename(context)
    pdf_export.render_pdf(context, path)
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@router.post("/{version_id}/export/ppt")
def export_pptx(
    version_id: int,
    request: ExportRequest | None = None,
    session: Session = Depends(get_session),
) -> FileResponse:
    """An editable PowerPoint deck of the current executive view."""
    request = request or ExportRequest()
    context = _context(session, version_id, request)
    settings = get_settings()
    path = settings.exports_dir / pptx_export.default_filename(context)
    pptx_export.render_pptx(context, path)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=path.name,
    )
