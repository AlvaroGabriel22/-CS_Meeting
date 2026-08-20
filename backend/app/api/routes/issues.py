"""Issue reports and their images."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.base import get_session
from app.db.models import Issue, PresentationVersion
from app.schemas.issues import IssueCreateIn, IssueMediaOut, IssueOut, IssueUpdateIn
from app.schemas.table import TableOut
from app.services import assets, issues, presentation_service, serializers

router = APIRouter(prefix="/api", tags=["issues"])


def _tables_of(version: PresentationVersion) -> list[TableOut]:
    return [
        serializers.table_out(definition)
        for data in version.imports
        for definition in sorted(data.tables, key=lambda item: item.order_index)
    ]


def _department_of(version: PresentationVersion) -> str:
    return version.imports[0].department.value if version.imports else "IQC"


def _media_out(media) -> IssueMediaOut:
    return IssueMediaOut(
        id=media.id,
        asset_id=media.asset_id,
        url=f"/api/assets/{media.asset_id}",
        mime_type=media.asset.mime_type,
        size_bytes=media.asset.size_bytes,
        caption=media.caption,
        order_index=media.order_index,
    )


def issue_out(issue: Issue) -> IssueOut:
    return IssueOut(
        id=issue.id,
        version_id=issue.version_id,
        department=issue.department.value,
        period=issue.period,
        reference_period=issue.reference_period,
        table=issue.table_name,
        category=issue.category,
        subcategory=issue.subcategory,
        metric=issue.metric,
        series_type=issue.series_type,
        title=issue.title,
        description=issue.description_text,
        description_doc=issue.description_doc or {},
        translation_key=issue.translation_key,
        language=issue.language,
        severity=issue.severity.value,
        status=issue.status.value,
        value=issue.value,
        previous_value=issue.previous_value,
        delta=issue.delta,
        delta_percent=issue.delta_percent,
        target=issue.target,
        direction=issue.direction,
        analytical_severity=issue.analytical_severity,
        trend=issue.trend,
        source_cell=issue.source_cell,
        source_range=issue.source_range,
        origin=issue.origin,
        media=[_media_out(media) for media in issue.media],
        created_at=issue.created_at,
        updated_at=issue.updated_at,
    )


@router.get("/versions/{version_id}/issues", response_model=list[IssueOut])
def list_issues(
    version_id: int,
    period: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_session),
) -> list[IssueOut]:
    """The issues raised on one snapshot, optionally for one period."""
    presentation_service.get_version(session, version_id)
    return [
        issue_out(issue)
        for issue in issues.list_issues(session, version_id=version_id, period=period, status=status)
    ]


@router.post("/versions/{version_id}/issues", response_model=IssueOut, status_code=201)
def create_issue(
    version_id: int, payload: IssueCreateIn, session: Session = Depends(get_session)
) -> IssueOut:
    """Raise an issue about one reading.

    The client chooses *what* the issue is about (table, category, metric,
    period) and writes the text; every number attached to it is read from the
    snapshot, so the issue can always be proved.
    """
    version = presentation_service.get_version(session, version_id)
    issue = issues.create_issue(
        session,
        version=version,
        tables=_tables_of(version),
        department=_department_of(version),
        period=payload.period,
        table=payload.table,
        category=payload.category,
        subcategory=payload.subcategory,
        metric=payload.metric,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        origin=payload.origin,
        language=payload.language,
    )
    return issue_out(issue)


@router.patch("/versions/{version_id}/issues/{issue_id}", response_model=IssueOut)
def update_issue(
    version_id: int,
    issue_id: int,
    payload: IssueUpdateIn,
    session: Session = Depends(get_session),
) -> IssueOut:
    """Edit the editorial half: title, description, severity, status, language."""
    issue = issues.get_issue(session, issue_id, version_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    changes.update(payload.model_extra or {})  # unknown fields are refused by name
    return issue_out(issues.update_issue(session, issue, changes))


@router.post(
    "/versions/{version_id}/issues/{issue_id}/media", response_model=IssueOut, status_code=201
)
async def attach_media(
    version_id: int,
    issue_id: int,
    file: UploadFile = File(...),
    caption: str | None = Form(None),
    session: Session = Depends(get_session),
) -> IssueOut:
    """Attach an image as evidence.  The bytes go to disk, never to SQLite."""
    issue = issues.get_issue(session, issue_id, version_id)
    payload = await file.read()
    asset = assets.store_image(
        session,
        filename=file.filename or "image.png",
        content_type=file.content_type,
        payload=payload,
    )
    issues.attach_media(session, issue, asset, caption)
    session.flush()
    return issue_out(issue)


@router.get("/assets/{asset_id}")
def get_asset(asset_id: int, session: Session = Depends(get_session)) -> FileResponse:
    """Serve an image by id — the stored path is never exposed to the client."""
    asset = assets.get_asset(session, asset_id)
    return FileResponse(
        assets.absolute_path(asset),
        media_type=asset.mime_type,
        filename=asset.original_filename or f"asset-{asset.id}",
    )
