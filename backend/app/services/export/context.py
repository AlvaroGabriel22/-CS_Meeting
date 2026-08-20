"""What an export contains — assembled once, rendered twice.

The PDF and the PPT must show the same thing the screen shows, so both read
this single context, built from the page's own state: the version, the period,
the table and the metric the user had selected (ADR-0030).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.db.models import PresentationVersion
from app.schemas.table import TableOut
from app.services import analytics, assets, executive, issues as issue_service
from app.services import presentation_service, serializers
from app.services.render_model import build_table_view

logger = logging.getLogger(__name__)


@dataclass
class ExportContext:
    department: str
    version_id: int
    version_number: int | None
    version_label: str | None
    raw_file: str | None
    period: dict[str, Any] | None
    reference_period: dict[str, Any] | None
    comparison_basis: str
    metric: str | None
    table: str | None
    kpis: list[dict[str, Any]] = field(default_factory=list)
    insights: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    series: list[dict[str, Any]] = field(default_factory=list)
    periods: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    comparison: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def title(self) -> str:
        return f"{self.department} — Quality Review"

    @property
    def subtitle(self) -> str:
        period = (self.period or {}).get("label") or "—"
        version = f"v{self.version_number}" if self.version_number else "—"
        return f"{period} · {version}"


def _issue_payload(issue: Any) -> dict[str, Any]:
    return {
        "id": issue.id,
        "title": issue.title,
        "description": issue.description_text or "",
        "severity": issue.severity.value,
        "status": issue.status.value,
        "period": issue.period_label,
        "table": issue.table_name,
        "category": issue.category,
        "subcategory": issue.subcategory,
        "metric": issue.metric,
        "value": issue.value,
        "previousValue": issue.previous_value,
        "delta": issue.delta,
        "deltaPercent": issue.delta_percent,
        "source": issue.source_cell,
        "sourceRange": issue.source_range,
        "trend": issue.trend,
        "images": [],  # filled in below, with paths on disk
    }


def build_context(
    session: Session,
    *,
    version_id: int,
    period: str | None = None,
    table: str | None = None,
    metric: str | None = None,
    compare_with: int | None = None,
    include_tables: bool = True,
    include_charts: bool = True,
) -> ExportContext:
    """Assemble exactly what the executive page is showing."""
    version: PresentationVersion = presentation_service.get_version(session, version_id)
    tables: list[TableOut] = [
        serializers.table_out(definition)
        for data in version.imports
        for definition in sorted(data.tables, key=lambda item: item.order_index)
    ]
    department = version.imports[0].department.value if version.imports else "IQC"

    summary = executive.build_executive_view(
        tables,
        period_label=period,
        table=table,
        metric=metric,
        department=department,
        version_id=version.id,
        version_number=version.number,
    )
    chosen_period = (summary.get("period") or {}).get("label")
    chosen_table = table or (summary["options"]["tables"][0] if summary["options"]["tables"] else None)

    context = ExportContext(
        department=department,
        version_id=version.id,
        version_number=version.number,
        version_label=version.label,
        raw_file=(version.summary or {}).get("rawFile"),
        period=summary.get("period"),
        reference_period=summary.get("previousPeriod"),
        comparison_basis=summary.get("comparisonBasis", "none"),
        metric=summary.get("metric"),
        table=chosen_table,
        kpis=summary.get("kpis", []),
        insights=summary.get("insights", []),
        warnings=list(summary.get("warnings", [])),
        periods=summary.get("periods", []),
    )

    # issues raised on this snapshot for this period, with their images
    for issue in issue_service.list_issues(
        session, version_id=version.id, period=chosen_period
    ):
        payload = _issue_payload(issue)
        for media in issue.media:
            path: Path = assets.absolute_path(media.asset)
            if path.exists():
                payload["images"].append(
                    {"path": str(path), "caption": media.caption, "mime": media.asset.mime_type}
                )
        context.issues.append(payload)

    if include_charts:
        chart = analytics.build_series_response(
            tables,
            filters={"table": chosen_table, "metric": context.metric},
            order="file",
        )
        context.series = chart["series"]
        context.periods = chart["periods"] or context.periods

    if include_tables:
        context.tables = [build_table_view(item) for item in tables]

    if compare_with:
        other = presentation_service.get_version(session, compare_with)
        other_tables = [
            serializers.table_out(definition)
            for data in other.imports
            for definition in sorted(data.tables, key=lambda item: item.order_index)
        ]
        comparison = analytics.compare_versions(
            tables,
            other_tables,
            period=chosen_period or "",
            filters={"table": chosen_table, "metric": context.metric},
            department=department,
        )
        comparison.update(
            {
                "versionNumber": version.number,
                "comparedVersionNumber": other.number,
            }
        )
        context.comparison = comparison

    logger.info(
        "export context: %s %s v%s — %d KPI(s), %d insight(s), %d issue(s), %d table(s)",
        department,
        chosen_period,
        version.number,
        len(context.kpis),
        len(context.insights),
        len(context.issues),
        len(context.tables),
    )
    return context
