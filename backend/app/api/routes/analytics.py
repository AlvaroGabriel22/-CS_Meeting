"""Analytics endpoints — series, period comparison, version comparison.

Model-oriented on purpose: the path names a *version*, the query names what to
look at (``table``, ``category``, ``subcategory``, ``metric``, ``period``).
There is no ``/iqc/aug`` and there never will be.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.db.base import get_session
from app.db.models import PresentationVersion
from app.schemas.analytics import ComparisonResponseOut, SeriesResponseOut
from app.schemas.table import TableOut
from app.services import analytics, presentation_service, serializers

router = APIRouter(prefix="/api/versions", tags=["analytics"])


def _tables_of(version: PresentationVersion) -> list[TableOut]:
    return [
        serializers.table_out(definition)
        for data in version.imports
        for definition in sorted(data.tables, key=lambda item: item.order_index)
    ]


def _department_of(version: PresentationVersion) -> str:
    return version.imports[0].department.value if version.imports else "IQC"


def _source_ranges(tables: list[TableOut]) -> dict[str, str]:
    return {(table.title or table.sheet_name): table.source_range for table in tables}


def _filters(
    table: str | None, category: str | None, subcategory: str | None, metric: str | None
) -> dict[str, str | None]:
    return {
        "table": table,
        "category": category,
        "subcategory": subcategory,
        "metric": metric,
    }


@router.get("/{version_id}/analytics/series", response_model=SeriesResponseOut)
def get_series(
    version_id: int,
    table: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    metric: str | None = None,
    order: str = Query("file", pattern="^(file|chronological)$"),
    limit: int | None = None,
    session: Session = Depends(get_session),
) -> SeriesResponseOut:
    """Chart-ready series for one snapshot.

    ``order=chronological`` sorts the period axis by the engine's ``sortKey``;
    the default keeps the workbook's own column order.  The response also lists
    the selector options found in the snapshot, so the UI never needs a
    hardcoded list of tables, metrics or periods.
    """
    version = presentation_service.get_version(session, version_id)
    tables = _tables_of(version)
    payload = analytics.build_series_response(
        tables,
        filters=_filters(table, category, subcategory, metric),
        order=order,
        limit=limit,
    )
    payload.update(
        {"versionId": version.id, "department": _department_of(version)}
    )
    return SeriesResponseOut.model_validate(payload)


@router.get("/{version_id}/analytics/comparison", response_model=ComparisonResponseOut)
def compare_periods(
    version_id: int,
    period_a: str = Query(..., alias="periodA"),
    period_b: str = Query(..., alias="periodB"),
    table: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    metric: str | None = None,
    insights: int = 10,
    session: Session = Depends(get_session),
) -> ComparisonResponseOut:
    """Two periods of the same snapshot: value A, value B, delta, delta %."""
    version = presentation_service.get_version(session, version_id)
    tables = _tables_of(version)
    department = _department_of(version)

    payload = analytics.compare_periods(
        tables,
        period_a=period_a,
        period_b=period_b,
        filters=_filters(table, category, subcategory, metric),
        department=department,
    )
    payload.update(
        {
            "versionId": version.id,
            "versionNumber": version.number,
            "department": department,
            "insights": analytics.build_insights(
                payload,
                department=department,
                version_id=version.id,
                version_number=version.number,
                source_ranges=_source_ranges(tables),
                limit=insights,
            ),
        }
    )
    return ComparisonResponseOut.model_validate(payload)


@router.get("/{version_id}/analytics/versus/{other_id}", response_model=ComparisonResponseOut)
def compare_versions(
    version_id: int,
    other_id: int,
    period: str = Query(...),
    table: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    metric: str | None = None,
    insights: int = 10,
    session: Session = Depends(get_session),
) -> ComparisonResponseOut:
    """The same period in two snapshots: what moved between the two imports.

    ``version_id`` is the baseline (A) and ``other_id`` the one being read (B).
    Neither snapshot is modified.
    """
    if version_id == other_id:
        raise ValidationError("Compare two different versions", {"versionId": version_id})

    baseline = presentation_service.get_version(session, version_id)
    other = presentation_service.get_version(session, other_id)
    tables_a, tables_b = _tables_of(baseline), _tables_of(other)
    department = _department_of(other)

    payload = analytics.compare_versions(
        tables_a,
        tables_b,
        period=period,
        filters=_filters(table, category, subcategory, metric),
        department=department,
    )
    payload.update(
        {
            "versionId": baseline.id,
            "versionNumber": baseline.number,
            "comparedVersionId": other.id,
            "comparedVersionNumber": other.number,
            "department": department,
            "insights": analytics.build_insights(
                payload,
                department=department,
                version_id=other.id,
                version_number=other.number,
                source_ranges=_source_ranges(tables_b),
                limit=insights,
            ),
        }
    )
    return ComparisonResponseOut.model_validate(payload)
