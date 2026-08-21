"""Export the department page as PDF or PowerPoint.

The page shows one snapshot: its charts, its tables and its report.  The
request carries the version and the language being read, and both formats are
produced from one context, so they can never tell different stories
(ADR-0030, ADR-0036).
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
    """What to put in the file.

    The reports library offers the three parts separately — report, charts,
    tables — so each can be downloaded on its own (ADR-0038).
    """

    include_charts: bool = True
    include_tables: bool = True
    include_report: bool = True
    #: the language the report is being read in — the file must say what the
    #: screen says, and only the report is ever translated (ADR-0036)
    language: str | None = None
    translate: bool = False


def _context(session: Session, version_id: int, request: ExportRequest):
    return export_context.build_context(
        session,
        version_id=version_id,
        include_tables=request.include_tables,
        include_charts=request.include_charts,
        include_report=request.include_report,
        language=request.language,
        translate=request.translate,
    )


@router.post("/{version_id}/export/pdf")
def export_pdf(
    version_id: int,
    request: ExportRequest | None = None,
    session: Session = Depends(get_session),
) -> FileResponse:
    """A structured PDF of the department page."""
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
    """An editable PowerPoint deck of the department page."""
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
