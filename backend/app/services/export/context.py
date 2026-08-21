"""What an export contains — assembled once, rendered twice.

The PDF and the deck must show what the page shows, so both read this single
context: the three charts, the three tables and the report the author wrote
(ADR-0030, ADR-0036).

Translation reaches the file the same way it reaches the screen: the report is
looked up in the overlay, and nothing else is (ADR-0035).  A translated export
therefore holds exactly the numbers of an untranslated one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Department, DepartmentSettings, PresentationVersion
from app.schemas.table import TableOut
from app.services import assets, charts, presentation_service, reports, serializers
from app.services.render_model import build_table_view
from app.services.translation import TranslationService

logger = logging.getLogger(__name__)


@dataclass
class ExportContext:
    department: str
    version_id: int
    version_number: int | None
    version_label: str | None
    raw_file: str | None
    metric: str | None = None
    charts: list[dict[str, Any]] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    #: the report the author built: title, columns, rows of blocks (ADR-0038)
    report: dict[str, Any] = field(default_factory=dict)
    #: absolute paths of the images it uses, by asset id
    report_images: dict[int, str] = field(default_factory=dict)
    language: str = "en"
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def title(self) -> str:
        return f"{self.department} — Quality Review"

    @property
    def subtitle(self) -> str:
        version = f"v{self.version_number}" if self.version_number else "—"
        return f"{self.version_label or '—'} · {version}"

    @property
    def has_report(self) -> bool:
        return bool(self.report.get("columns") or self.report.get("rows") or self.report.get("title"))


def build_context(
    session: Session,
    *,
    version_id: int,
    include_tables: bool = True,
    include_charts: bool = True,
    include_report: bool = True,
    language: str | None = None,
    translate: bool = False,
) -> ExportContext:
    """Assemble exactly what the department page is showing."""
    version: PresentationVersion = presentation_service.get_version(session, version_id)
    tables: list[TableOut] = [
        serializers.table_out(definition)
        for data in version.imports
        for definition in sorted(data.tables, key=lambda item: item.order_index)
    ]
    department = version.imports[0].department.value if version.imports else "IQC"

    context = ExportContext(
        department=department,
        version_id=version.id,
        version_number=version.number,
        version_label=version.label,
        raw_file=(version.summary or {}).get("rawFile"),
    )

    settings = session.scalars(
        select(DepartmentSettings).where(DepartmentSettings.department == Department(department))
    ).first()
    chart_titles = (settings.chart_titles if settings else {}) or {}
    table_titles = (settings.table_titles if settings else {}) or {}

    if include_charts:
        built = charts.build_charts(
            tables,
            department=department,
            configured=(settings.chart_series if settings else {}) or {},
        )
        context.metric = built["metric"]
        context.charts = [
            {**chart, "title": chart_titles.get(chart["table"]) or chart["table"]}
            for chart in built["charts"]
        ]

    if include_tables:
        context.tables = []
        for item in tables:
            view = build_table_view(item)
            name = view.get("title") or view.get("sheet")
            view["title"] = table_titles.get(name) or name
            context.tables.append(view)

    report = reports.get_report(session, version.id) if include_report else None
    if report is not None:
        content = report.content or reports.empty_content()

        if translate and language and language != report.language:
            # only the report is translated — the rest of the page is interface
            # text and workbook labels, which never leave the process (ADR-0036)
            outcome = TranslationService().translate_texts(
                session,
                reports.translatable_strings(content),
                source_language=report.language,
                target_language=language,
                department=department,
            )
            content = reports.apply_translation(content, outcome.mapping)
            context.language = language

        context.report = content
        for media in report.media:
            path: Path = assets.absolute_path(media.asset)
            if path.exists():
                context.report_images[media.asset_id] = str(path)

    logger.info(
        "export context: %s v%s — %d chart(s), %d table(s), report %s, language %s",
        department,
        version.number,
        len(context.charts),
        len(context.tables),
        "yes" if context.has_report else "no",
        context.language,
    )
    return context
