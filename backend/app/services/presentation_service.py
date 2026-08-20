"""Presentations and version snapshots.

Every upload is a photograph of the raw data at that moment.  A snapshot is
therefore **append-only**: version 3 showing ``4Q | Nov | Dec`` never touches
version 1, which still shows ``3Q | Aug`` and still points at the workbook it
was built from.

    Presentation (IQC)
      └── Version 1 → import 7  → raw file A   ('25 '26 1Q 2Q 3Q Aug)
      └── Version 2 → import 9  → raw file B   (… Aug Sep)
      └── Version 3 → import 12 → raw file C   (… 4Q Nov Dec)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import LimitReached, NotFound
from app.db.models import (
    Department,
    DepartmentData,
    Presentation,
    PresentationStatus,
    PresentationVersion,
    VersionStatus,
)

logger = logging.getLogger(__name__)


def active_presentations(session: Session) -> list[Presentation]:
    return list(
        session.scalars(
            select(Presentation).where(
                Presentation.status.in_([PresentationStatus.DRAFT, PresentationStatus.READY])
            )
        )
    )


def find_presentation(session: Session, department: Department) -> Presentation | None:
    return session.scalars(
        select(Presentation)
        .where(
            Presentation.department == department,
            Presentation.status.in_([PresentationStatus.DRAFT, PresentationStatus.READY]),
        )
        .order_by(Presentation.id.desc())
    ).first()


def ensure_presentation(
    session: Session, department: Department, *, name: str | None = None
) -> Presentation:
    """The department's active presentation, created on first use.

    The 8-presentation ceiling is enforced here; nothing is ever archived or
    deleted automatically to make room.
    """
    existing = find_presentation(session, department)
    if existing is not None:
        return existing

    limit = get_settings().max_active_presentations
    if len(active_presentations(session)) >= limit:
        raise LimitReached(
            "Presentation limit reached",
            {"limit": limit, "department": department.value},
        )

    presentation = Presentation(
        department=department,
        name=name or f"{department.value} Quality Weekly",
        status=PresentationStatus.DRAFT,
    )
    session.add(presentation)
    session.flush()
    logger.info("created presentation %d for %s", presentation.id, department.value)
    return presentation


def next_version_number(session: Session, presentation: Presentation) -> int:
    highest = session.scalar(
        select(func.max(PresentationVersion.number)).where(
            PresentationVersion.presentation_id == presentation.id
        )
    )
    return (highest or 0) + 1


def create_snapshot(
    session: Session,
    *,
    presentation: Presentation,
    data: DepartmentData,
    label: str | None = None,
) -> PresentationVersion:
    """Freeze one import as a new version of the presentation."""
    previous = session.scalars(
        select(PresentationVersion)
        .where(PresentationVersion.presentation_id == presentation.id)
        .order_by(PresentationVersion.number.desc())
    ).first()

    summary = dict(data.summary or {})
    period_labels = summary.get("periodLabels") or []
    version = PresentationVersion(
        presentation_id=presentation.id,
        number=next_version_number(session, presentation),
        label=label or _default_label(summary),
        status=VersionStatus.PUBLISHED,
        published_at=datetime.now(timezone.utc),
        parent_version_id=previous.id if previous else None,
        summary={
            "parserVersion": data.parser_version,
            "tableNames": summary.get("tableNames", []),
            "periodLabels": period_labels,
            "tableCount": summary.get("tableCount", 0),
            "sheets": summary.get("sheets", []),
            "rawFile": data.raw_file.original_filename if data.raw_file else None,
        },
        warnings=list(data.warnings or []),
    )
    version.imports.append(data)  # referenced, never copied
    session.add(version)
    session.flush()

    presentation.period_label = _default_label(summary) or presentation.period_label
    presentation.updated_at = datetime.now(timezone.utc)
    logger.info(
        "presentation %d: created version %d from import %d",
        presentation.id,
        version.number,
        data.id,
    )
    return version


def _default_label(summary: dict) -> str | None:
    """Name a version after the last period the file shows ("Aug", "W48")."""
    labels = summary.get("periodLabels") or []
    return labels[-1] if labels else None


def snapshot_for_import(
    session: Session, *, department: Department, data: DepartmentData
) -> PresentationVersion:
    presentation = ensure_presentation(session, department)
    return create_snapshot(session, presentation=presentation, data=data)


def get_version(session: Session, version_id: int) -> PresentationVersion:
    version = session.get(PresentationVersion, version_id)
    if version is None:
        raise NotFound("Version not found", {"versionId": version_id})
    return version


def list_versions(session: Session, presentation_id: int) -> list[PresentationVersion]:
    return list(
        session.scalars(
            select(PresentationVersion)
            .where(PresentationVersion.presentation_id == presentation_id)
            .order_by(PresentationVersion.number.desc())
        )
    )
