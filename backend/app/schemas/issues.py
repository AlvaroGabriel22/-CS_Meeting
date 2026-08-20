"""Wire contract for issue reports (Sprint 5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict

from .common import CamelModel
from .imports import DepartmentLiteral
from .table import PeriodOut

IssueStatusLiteral = Literal["open", "in_progress", "resolved", "closed"]
IssueSeverityLiteral = Literal["info", "low", "medium", "high"]


class IssueMediaOut(CamelModel):
    """An image attached as evidence — never analytical data."""

    id: int
    asset_id: int
    url: str
    mime_type: str
    size_bytes: int
    caption: str | None = None
    order_index: int = 0


class IssueOut(CamelModel):
    """An issue: what the user wrote, and the numbers that justify it."""

    id: int
    version_id: int
    department: DepartmentLiteral
    # --- what it is about --------------------------------------------------- #
    period: PeriodOut | None = None
    reference_period: PeriodOut | None = None
    table: str | None = None
    category: str | None = None
    subcategory: str | None = None
    metric: str | None = None
    series_type: str | None = None
    # --- editorial (the only editable half) --------------------------------- #
    title: str
    description: str | None = None
    description_doc: dict[str, Any] = {}
    translation_key: str | None = None
    language: str = "en"
    severity: IssueSeverityLiteral = "medium"
    status: IssueStatusLiteral = "open"
    # --- the numbers, read from the model ----------------------------------- #
    value: float | None = None
    previous_value: float | None = None
    delta: float | None = None
    delta_percent: float | None = None
    target: float | None = None
    direction: str | None = None
    analytical_severity: str | None = None
    trend: dict[str, Any] | None = None
    # --- provenance ---------------------------------------------------------- #
    source_cell: str | None = None
    source_range: str | None = None
    origin: dict[str, Any] | None = None
    media: list[IssueMediaOut] = []
    created_at: datetime
    updated_at: datetime


class IssueCreateIn(CamelModel):
    """What the client may choose: the selector and the editorial text.

    The values, the delta and the provenance are recomputed from the snapshot —
    they are never accepted from the client (ADR-0029).
    """

    period: str | None = None
    table: str | None = None
    category: str | None = None
    subcategory: str | None = None
    metric: str | None = None
    title: str | None = None
    description: str | None = None
    severity: IssueSeverityLiteral | None = None
    language: str = "en"
    #: the insight this was raised from, kept for traceability
    origin: dict[str, Any] | None = None


class IssueUpdateIn(CamelModel):
    """Only the editorial half can be edited.

    Unknown fields are *kept* rather than dropped so the service can refuse
    them by name: a client trying to set ``value`` gets told why, instead of
    seeing its change silently ignored.
    """

    model_config = ConfigDict(
        alias_generator=CamelModel.model_config["alias_generator"],
        populate_by_name=True,
        from_attributes=True,
        extra="allow",
    )

    title: str | None = None
    description: str | None = None
    severity: IssueSeverityLiteral | None = None
    status: IssueStatusLiteral | None = None
    language: str | None = None
