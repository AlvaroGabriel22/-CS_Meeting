"""Issue reports: what deserves attention, and the numbers that say so.

An issue has two halves and they are kept apart on purpose (ADR-0029):

* the **editorial** half — title, description, severity, status, images — is
  written by the user and is the only part an edit can touch;
* the **analytical** half — period, value, previous value, delta, trend, origin
  cell — is read from the model when the issue is created and stored with it.

The analytical half is *recomputed here* rather than accepted from the client:
an issue that claims a number the snapshot does not hold would be worse than no
issue at all.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationError
from app.db.models import (
    Asset,
    Department,
    Issue,
    IssueMedia,
    IssueSeverity,
    IssueStatus,
    PresentationVersion,
)
from app.schemas.table import TableOut
from app.services import executive
from app.services.translation import documents

logger = logging.getLogger(__name__)

#: what an edit is allowed to change
EDITABLE_FIELDS = ("title", "description", "severity", "status", "language")


# --------------------------------------------------------------------------- #
# Description documents
# --------------------------------------------------------------------------- #
def text_to_doc(text: str | None) -> dict[str, Any]:
    """Wrap plain text in the rich-document shape the system uses (ADR-0006)."""
    paragraphs = [line for line in (text or "").split("\n")]
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": ([{"type": "text", "text": line}] if line else []),
            }
            for line in paragraphs
        ]
        or [{"type": "paragraph", "content": []}],
    }


def doc_to_text(doc: dict[str, Any] | None) -> str:
    return documents.plain_text(doc or {}, separator="\n")


# --------------------------------------------------------------------------- #
# Deriving the analytical half
# --------------------------------------------------------------------------- #
def default_severity(kpi: dict[str, Any]) -> IssueSeverity:
    """A starting point the user can change — never a verdict.

    A movement the department calls bad is *medium*; if it also breaches a
    target the file carries, or the trend is worsening, it starts *high*.
    Anything else starts *info*.
    """
    trend = kpi.get("trend") or {}
    if kpi.get("severity") == "negative":
        if kpi.get("targetBreached") or trend.get("quality") == "worsening":
            return IssueSeverity.HIGH
        return IssueSeverity.MEDIUM
    return IssueSeverity.INFO


def find_kpi(
    tables: Sequence[TableOut],
    *,
    department: str,
    period: str | None,
    table: str | None,
    category: str | None,
    subcategory: str | None,
    metric: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
    """The KPI an issue is about, recomputed from the snapshot itself."""
    resolved = executive.resolve_period(tables, period)
    if resolved is None:
        raise ValidationError("This snapshot holds no period", {"period": period})
    reference, basis = executive.reference_of(tables, resolved)

    kpis = executive.build_kpis(
        tables,
        period=resolved,
        previous=reference,
        table=table,
        metric=metric,
        department=department,
        limit=100,
    )
    for kpi in kpis:
        selector = kpi["selector"]
        if category and selector.get("category") != category:
            continue
        if subcategory and selector.get("subcategory") != subcategory:
            continue
        return kpi, reference, basis

    raise ValidationError(
        "No reading matches this selection in the snapshot",
        {
            "period": resolved["label"],
            "table": table,
            "category": category,
            "subcategory": subcategory,
            "metric": metric,
        },
    )


def default_title(kpi: dict[str, Any]) -> str:
    """A name a meeting can scan — the label plus what happened."""
    direction = kpi.get("direction")
    word = {"up": "increase", "down": "decrease", "flat": "stable"}.get(direction or "", "reading")
    return f"{kpi['label']} {word}"


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def create_issue(
    session: Session,
    *,
    version: PresentationVersion,
    tables: Sequence[TableOut],
    department: str,
    period: str | None = None,
    table: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    metric: str | None = None,
    title: str | None = None,
    description: str | None = None,
    severity: str | None = None,
    origin: dict[str, Any] | None = None,
    language: str = "en",
) -> Issue:
    """Raise an issue about one reading of one snapshot."""
    kpi, reference, _basis = find_kpi(
        tables,
        department=department,
        period=period,
        table=table,
        category=category,
        subcategory=subcategory,
        metric=metric,
    )
    doc = text_to_doc(description)
    selector = kpi["selector"]

    issue = Issue(
        version_id=version.id,
        department=Department(department),
        period_label=kpi["period"]["label"],
        period=kpi["period"],
        reference_period=reference,
        table_name=selector.get("table"),
        category=selector.get("category"),
        subcategory=selector.get("subcategory"),
        metric=selector.get("metric"),
        series_type=selector.get("seriesType"),
        title=title or default_title(kpi),
        description_doc=doc,
        description_text=doc_to_text(doc),
        translation_key=documents.content_hash(doc),
        language=language,
        severity=IssueSeverity(severity) if severity else default_severity(kpi),
        status=IssueStatus.OPEN,
        value=kpi["value"],
        previous_value=kpi["previousValue"],
        delta=kpi["delta"],
        delta_percent=kpi["deltaPercent"],
        target=kpi["target"],
        direction=kpi["direction"],
        analytical_severity=kpi["severity"],
        trend=kpi.get("trend"),
        source_cell=kpi["source"],
        source_range=kpi["sourceRange"],
        origin=origin,
    )
    session.add(issue)
    session.flush()
    logger.info(
        "issue %d raised on version %d: %s (%s)",
        issue.id,
        version.id,
        issue.title,
        issue.period_label,
    )
    return issue


def update_issue(session: Session, issue: Issue, changes: dict[str, Any]) -> Issue:
    """Edit the editorial half.  The numbers are not editable by hand."""
    rejected = [key for key in changes if key not in EDITABLE_FIELDS]
    if rejected:
        raise ValidationError(
            "These fields come from the data and cannot be edited",
            {"fields": sorted(rejected)},
        )

    if "title" in changes and changes["title"]:
        issue.title = changes["title"]
    if "description" in changes:
        doc = text_to_doc(changes["description"])
        issue.description_doc = doc
        issue.description_text = doc_to_text(doc)
        issue.translation_key = documents.content_hash(doc)
    if changes.get("severity"):
        issue.severity = IssueSeverity(changes["severity"])
    if changes.get("status"):
        issue.status = IssueStatus(changes["status"])
    if changes.get("language"):
        issue.language = changes["language"]

    issue.updated_at = datetime.now(timezone.utc)
    session.flush()
    logger.info("issue %d updated (%s)", issue.id, ", ".join(sorted(changes)))
    return issue


def attach_media(
    session: Session, issue: Issue, asset: Asset, caption: str | None = None
) -> IssueMedia:
    media = IssueMedia(
        asset_id=asset.id,
        caption=caption,
        order_index=len(issue.media),
    )
    # append through the relationship so the loaded collection stays correct
    issue.media.append(media)
    session.flush()
    logger.info("issue %d: attached asset %d", issue.id, asset.id)
    return media


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #
def list_issues(
    session: Session,
    *,
    version_id: int,
    period: str | None = None,
    status: str | None = None,
) -> list[Issue]:
    query = select(Issue).where(Issue.version_id == version_id).order_by(Issue.id)
    if period:
        query = query.where(Issue.period_label == period)
    if status:
        query = query.where(Issue.status == IssueStatus(status))
    return list(session.scalars(query))


def get_issue(session: Session, issue_id: int, version_id: int | None = None) -> Issue:
    issue = session.get(Issue, issue_id)
    if issue is None or (version_id is not None and issue.version_id != version_id):
        raise NotFound("Issue not found", {"issueId": issue_id})
    return issue
