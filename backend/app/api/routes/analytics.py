"""Series endpoint — the chart-ready projection of one snapshot.

Model-oriented on purpose: the path names a *version*, the query names what to
look at (``table``, ``category``, ``subcategory``, ``metric``).  There is no
``/iqc/aug`` and there never will be.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.base import get_session
from app.db.models import PresentationVersion
from app.schemas.analytics import SeriesResponseOut
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
