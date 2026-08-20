"""Presentations and their version snapshots."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.base import get_session
from app.db.models import Department, Presentation
from app.schemas.imports import ImportOut
from app.schemas.presentation import PresentationOut, PresentationVersionOut, VersionViewOut
from app.services import presentation_service, serializers
from app.services.render_model import build_table_view

router = APIRouter(prefix="/api", tags=["presentations"])


@router.get("/presentations", response_model=list[PresentationOut])
def list_presentations(
    department: Department | None = None,
    session: Session = Depends(get_session),
) -> list[PresentationOut]:
    query = select(Presentation).order_by(Presentation.id)
    if department:
        query = query.where(Presentation.department == department)
    return [serializers.presentation_out(item) for item in session.scalars(query)]


@router.get("/presentations/{presentation_id}", response_model=PresentationOut)
def get_presentation(
    presentation_id: int, session: Session = Depends(get_session)
) -> PresentationOut:
    presentation = session.get(Presentation, presentation_id)
    if presentation is None:
        raise NotFound("Presentation not found", {"presentationId": presentation_id})
    return serializers.presentation_out(presentation)


@router.get(
    "/presentations/{presentation_id}/versions", response_model=list[PresentationVersionOut]
)
def list_versions(
    presentation_id: int, session: Session = Depends(get_session)
) -> list[PresentationVersionOut]:
    """Every snapshot, newest first.  Old versions are never rewritten."""
    if session.get(Presentation, presentation_id) is None:
        raise NotFound("Presentation not found", {"presentationId": presentation_id})
    return [
        serializers.version_out(version)
        for version in presentation_service.list_versions(session, presentation_id)
    ]


@router.get("/versions/{version_id}", response_model=PresentationVersionOut)
def get_version(version_id: int, session: Session = Depends(get_session)) -> PresentationVersionOut:
    return serializers.version_out(presentation_service.get_version(session, version_id))


@router.get("/versions/{version_id}/imports", response_model=list[ImportOut])
def get_version_imports(
    version_id: int, session: Session = Depends(get_session)
) -> list[ImportOut]:
    """The data this snapshot froze — exactly what it showed when it was saved."""
    version = presentation_service.get_version(session, version_id)
    return [serializers.import_out(data, version=version) for data in version.imports]


@router.get("/versions/{version_id}/view", response_model=VersionViewOut)
def get_version_view(version_id: int, session: Session = Depends(get_session)) -> VersionViewOut:
    """Render a snapshot exactly as it was saved.

    A later upload creates a new version; this one keeps showing the periods and
    the values it froze.
    """
    version = presentation_service.get_version(session, version_id)
    tables = [
        build_table_view(serializers.table_out(definition))
        for data in version.imports
        for definition in sorted(data.tables, key=lambda item: item.order_index)
    ]
    department = version.imports[0].department.value if version.imports else "IQC"
    return VersionViewOut.model_validate(
        {
            "version": serializers.version_out(version).model_dump(by_alias=True),
            "department": department,
            "tables": tables,
        }
    )
